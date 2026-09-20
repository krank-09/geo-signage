"""Health scoring + alerts, live broadcasts, connection types."""
from datetime import datetime, timedelta, timezone

import pytest

from app import config
from app.database import SessionLocal
from app.models import Device, Zone
from app.services import broadcasts as live
from app.services.health import evaluate_alerts, health


def _device(**kw) -> Device:
    base = dict(device_id="X", name="X", registration_token_hash="", last_seen=datetime.now(timezone.utc),
                cpu=10.0, memory=20.0, gps_ok=True, config={})
    return Device(**{**base, **kw})


# ------------------------------------------------------------------ health score (pure)
def test_health_score_penalties(monkeypatch):
    monkeypatch.setattr(config, "OFFLINE_THRESHOLD_SECONDS", 30)   # the suite runs with 2 s; use the real default here
    assert health(_device()) == (100, [])
    assert health(_device(last_seen=None)) == (0, ["Never connected"])
    assert health(_device(last_seen=datetime.now(timezone.utc) - timedelta(minutes=5))) == (0, ["Offline"])
    assert health(_device(cpu=100.0))[0] == 70
    assert health(_device(memory=100.0))[0] == 70
    assert health(_device(gps_ok=False))[0] == 90
    score, reasons = health(_device(cpu=100.0, memory=100.0, gps_ok=False))
    assert score == 30 and reasons == ["CPU 100%", "Memory 100%", "No GPS fix"]
    # a heartbeat later than two intervals (20 s by default) costs points, growing until it counts as offline
    late = health(_device(last_seen=datetime.now(timezone.utc) - timedelta(seconds=25)))
    assert late[0] < 100 and "Heartbeat running late" in late[1]


# ------------------------------------------------------------------ fixtures: one fresh device per module
@pytest.fixture(scope="module")
def dev(client, admin):
    r = client.post("/devices", headers=admin, json={"device_id": "HEALTH-1", "name": "Health test", "connection_type": "cellular_4g"})
    assert r.status_code == 201, r.text
    tok = client.post("/device/register", json={"device_id": "HEALTH-1", "registration_token": r.json()["registration_token"]}).json()
    return {"Authorization": f"Bearer {tok['access_token']}"}


def _beat(client, dev, **body):
    r = client.post("/device/heartbeat", headers=dev, json=body)
    assert r.status_code == 200, r.text


# ------------------------------------------------------------------ alerts lifecycle
def test_alert_raised_and_recovered(client, admin, dev):
    _beat(client, dev, cpu=10, memory=10, gps=True)
    with SessionLocal() as db:
        assert not [a for a in evaluate_alerts(db)["raised"] if a["device_id"] == "HEALTH-1"]

    _beat(client, dev, cpu=100, memory=100, gps=False)          # 100 - 30 - 30 - 10 = 30 < default threshold 50
    with SessionLocal() as db:
        raised = [a for a in evaluate_alerts(db)["raised"] if a["device_id"] == "HEALTH-1"]
    assert len(raised) == 1 and raised[0]["health"] == 30 and raised[0]["kind"] == "health_low"
    assert "CPU 100%" in raised[0]["message"]
    with SessionLocal() as db:                                    # no duplicate while it stays low
        assert not [a for a in evaluate_alerts(db)["raised"] if a["device_id"] == "HEALTH-1"]

    open_alerts = client.get("/alerts", headers=admin).json()
    mine = next(a for a in open_alerts if a["device_id"] == "HEALTH-1")
    assert mine["device_name"] == "Health test" and mine["acknowledged_at"] is None
    assert client.post(f"/alerts/{mine['id']}/ack", headers=admin).json()["acknowledged_by"] == "admin"

    devices = {d["device_id"]: d for d in client.get("/devices", headers=admin).json()}
    assert devices["HEALTH-1"]["health"] == 30 and devices["HEALTH-1"]["connection_type"] == "cellular_4g"

    _beat(client, dev, cpu=10, memory=10, gps=True)              # recovers
    with SessionLocal() as db:
        resolved = [a for a in evaluate_alerts(db)["resolved"] if a["device_id"] == "HEALTH-1"]
    assert len(resolved) == 1
    assert not [a for a in client.get("/alerts", headers=admin).json() if a["device_id"] == "HEALTH-1"]
    assert any(a["device_id"] == "HEALTH-1" for a in client.get("/alerts?state=all", headers=admin).json())


