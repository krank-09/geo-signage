"""Client isolation: one customer must never see, change, reference or receive another customer's data."""
import asyncio

import pytest
from sqlalchemy import create_engine, inspect, text

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


def bearer(token: str, client: int | None = None) -> dict:
    h = {"Authorization": f"Bearer {token}"}
    if client is not None:
        h["X-Client-Id"] = str(client)
    return h


def login(client, username, password):
    r = client.post("/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def world(client, admin):
    """Default client (A, has the seeded data) + a new client B with its own admin, zone, content, group, device."""
    a = next(c for c in client.get("/clients", headers=admin).json() if c["name"] == "Default")
    created = client.post("/clients", headers=admin, json={"name": "Acme Retail"})
    assert created.status_code == 201, created.text
    b = created.json()
    assert client.post("/users", headers=admin, json={"username": "acme_admin", "password": "acmepass123", "role": "admin", "client_id": b["id"]}).status_code == 201
    assert client.post("/users", headers=admin, json={"username": "acme_viewer", "password": "acmepass123", "role": "viewer", "client_id": b["id"]}).status_code == 201
    bh = bearer(login(client, "acme_admin", "acmepass123"))
    ah = {**admin, "X-Client-Id": str(a["id"])}

    zone = client.post("/zones", headers=bh, json={"name": "Delhi Zone", "polygon": [[28, 76], [28, 78], [29, 78], [29, 76]], "priority": 5})
    content = client.post("/content/upload", headers=bh, files={"file": ("acme.png", PNG, "image/png")}, data={"name": "Acme Ad", "duration": "5"})
    group = client.post("/groups", headers=bh, json={"name": "North India"})
    assert zone.status_code == content.status_code == group.status_code == 201, (zone.text, content.text, group.text)
    assign = client.post("/assignments", headers=bh, json={"content_id": content.json()["id"], "zone_id": zone.json()["id"], "priority": 10})
    dev = client.post("/devices", headers=bh, json={"device_id": "ACME-1", "name": "Acme screen", "connection_type": "wifi"})
    assert assign.status_code == dev.status_code == 201, (assign.text, dev.text)
    tok = client.post("/device/register", json={"device_id": "ACME-1", "registration_token": dev.json()["registration_token"]}).json()["access_token"]
    dh = bearer(tok)
    client.post("/device/location", headers=dh, json={"latitude": 28.6139, "longitude": 77.209})

    yield {"a": a, "b": b, "ah": ah, "bh": bh, "zone": zone.json(), "content": content.json(), "group": group.json(),
           "assign": assign.json(), "dev": dev.json(), "dh": dh, "admin": admin}

    # leave the shared database as we found it: later test modules expect a single client
    for path in ("/broadcasts",):
        client.delete(path, headers=bh)
    client.delete("/devices/ACME-1", headers=bh)
    client.delete(f"/assignments/{assign.json()['id']}", headers=bh)
    client.delete(f"/content/{content.json()['id']}", headers=bh)
    client.delete(f"/zones/{zone.json()['id']}", headers=bh)
    client.delete(f"/groups/{group.json()['id']}", headers=bh)
    for u in client.get("/users", headers=admin).json():
        if u["username"].startswith("acme_") or u["client_id"] == b["id"]:
            client.delete(f"/users/{u['id']}", headers=admin)
    client.put(f"/clients/{b['id']}", headers=admin, json={"active": True, "clear_device_limit": True})
    assert client.delete(f"/clients/{b['id']}", headers=admin).status_code == 200


# ------------------------------------------------------------------ managing clients
def test_platform_manages_clients_and_client_admins_cannot(client, admin, world):
    listed = {c["name"]: c for c in client.get("/clients", headers=admin).json()}
    assert {"Default", "Acme Retail"} <= set(listed)
    assert listed["Acme Retail"]["enrollment_key"].startswith("enr_") and listed["Acme Retail"]["devices"] == 1
    assert client.post("/clients", headers=admin, json={"name": "Acme Retail"}).status_code == 409
    assert client.post("/clients", headers=world["bh"], json={"name": "Sneaky"}).status_code == 403
    assert client.put(f"/clients/{world['a']['id']}", headers=world["bh"], json={"name": "Hijacked"}).status_code == 403
    assert client.delete(f"/clients/{world['a']['id']}", headers=world["bh"]).status_code == 403
    mine = client.get("/clients", headers=world["bh"]).json()
    assert [c["name"] for c in mine] == ["Acme Retail"]           # a client only ever sees itself


def test_platform_needs_a_client_for_writes_once_several_exist(client, world):
    admin = world["admin"]
    r = client.post("/zones", headers=admin, json={"name": "Nowhere", "polygon": [[0, 0], [0, 1], [1, 1]]})
    assert r.status_code == 400 and "Select a client" in r.json()["detail"]
    everything = {d["device_id"] for d in client.get("/devices", headers=admin).json()}
    assert {"DEV-001", "ACME-1"} <= everything                                       # read-only aggregate across clients
    only_a = {d["device_id"] for d in client.get("/devices", headers=world["ah"]).json()}
    only_b = {d["device_id"] for d in client.get("/devices", headers={**admin, "X-Client-Id": str(world["b"]["id"])}).json()}
    assert "ACME-1" not in only_a and only_b == {"ACME-1"}
    assert client.get("/devices", headers={**admin, "X-Client-Id": "99999"}).status_code == 404
    assert client.get("/devices", headers={**admin, "X-Client-Id": "abc"}).status_code == 404


def test_client_users_are_pinned_to_their_client(client, world):
    assert {d["device_id"] for d in client.get("/devices", headers=world["bh"]).json()} == {"ACME-1"}
    forged = {**world["bh"], "X-Client-Id": str(world["a"]["id"])}                   # try to act as the other client
    assert {d["device_id"] for d in client.get("/devices", headers=forged).json()} == {"ACME-1"}
    assert client.post("/zones", headers=forged, json={"name": "Mine anyway", "polygon": [[0, 0], [0, 1], [1, 1]]}).json()["client_id"] == world["b"]["id"]
    for z in client.get("/zones", headers=world["bh"]).json():
        if z["name"] == "Mine anyway":
            client.delete(f"/zones/{z['id']}", headers=world["bh"])
    me = client.get("/auth/me", headers=world["bh"]).json()
    assert me["client_name"] == "Acme Retail" and me["platform"] is False


def test_viewers_are_read_only_inside_their_client(client, world):
    vh = bearer(login(client, "acme_viewer", "acmepass123"))
    assert client.get("/zones", headers=vh).status_code == 200
    assert client.post("/zones", headers=vh, json={"name": "x", "polygon": [[0, 0], [0, 1], [1, 1]]}).status_code == 403
    assert client.post("/broadcasts", headers=vh, json={"message": "x"}).status_code == 403


# ------------------------------------------------------------------ the isolation matrix (IDOR)
def test_client_b_cannot_touch_client_a_objects_by_id(client, world):
    bh = world["bh"]
    a_dev, a_zone, a_content, a_assign, a_group = "DEV-001", None, None, None, None
    a = world["ah"]
    a_zone = client.get("/zones", headers=a).json()[0]["id"]
    a_content = client.get("/content", headers=a).json()[0]["id"]
    a_assign = client.get("/assignments", headers=a).json()[0]["id"]
    a_group = client.get("/groups", headers=a).json()[0]["id"]

    # reads: not in lists, 404 by id
    assert all(z["id"] != a_zone for z in client.get("/zones", headers=bh).json())
    assert all(c["id"] != a_content for c in client.get("/content", headers=bh).json())
    assert all(x["id"] != a_assign for x in client.get("/assignments", headers=bh).json())
    assert all(g["id"] != a_group for g in client.get("/groups", headers=bh).json())
    assert client.get(f"/devices/{a_dev}", headers=bh).status_code == 404
    assert client.get(f"/devices/{a_dev}/logs", headers=bh).status_code == 404
    assert client.get(f"/content/{a_content}/file?token={bh['Authorization'][7:]}").status_code == 404
    # writes: 404, and nothing changed
    assert client.put(f"/zones/{a_zone}", headers=bh, json={"name": "pwned", "polygon": [[0, 0], [0, 1], [1, 1]]}).status_code == 404
    assert client.delete(f"/zones/{a_zone}", headers=bh).status_code == 404
    assert client.put(f"/content/{a_content}", headers=bh, json={"name": "pwned"}).status_code == 404
    assert client.delete(f"/content/{a_content}", headers=bh).status_code == 404
    assert client.put(f"/assignments/{a_assign}", headers=bh, json={"content_id": world["content"]["id"]}).status_code == 404
    assert client.delete(f"/assignments/{a_assign}", headers=bh).status_code == 404
    assert client.delete(f"/groups/{a_group}", headers=bh).status_code == 404
    for verb, path in (("put", f"/devices/{a_dev}"), ("delete", f"/devices/{a_dev}"), ("post", f"/devices/{a_dev}/rotate-token"), ("post", f"/devices/{a_dev}/sync")):
        kw = {"json": {"name": "pwned"}} if verb == "put" else {}
        assert getattr(client, verb)(path, headers=bh, **kw).status_code == 404, path
    assert client.get("/zones", headers=a).json()[0]["name"] != "pwned"
    assert client.get(f"/devices/{a_dev}", headers=a).status_code == 200                       # A's device is untouched


def test_client_b_cannot_reference_client_a_objects(client, world):
    bh, a = world["bh"], world["ah"]
    a_zone = client.get("/zones", headers=a).json()[0]["id"]
    a_content = client.get("/content", headers=a).json()[0]["id"]
    a_group = client.get("/groups", headers=a).json()[0]["id"]
    mk = lambda **kw: client.post("/assignments", headers=bh, json=kw)                        # noqa: E731
    assert mk(content_id=a_content).status_code == 400                                           # same answer as "unknown"
    assert mk(content_id=world["content"]["id"], zone_id=a_zone).status_code == 400
    assert mk(content_id=world["content"]["id"], group_id=a_group).status_code == 400
    assert client.post("/broadcasts", headers=bh, json={"message": "x", "zone_id": a_zone}).status_code == 404
    assert client.post("/broadcasts", headers=bh, json={"message": "x", "group_id": a_group}).status_code == 404
    assert client.post("/broadcasts", headers=bh, json={"message": "x", "device_id": "DEV-001"}).status_code == 404
    assert client.post("/devices", headers=bh, json={"device_id": "ACME-2", "name": "x", "group_id": a_group}).status_code == 404
    assert client.get(f"/discovery/agents?zone_id={a_zone}", headers=bh).status_code == 404
    assert client.post("/emergency", headers=bh, json={"content_id": a_content}).status_code == 400


def test_same_names_are_fine_across_clients_but_not_within_one(client, world):
    bh, a = world["bh"], world["ah"]
    assert any(z["name"] == "Delhi Zone" for z in client.get("/zones", headers=a).json())        # A has one too
    assert client.post("/zones", headers=bh, json={"name": "Delhi Zone", "polygon": [[0, 0], [0, 1], [1, 1]]}).status_code == 409
    assert any(g["name"] == "North India" for g in client.get("/groups", headers=a).json())
    assert client.post("/groups", headers=bh, json={"name": "North India"}).status_code == 409
    r = client.post("/cities/kochi/zone", headers=bh, json={})
    assert r.status_code == 201
    assert client.post("/cities/kochi/zone", headers=a, json={}).status_code == 201             # each client can have "Kochi Zone"
    for h in (bh, a):
        for z in client.get("/zones", headers=h).json():
            if z["name"] == "Kochi Zone":
                client.delete(f"/zones/{z['id']}", headers=h)


def test_device_ids_are_global_and_do_not_leak(client, world):
    r = client.post("/devices", headers=world["bh"], json={"device_id": "DEV-001", "name": "clash"})
    assert r.status_code == 409 and "not available" in r.json()["detail"]


# ------------------------------------------------------------------ what a display sees
def test_displays_only_get_their_own_clients_content_and_broadcasts(client, world):
    dh, bh, a = world["dh"], world["bh"], world["ah"]
    content = client.get("/device/ACME-1/content", headers=dh).json()
    assert [i["name"] for i in content["items"]] == ["Acme Ad"] and content["reason"].startswith("zone")
    a_content = client.get("/content", headers=a).json()[0]["id"]
    assert client.get(f"/device/ACME-1/media/{a_content}", headers=dh).status_code == 404       # another client's file, whatever the id
    assert client.get(f"/device/ACME-1/media/{world['content']['id']}", headers=dh).status_code == 200

    # a broadcast or emergency in A never reaches B's display, and vice versa
    client.post("/broadcasts", headers=a, json={"message": "for A only"})
    client.post("/emergency", headers=a, json={"content_id": a_content})
    seen = client.get("/device/ACME-1/content", headers=dh).json()
    assert seen["broadcasts"] == [] and not seen["emergency"]
    mine = client.post("/broadcasts", headers=bh, json={"message": "for B only"}).json()
    assert [b["message"] for b in client.get("/device/ACME-1/content", headers=dh).json()["broadcasts"]] == ["for B only"]
    a_dev = client.post("/device/heartbeat", headers=dh, json={}).json()
    assert a_dev["manifest_version"]
    client.delete("/broadcasts", headers=a)
    client.delete("/emergency", headers=a)
    client.delete(f"/broadcasts/{mine['id']}", headers=bh)


def test_a_device_in_a_client_without_assignments_shows_nothing(client, world):
    # B's only assignment is zone-based; move the display out of the zone: B has no default content, and A's default must not leak
    client.post("/device/location", headers=world["dh"], json={"latitude": 10.0, "longitude": 10.0})
    assert client.get("/device/ACME-1/content", headers=world["dh"]).json()["items"] == []
    client.post("/device/location", headers=world["dh"], json={"latitude": 28.6139, "longitude": 77.209})


# ------------------------------------------------------------------ monitoring stays inside the client
def test_monitoring_is_scoped(client, world):
    bh, a = world["bh"], world["ah"]
    ov_b, ov_a = client.get("/monitoring/overview", headers=bh).json(), client.get("/monitoring/overview", headers=a).json()
    assert ov_b["devices_total"] == 1 and ov_a["devices_total"] >= 3
    assert {r["device_id"] for r in client.get("/monitoring/logs?limit=200", headers=bh).json()} <= {"ACME-1"}
    an = client.get("/monitoring/analytics", headers=bh).json()
    assert [u["device_id"] for u in an["uptime"]] == ["ACME-1"]
    assert client.get("/monitoring/timeline", headers=bh).json()["devices_total"] == 1
    assert {a_["device_id"] for a_ in client.get("/alerts?state=all", headers=bh).json()} <= {"ACME-1"}


# ------------------------------------------------------------------ suspension, quotas
def test_suspending_a_client_locks_out_its_users_and_devices(client, world):
    admin, b = world["admin"], world["b"]
    assert client.put(f"/clients/{b['id']}", headers=admin, json={"active": False}).status_code == 200
    try:
        assert client.get("/devices", headers=world["bh"]).status_code == 403
        assert client.post("/auth/login", json={"username": "acme_admin", "password": "acmepass123"}).status_code == 200   # can log in...
        assert client.get("/zones", headers=bearer(login(client, "acme_admin", "acmepass123"))).status_code == 403          # ...but gets nothing
        assert client.post("/device/heartbeat", headers=world["dh"], json={}).status_code == 403
        assert client.get("/device/ACME-1/content", headers=world["dh"]).status_code == 403
        tok = client.post("/devices/ACME-1/rotate-token", headers={**admin, "X-Client-Id": str(b["id"])}).json()["registration_token"]
        assert client.post("/device/register", json={"device_id": "ACME-1", "registration_token": tok}).status_code == 403
        assert client.post("/discovery/announce", json={"secret": "k" * 32, "name": "x", "enrollment_key": b["enrollment_key"]}).status_code == 403
    finally:
        client.put(f"/clients/{b['id']}", headers=admin, json={"active": True})
    assert client.get("/devices", headers=world["bh"]).status_code == 200
    reg = client.post("/device/register", json={"device_id": "ACME-1", "registration_token": tok})
    assert reg.status_code == 200
    world["dh"].update(bearer(reg.json()["access_token"]))


def test_device_limit_is_enforced(client, world):
    admin, b, bh = world["admin"], world["b"], world["bh"]
    client.put(f"/clients/{b['id']}", headers=admin, json={"device_limit": 1})
    r = client.post("/devices", headers=bh, json={"device_id": "ACME-EXTRA", "name": "over the limit"})
    assert r.status_code == 409 and "limit" in r.json()["detail"].lower()
    client.put(f"/clients/{b['id']}", headers=admin, json={"clear_device_limit": True})
    assert client.post("/devices", headers=bh, json={"device_id": "ACME-EXTRA", "name": "now fine"}).status_code == 201
    client.delete("/devices/ACME-EXTRA", headers=bh)


# ------------------------------------------------------------------ users
def test_client_admins_manage_only_their_own_people(client, world):
    admin, bh, b = world["admin"], world["bh"], world["b"]
    names = {u["username"] for u in client.get("/users", headers=bh).json()}
    assert names == {"acme_admin", "acme_viewer"}                                             # never the platform admin or other clients' users
    made = client.post("/users", headers=bh, json={"username": "acme_new", "password": "newpass123", "role": "viewer", "client_id": world["a"]["id"]})
    assert made.status_code == 201 and made.json()["client_id"] == b["id"]                     # cannot place users in another client
    platform_user = next(u for u in client.get("/users", headers=admin).json() if u["username"] == "admin")
    assert client.put(f"/users/{platform_user['id']}/role", headers=bh, json={"role": "viewer"}).status_code == 404
    assert client.delete(f"/users/{platform_user['id']}", headers=bh).status_code == 404
    assert client.put(f"/users/{made.json()['id']}/role", headers=bh, json={"role": "admin", "client_id": world["a"]["id"]}).json()["client_id"] == b["id"]   # ignored
    moved = client.put(f"/users/{made.json()['id']}/role", headers=admin, json={"role": "viewer", "client_id": world["a"]["id"]})
    assert moved.json()["client_id"] == world["a"]["id"]                                       # only the platform can move people
    assert client.get("/users", headers=bh).status_code == 200
    client.delete(f"/users/{made.json()['id']}", headers=admin)


# ------------------------------------------------------------------ discovery + enrollment keys
def test_enrollment_keys_keep_unclaimed_displays_inside_their_client(client, world):
    from app.services import discovery

    discovery.reset()
    admin, a, bh = world["admin"], world["ah"], world["bh"]
    ann = lambda secret, **kw: client.post("/discovery/announce", json={"secret": secret * 32, "name": kw.pop("name"), "latitude": 28.61, "longitude": 77.2, **kw})  # noqa: E731
    assert ann("b", name="B laptop", enrollment_key=world["b"]["enrollment_key"]).status_code == 200
    assert ann("a", name="A laptop", enrollment_key=world["a"]["enrollment_key"]).status_code == 200
    assert ann("u", name="Unassigned laptop").status_code == 200
    assert ann("x", name="bad", enrollment_key="enr_wrong").status_code == 403

    seen = lambda h: {x["name"] for x in client.get("/discovery/agents", headers=h).json()["agents"]}     # noqa: E731
    assert seen(bh) == {"B laptop"}                                                            # a client sees only its own
    assert seen({"Authorization": world["bh"]["Authorization"], "X-Client-Id": str(world["a"]["id"])}) == {"B laptop"}   # header cannot widen it
    assert seen(admin) == {"A laptop", "B laptop", "Unassigned laptop"}                        # platform, all clients
    assert seen(a) == {"A laptop", "Unassigned laptop"}                                        # platform inside client A: A's + the unassigned pool

    pid = {x["name"]: x["id"] for x in client.get("/discovery/agents", headers=admin).json()["agents"]}
    # B cannot claim A's or the unassigned display, even knowing the id
    assert client.post("/devices", headers=bh, json={"device_id": "ACME-X", "name": "x", "discovery_id": pid["A laptop"]}).status_code == 409
    assert client.post("/devices", headers=bh, json={"device_id": "ACME-X", "name": "x", "discovery_id": pid["Unassigned laptop"]}).status_code == 409
    ok = client.post("/devices", headers=bh, json={"device_id": "ACME-X", "name": "claimed", "discovery_id": pid["B laptop"]})
    assert ok.status_code == 201 and ok.json()["claimed_agent"] is True
    client.delete("/devices/ACME-X", headers=bh)
    discovery.reset()


# ------------------------------------------------------------------ realtime
def test_events_only_reach_the_right_clients_dashboards():
    from app.realtime import Hub

    class Sock:
        def __init__(self):
            self.got = []

        async def send_text(self, text):
            self.got.append(text)

    async def run():
        hub, s1, s2, sp = Hub(), Sock(), Sock(), Sock()
        hub.admins.update({s1: 1, s2: 2, sp: None})
        await hub.to_admins({"event": "device_update"}, client_id=1)
        await hub.to_admins({"event": "platform_only"}, client_id=None)
        return len(s1.got), len(s2.got), len(sp.got)

    assert asyncio.run(run()) == (2, 1, 2)      # client 1 gets its own + platform-wide; client 2 only the platform-wide one; the platform gets all

    async def displays():
        hub, d1, d2 = Hub(), Sock(), Sock()
        hub.devices = {"D1": {d1}, "D2": {d2}}
        hub.device_client = {"D1": 1, "D2": 2}
        await hub.to_devices({"type": "sync"}, None, client_id=1)
        return len(d1.got), len(d2.got)

    assert asyncio.run(displays()) == (1, 0)


# ------------------------------------------------------------------ deleting clients, upgrading old data
def test_clients_with_data_cannot_be_deleted_and_the_last_one_cannot_either(client, admin, world):
    assert client.delete(f"/clients/{world['b']['id']}", headers=admin).status_code == 409
    empty = client.post("/clients", headers=admin, json={"name": "Temporary"}).json()
    assert client.delete(f"/clients/{empty['id']}", headers=admin).status_code == 200
    assert client.delete("/clients/99999", headers=admin).status_code == 404


def test_rows_from_before_multi_client_move_into_the_first_client(client):
    from app.database import SessionLocal
    from app.models import Client, Zone
    from app.services.clients import ensure_default_client

    with SessionLocal() as db:
        first = db.query(Client).order_by(Client.id).first()
        z = Zone(client_id=None, name="Legacy zone", polygon=[[0, 0], [0, 1], [1, 1]])   # as written by the previous version
        db.add(z)
        db.commit()
        ensure_default_client(db)
        db.refresh(z)
        assert z.client_id == first.id
        db.delete(z)
        db.commit()


def test_legacy_database_is_upgraded_in_place(tmp_path, monkeypatch):
    """A database from before multi-client: UNIQUE(name) on zones/groups must go, rows must survive, columns must appear."""
    import app.database as dbmod

    engine = create_engine(f"sqlite:///{tmp_path}/legacy.db")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE zones (id INTEGER PRIMARY KEY, name VARCHAR(100) NOT NULL UNIQUE, polygon JSON NOT NULL, priority INTEGER NOT NULL, color VARCHAR(16) NOT NULL)"))
        conn.execute(text("CREATE TABLE device_groups (id INTEGER PRIMARY KEY, name VARCHAR(100) NOT NULL UNIQUE)"))
        conn.execute(text("INSERT INTO zones VALUES (1, 'Delhi Zone', '[[0,0],[0,1],[1,1]]', 10, '#123456')"))
        conn.execute(text("INSERT INTO device_groups VALUES (1, 'North')"))
    monkeypatch.setattr(dbmod, "engine", engine)
    dbmod.sync_schema()
    dbmod.sync_schema()                                                                          # idempotent
    with engine.begin() as conn:
        assert conn.execute(text("SELECT name, priority, color FROM zones")).all() == [("Delhi Zone", 10, "#123456")]     # data survived
        conn.execute(text("UPDATE zones SET client_id = 1"))
        conn.execute(text("INSERT INTO zones (name, polygon, priority, color, client_id) VALUES ('Delhi Zone', '[]', 1, '#000000', 2)"))   # same name, other client
        conn.execute(text("INSERT INTO device_groups (name, client_id) VALUES ('North', 2)"))
    with engine.begin() as conn:
        from sqlalchemy.exc import IntegrityError

        with pytest.raises(IntegrityError):                                                      # ...but still unique within a client
            conn.execute(text("INSERT INTO zones (name, polygon, priority, color, client_id) VALUES ('Delhi Zone', '[]', 1, '#000000', 2)"))
    cols = {c["name"] for c in inspect(engine).get_columns("zones")}
    assert {"client_id", "id", "name", "polygon", "priority", "color"} <= cols
