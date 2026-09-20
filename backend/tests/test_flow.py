import time

from app.services.geo import point_in_polygon
from app.services.resolver import in_window


def test_point_in_polygon():
    sq = [[0, 0], [0, 10], [10, 10], [10, 0]]
    assert point_in_polygon(5, 5, sq)
    assert not point_in_polygon(15, 5, sq)


def test_time_window_wraps_midnight():
    from datetime import datetime, timezone

    # 20:00 UTC == 01:30 IST next day
    now = datetime(2026, 1, 1, 20, 0, tzinfo=timezone.utc)
    assert in_window("22:00", "06:00", now)
    assert not in_window("08:00", "12:00", now)
    assert in_window(None, None, now)


def test_auth_required(client):
    assert client.get("/devices").status_code == 401
    assert client.post("/auth/login", json={"username": "admin", "password": "wrong"}).status_code == 401
    assert client.get("/device/DEV-001/content").status_code == 401


def test_device_token_cannot_call_admin_api(client, device):
    assert client.get("/devices", headers=device).status_code == 401


def test_register_rejects_bad_token(client):
    r = client.post("/device/register", json={"device_id": "DEV-001", "registration_token": "nope"})
    assert r.status_code == 401


def test_geofence_switching(client, admin, device):
    def content_for(lat, lng):
        r = client.post("/device/location", json={"latitude": lat, "longitude": lng}, headers=device)
        assert r.status_code == 200
        c = client.get("/device/DEV-001/content", headers=device).json()
        return r.json(), c

    st, c = content_for(30.7333, 76.7794)  # Chandigarh
    assert st["zone"]["name"] == "Chandigarh Zone"
    assert c["items"][0]["name"] == "Chandigarh Advertisement"
    v_chd = c["manifest_version"]

    st, c = content_for(28.6139, 77.2090)  # Delhi
    assert c["items"][0]["name"] == "Delhi Advertisement"
    assert c["manifest_version"] != v_chd

    st, c = content_for(26.9, 75.8)  # Jaipur, outside all zones -> default
    assert st["zone"] is None
    assert c["items"][0]["name"].startswith("Welcome")

    st, c = content_for(19.0760, 72.8777)  # Mumbai
    assert c["items"][0]["name"] == "Mumbai Advertisement"


def test_media_range_and_auth(client, admin, device):
    c = client.get("/device/DEV-001/content", headers=device).json()["items"][0]
    r = client.get(c["url"], headers={**device, "Range": "bytes=0-7"})
    assert r.status_code == 206 and r.content[:4] == b"\x89PNG"
    assert client.get(c["url"]).status_code == 401
    # other device cannot read via wrong id
    assert client.get(f"/device/DEV-002/media/{c['content_id']}", headers=device).status_code == 403


def test_emergency_override_and_clear(client, admin, device):
    contents = client.get("/content", headers=admin).json()
    alert = next(c for c in contents if c["name"] == "EMERGENCY ALERT")
    r = client.post("/emergency", json={"content_id": alert["id"]}, headers=admin)
    assert r.status_code == 201
    c = client.get("/device/DEV-001/content", headers=device).json()
    assert c["emergency"] and c["items"][0]["name"] == "EMERGENCY ALERT"
    client.delete("/emergency", headers=admin)
    c = client.get("/device/DEV-001/content", headers=device).json()
    assert not c["emergency"]


def test_scheduling_and_priority(client, admin, device):
    contents = {c["name"]: c for c in client.get("/content", headers=admin).json()}
    zones = {z["name"]: z for z in client.get("/zones", headers=admin).json()}
    # Device is in Mumbai. A higher-priority assignment with a window covering "now" wins...
    r = client.post("/assignments", headers=admin, json={
        "content_id": contents["Delhi Advertisement"]["id"], "zone_id": zones["Mumbai Zone"]["id"],
        "priority": 50, "start_time": "00:00", "end_time": "23:59"})
    assert r.status_code == 201
    aid = r.json()["id"]
    c = client.get("/device/DEV-001/content", headers=device).json()
    assert c["items"][0]["name"] == "Delhi Advertisement"
    # ...and an inactive one is ignored.
    client.put(f"/assignments/{aid}", headers=admin, json={
        "content_id": contents["Delhi Advertisement"]["id"], "zone_id": zones["Mumbai Zone"]["id"],
        "priority": 50, "active": False})
    c = client.get("/device/DEV-001/content", headers=device).json()
    assert c["items"][0]["name"] == "Mumbai Advertisement"
    client.delete(f"/assignments/{aid}", headers=admin)


def test_upload_validation(client, admin):
    bad = client.post("/content/upload", headers=admin, files={"file": ("x.exe", b"MZ", "application/octet-stream")})
    assert bad.status_code == 400
    fake = client.post("/content/upload", headers=admin, files={"file": ("x.png", b"not a png at all", "image/png")})
    assert fake.status_code == 400
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 64
    ok = client.post("/content/upload", headers=admin, files={"file": ("y.png", png, "image/png")}, data={"name": "Y", "duration": "5"})
    assert ok.status_code == 201
    cid = ok.json()["id"]
    rep = client.post(f"/content/{cid}/replace", headers=admin, files={"file": ("z.png", png, "image/png")})
    assert rep.json()["version"] == 2
    assert client.delete(f"/content/{cid}", headers=admin).status_code == 200


def test_offline_detection_and_reregister_revokes(client, admin, device):
    client.post("/device/heartbeat", json={"cpu": 10, "memory": 20, "network": "wifi", "gps": True}, headers=device)
    d = client.get("/devices/DEV-001", headers=admin).json()
    assert d["status"] == "online" and d["cpu"] == 10
    time.sleep(3)
    assert client.get("/devices/DEV-001", headers=admin).json()["status"] == "offline"
    # Re-registering rotates credentials and revokes the old token.
    r = client.post("/device/register", json={"device_id": "DEV-001", "registration_token": "DEMO-REG-001"})
    assert r.status_code == 200
    assert client.get("/device/DEV-001/content", headers=device).status_code == 401


def test_viewer_role_is_read_only(client, admin):
    client.post("/users", headers=admin, json={"username": "viewer1", "password": "viewerpass1", "role": "viewer"})
    tok = client.post("/auth/login", json={"username": "viewer1", "password": "viewerpass1"}).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    assert client.get("/devices", headers=h).status_code == 200
    assert client.post("/zones", headers=h, json={"name": "x", "polygon": [[0, 0], [0, 1], [1, 1]]}).status_code == 403


def test_timeline_series(client, admin):
    t = client.get("/monitoring/timeline", headers=admin).json()
    assert len(t["online"]) == 18 and len(t["views"]) == 12
    assert t["devices_total"] >= 3


def test_change_own_password(client, admin):
    client.post("/users", headers=admin, json={"username": "pwuser", "password": "firstpass1", "role": "viewer"})
    tok = client.post("/auth/login", json={"username": "pwuser", "password": "firstpass1"}).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    assert client.post("/users/me/password", headers=h, json={"current_password": "wrong", "new_password": "secondpass2"}).status_code == 400
    assert client.post("/users/me/password", headers=h, json={"current_password": "firstpass1", "new_password": "short"}).status_code == 422
    assert client.post("/users/me/password", headers=h, json={"current_password": "firstpass1", "new_password": "secondpass2"}).status_code == 200
    assert client.post("/auth/login", json={"username": "pwuser", "password": "firstpass1"}).status_code == 401
    assert client.post("/auth/login", json={"username": "pwuser", "password": "secondpass2"}).status_code == 200