def test_threshold_setting_applies_immediately(client, admin, dev):
    assert client.get("/settings/health", headers=admin).json() == {"threshold": 50}
    _beat(client, dev, cpu=100, memory=100, gps=False)          # health 30
    assert client.put("/settings/health", headers=admin, json={"threshold": 60}).status_code == 200
    assert any(a["device_id"] == "HEALTH-1" for a in client.get("/alerts", headers=admin).json())
    client.put("/settings/health", headers=admin, json={"threshold": 20})   # 30 >= 20 + margin 5 -> resolves at once
    assert not any(a["device_id"] == "HEALTH-1" for a in client.get("/alerts", headers=admin).json())
    assert client.put("/settings/health", headers=admin, json={"threshold": 101}).status_code == 422
    client.put("/settings/health", headers=admin, json={"threshold": 50})
    _beat(client, dev, cpu=10, memory=10, gps=True)


def test_never_connected_devices_do_not_alert(client, admin):
    client.post("/devices", headers=admin, json={"device_id": "NEVER-1", "name": "Never seen"})
    with SessionLocal() as db:
        evaluate_alerts(db)
    assert not any(a["device_id"] == "NEVER-1" for a in client.get("/alerts?state=all", headers=admin).json())


# ------------------------------------------------------------------ live broadcasts
def test_broadcast_reaches_targeted_devices_only(client, admin, dev):
    client.post("/device/location", headers=dev, json={"latitude": 30.7333, "longitude": 76.7794})   # Chandigarh Zone
    zones = {z["name"]: z["id"] for z in client.get("/zones", headers=admin).json()}
    base = client.get("/device/HEALTH-1/content", headers=dev).json()
    assert base["broadcasts"] == []

    everyone = client.post("/broadcasts", headers=admin, json={"message": "Storm warning", "style": "banner", "severity": "warning"})
    assert everyone.status_code == 201
    delhi_only = client.post("/broadcasts", headers=admin, json={"message": "Delhi only", "zone_id": zones["Delhi Zone"]}).json()
    here = client.post("/broadcasts", headers=admin, json={"message": "Chandigarh sale", "zone_id": zones["Chandigarh Zone"], "duration_seconds": 60}).json()

    content = client.get("/device/HEALTH-1/content", headers=dev).json()
    shown = {b["message"]: b for b in content["broadcasts"]}
    assert set(shown) == {"Storm warning", "Chandigarh sale"}
    assert shown["Storm warning"]["style"] == "banner" and shown["Storm warning"]["remaining_seconds"] is None
    assert 0 < shown["Chandigarh sale"]["remaining_seconds"] <= 60
    assert content["manifest_version"] != base["manifest_version"]          # agents notice the change on their next reply

    hb = client.post("/device/heartbeat", headers=dev, json={}).json()
    assert hb["manifest_version"] == content["manifest_version"]

    assert client.delete(f"/broadcasts/{everyone.json()['id']}", headers=admin).status_code == 200
    assert {b["message"] for b in client.get("/device/HEALTH-1/content", headers=dev).json()["broadcasts"]} == {"Chandigarh sale"}
    client.delete(f"/broadcasts/{delhi_only['id']}", headers=admin)
    assert client.delete("/broadcasts", headers=admin).json()["ended"] >= 1
    assert client.get("/device/HEALTH-1/content", headers=dev).json()["broadcasts"] == []
    active = client.get("/broadcasts?state=active", headers=admin).json()
    assert active == [] and any(b["id"] == here["id"] for b in client.get("/broadcasts", headers=admin).json())


def test_broadcast_expires_and_targets_device_or_group(client, admin, dev):
    b = client.post("/broadcasts", headers=admin, json={"message": "Just you", "device_id": "HEALTH-1", "duration_seconds": 5}).json()
    other = client.post("/broadcasts", headers=admin, json={"message": "Someone else", "device_id": "DEV-002"}).json()
    with SessionLocal() as db:
        d = db.query(Device).filter(Device.device_id == "HEALTH-1").first()
        zones = {z.id for z in db.query(Zone).all()}
        now = datetime.now(timezone.utc)
        assert [x["message"] for x in live.active_for_device(db, d, zones, now)] == ["Just you"]
        assert live.active_for_device(db, d, zones, now + timedelta(seconds=6)) == []     # expired by itself
    client.delete(f"/broadcasts/{b['id']}", headers=admin)
    client.delete(f"/broadcasts/{other['id']}", headers=admin)


def test_broadcast_validation_and_permissions(client, admin):
    assert client.post("/broadcasts", headers=admin, json={"message": ""}).status_code == 422
    assert client.post("/broadcasts", headers=admin, json={"message": "x" * 281}).status_code == 422
    assert client.post("/broadcasts", headers=admin, json={"message": "x", "style": "confetti"}).status_code == 422
    assert client.post("/broadcasts", headers=admin, json={"message": "x", "duration_seconds": 1}).status_code == 422
    assert client.post("/broadcasts", headers=admin, json={"message": "x", "zone_id": 99999}).status_code == 404
    assert client.post("/broadcasts", headers=admin, json={"message": "x", "device_id": "NOPE-1"}).status_code == 404
    viewer = client.post("/auth/login", json={"username": "viewer1", "password": "viewerpass1"}).json()["access_token"]
    assert client.post("/broadcasts", headers={"Authorization": f"Bearer {viewer}"}, json={"message": "x"}).status_code == 403
    assert client.get("/broadcasts", headers={"Authorization": f"Bearer {viewer}"}).status_code == 200


# ------------------------------------------------------------------ connection type
def test_connection_type(client, admin):
    assert client.post("/devices", headers=admin, json={"device_id": "CONN-1", "name": "c", "connection_type": "satellite"}).status_code == 422
    r = client.post("/devices", headers=admin, json={"device_id": "CONN-1", "name": "c", "connection_type": "ethernet"})
    assert r.status_code == 201 and r.json()["connection_type"] == "ethernet"
    assert client.put("/devices/CONN-1", headers=admin, json={"connection_type": "wifi"}).json()["connection_type"] == "wifi"
    assert client.get("/devices/CONN-1", headers=admin).json()["connection_type"] == "wifi"


# ------------------------------------------------------------------ predefined cities
def test_city_list_and_search(client, admin):
    cities = client.get("/cities", headers=admin).json()
    assert len(cities) >= 40 and {"id", "name", "state", "center", "source", "vertices", "zone_exists"} <= set(cities[0])
    assert "polygon" not in cities[0]                                     # the list stays light
    assert [c["name"] for c in client.get("/cities?q=chandi", headers=admin).json()] == ["Chandigarh"]
    assert any(c["name"] == "Kochi" for c in client.get("/cities?q=kerala", headers=admin).json())
    assert client.get("/cities?q=zzzz", headers=admin).json() == []
    detail = client.get("/cities/chandigarh", headers=admin).json()
    assert len(detail["polygon"]) >= 8 and all(len(p) == 2 for p in detail["polygon"])
    assert client.get("/cities/atlantis", headers=admin).status_code == 404


def test_create_zone_from_city_and_relocate(client, admin):
    poly = client.get("/cities/chandigarh", headers=admin).json()["polygon"]
    listed = {c["id"]: c for c in client.get("/cities", headers=admin).json()}
    assert listed["chandigarh"]["zone_exists"] is True     # the seed data already contains "Chandigarh Zone"
    assert listed["kochi"]["zone_exists"] is False
    created = []
    try:
        r = client.post("/cities/chandigarh/zone", headers=admin, json={"name": "City test zone", "priority": 30, "color": "#123456"})
        assert r.status_code == 201, r.text
        zone = r.json()
        created.append(zone["id"])
        assert zone["name"] == "City test zone" and zone["priority"] == 30 and zone["color"] == "#123456" and zone["polygon"] == poly
        assert client.post("/cities/chandigarh/zone", headers=admin, json={"name": "City test zone"}).status_code == 409
        assert client.post("/cities/chandigarh/zone", headers=admin, json={}).status_code == 409      # default name is taken by the seed zone
        k = client.post("/cities/kochi/zone", headers=admin, json={})
        assert k.status_code == 201 and k.json()["name"] == "Kochi Zone"
        created.append(k.json()["id"])
        assert {c["id"]: c["zone_exists"] for c in client.get("/cities?q=kochi", headers=admin).json()}["kochi"] is True
    finally:
        for zid in created:                                # never leave test zones behind: other tests count zones
            client.delete(f"/zones/{zid}", headers=admin)
    assert not any(z["id"] in created for z in client.get("/zones", headers=admin).json())


def test_city_zone_requires_admin(client):
    viewer = client.post("/auth/login", json={"username": "viewer1", "password": "viewerpass1"}).json()["access_token"]
    assert client.post("/cities/kochi/zone", headers={"Authorization": f"Bearer {viewer}"}, json={}).status_code == 403


# ------------------------------------------------------------------ discovery of unclaimed agents
SECRET = "s" * 32


@pytest.fixture()
def fresh_discovery():
    from app.services import discovery
    discovery.reset()
    yield discovery
    discovery.reset()


def _announce(client, secret=SECRET, **kw):
    body = {"secret": secret, "name": "Lobby laptop", "latitude": 30.7333, "longitude": 76.7794, "connection_type": "wifi", **kw}
    return client.post("/discovery/announce", json=body)


def test_announce_list_and_filter(client, admin, fresh_discovery):
    assert _announce(client).json() == {"claimed": False}                    # no login needed: the secret is the credential
    _announce(client, secret="t" * 32, name="Mumbai kiosk", latitude=19.076, longitude=72.8777)
    _announce(client, secret="u" * 32, name="No GPS box", latitude=None, longitude=None)
    everything = client.get("/discovery/agents", headers=admin).json()
    assert {a["name"] for a in everything["agents"]} == {"Lobby laptop", "Mumbai kiosk", "No GPS box"}
    lobby = next(a for a in everything["agents"] if a["name"] == "Lobby laptop")
    assert lobby["zones"] == ["Chandigarh Zone"] and len(lobby["id"]) == 16 and "secret" not in lobby   # only a hash is exposed
    zones = {z["name"]: z["id"] for z in client.get("/zones", headers=admin).json()}
    by_zone = client.get(f"/discovery/agents?zone_id={zones['Mumbai Zone']}", headers=admin).json()
    assert by_zone["area"] == "Mumbai Zone" and [a["name"] for a in by_zone["agents"]] == ["Mumbai kiosk"]
    by_city = client.get("/discovery/agents?city_id=chandigarh", headers=admin).json()
    assert [a["name"] for a in by_city["agents"]] == ["Lobby laptop"]         # agents without a location never match an area filter
    assert client.get("/discovery/agents?zone_id=99999", headers=admin).status_code == 404
    assert client.get("/discovery/agents?city_id=atlantis", headers=admin).status_code == 404
    assert client.get("/discovery/agents").status_code == 401


def test_claim_delivers_credentials_to_the_agent_once(client, admin, fresh_discovery):
    _announce(client)
    pid = client.get("/discovery/agents", headers=admin).json()["agents"][0]["id"]
    r = client.post("/devices", headers=admin, json={"device_id": "CLAIM-1", "name": "Claimed", "connection_type": "ethernet", "discovery_id": pid})
    assert r.status_code == 201 and r.json()["claimed_agent"] is True
    assert client.get("/discovery/agents", headers=admin).json()["agents"][0]["id"] == pid        # still listed until it collects
    creds = _announce(client).json()                                        # the agent's next announcement
    assert creds["claimed"] is True and creds["device_id"] == "CLAIM-1"
    assert creds["registration_token"] == r.json()["registration_token"]
    assert _announce(client).json() == {"claimed": False}                   # collected once; it is now just another unknown agent
    reg = client.post("/device/register", json={"device_id": creds["device_id"], "registration_token": creds["registration_token"]})
    assert reg.status_code == 200                                           # the delivered credentials really work
    # someone who only knows the public id cannot collect anything
    other = client.post("/discovery/announce", json={"secret": "x" * 32, "name": "Attacker"}).json()
    assert other == {"claimed": False}


def test_claim_unknown_or_expired_agent_is_rejected(client, admin, fresh_discovery):
    r = client.post("/devices", headers=admin, json={"device_id": "CLAIM-2", "name": "x", "discovery_id": "0123456789abcdef"})
    assert r.status_code == 409
    assert client.get("/devices/CLAIM-2", headers=admin).status_code == 404   # nothing half-created
    _announce(client)
    pid = fresh_discovery.public_id(SECRET)
    fresh_discovery._agents[pid]["last_seen"] -= 1000                        # simulate 1000 s of silence
    assert client.get("/discovery/agents", headers=admin).json()["agents"] == []


def test_announce_is_validated_and_bounded(client, fresh_discovery, monkeypatch):
    assert _announce(client, secret="short").status_code == 422
    assert _announce(client, latitude=123).status_code == 422
    assert _announce(client, connection_type="satellite").status_code == 422
    monkeypatch.setattr(fresh_discovery, "MAX_AGENTS", 2)
    assert _announce(client, secret="a" * 32).status_code == 200
    assert _announce(client, secret="b" * 32).status_code == 200
    assert _announce(client, secret="c" * 32).status_code == 429            # unauthenticated endpoint: memory is capped
    assert _announce(client, secret="a" * 32).status_code == 200            # an already-known agent can still refresh itself
