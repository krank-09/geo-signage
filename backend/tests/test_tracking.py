"""Route-based targeting, location history and zone visits, remote screenshots."""
import io

import pytest
from PIL import Image

from app.services.geo import route_position

CHD, DEL, JAI, MUM = (30.7333, 76.7794), (28.6139, 77.2090), (26.9124, 75.7873), (19.0760, 72.8777)
WP = [{"name": n, "lat": p[0], "lng": p[1]} for n, p in (("Chandigarh", CHD), ("Delhi", DEL), ("Jaipur", JAI), ("Mumbai", MUM))]


def jpeg(color=(200, 30, 30)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 36), color).save(buf, "JPEG")
    return buf.getvalue()


def png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (16, 16), (0, 0, 0)).save(buf, "PNG")
    return buf.getvalue()


def test_route_position_geometry():
    assert route_position(WP, *CHD)["leg"] == 0 and route_position(WP, *CHD)["progress"] < 1
    mid = route_position(WP, (CHD[0] + DEL[0]) / 2, (CHD[1] + DEL[1]) / 2)
    assert mid["leg"] == 0 and mid["offset_km"] < 2 and mid["next_stop"] == "Delhi"
    assert route_position(WP, 27.7, 76.4)["leg"] == 1
    end = route_position(WP, *MUM)
    assert end["leg"] == 2 and end["progress"] > 99
    far = route_position(WP, 22.0, 88.0)                                    # Kolkata: nowhere near the path
    assert far["offset_km"] > 500
    assert route_position(WP[:1], 0, 0) is None


@pytest.fixture(scope="module")
def setup(client, admin):
    """A route, two content items and a display that is moved around."""
    r = client.post("/routes", headers=admin, json={"name": "Test run", "waypoints": WP, "corridor_km": 40})
    assert r.status_code == 201, r.text
    route = r.json()
    png_bytes = b"\x89PNG\r\n\x1a\n" + b"0" * 64
    c1 = client.post("/content/upload", headers=admin, files={"file": ("a.png", png_bytes, "image/png")}, data={"name": "Leg one ad", "duration": "5"}).json()
    c2 = client.post("/content/upload", headers=admin, files={"file": ("b.png", png_bytes, "image/png")}, data={"name": "Route wide ad", "duration": "5"}).json()
    d = client.post("/devices", headers=admin, json={"device_id": "RT-1", "name": "Route van", "connection_type": "wifi"}).json()
    tok = client.post("/device/register", json={"device_id": "RT-1", "registration_token": d["registration_token"]}).json()["access_token"]
    dh = {"Authorization": f"Bearer {tok}"}
    assert client.put("/devices/RT-1", headers=admin, json={"route_id": route["id"]}).status_code == 200
    a1 = client.post("/assignments", headers=admin, json={"content_id": c1["id"], "route_id": route["id"], "route_leg": 0, "priority": 50}).json()
    a2 = client.post("/assignments", headers=admin, json={"content_id": c2["id"], "route_id": route["id"], "priority": 40}).json()
    yield {"route": route, "dh": dh, "c1": c1, "c2": c2, "a1": a1, "a2": a2}


def playing(client, dh):
    return [i["name"] for i in client.get("/device/RT-1/content", headers=dh).json()["items"]]


def at(client, dh, p):
    r = client.post("/device/location", headers=dh, json={"latitude": p[0], "longitude": p[1]})
    assert r.status_code == 200, r.text
    return r.json()


def test_content_follows_the_leg(client, admin, setup):
    dh = setup["dh"]
    at(client, dh, (29.7, 77.0))                                            # between Chandigarh and Delhi: leg 0
    assert playing(client, dh) == ["Leg one ad"]
    at(client, dh, (27.7, 76.4))                                            # between Delhi and Jaipur: leg 1, only the route-wide ad applies
    assert playing(client, dh) == ["Route wide ad"]
    dev = client.get("/devices/RT-1", headers=admin).json()
    assert dev["route"]["leg"] == 1 and dev["route"]["leg_label"] == "Delhi → Jaipur" and 0 < dev["route"]["progress"] < 100


def test_leaving_the_corridor_raises_and_clears_an_alert(client, admin, setup):
    dh = setup["dh"]
    at(client, dh, (22.0, 88.0))
    dev = client.get("/devices/RT-1", headers=admin).json()
    assert dev["route"]["off_route"] is True
    alerts = client.get("/alerts", headers=admin).json()
    alerts = alerts["alerts"] if isinstance(alerts, dict) else alerts
    assert any(a["kind"] == "off_route" and a["device_id"] == "RT-1" for a in alerts)
    at(client, dh, (29.7, 77.0))
    assert client.get("/devices/RT-1", headers=admin).json()["route"]["off_route"] is False
    alerts = client.get("/alerts?state=open", headers=admin).json()
    alerts = alerts["alerts"] if isinstance(alerts, dict) else alerts
    assert not any(a["kind"] == "off_route" and a["device_id"] == "RT-1" for a in alerts)


def test_route_validation_and_ownership(client, admin, setup):
    rid = setup["route"]["id"]
    assert client.post("/assignments", headers=admin, json={"content_id": setup["c1"]["id"], "route_leg": 1}).status_code == 400          # leg without route
    assert client.post("/assignments", headers=admin, json={"content_id": setup["c1"]["id"], "route_id": rid, "route_leg": 9}).status_code == 400
    assert client.post("/assignments", headers=admin, json={"content_id": setup["c1"]["id"], "route_id": 99999}).status_code == 400
    assert client.post("/routes", headers=admin, json={"name": "Test run", "waypoints": WP}).status_code == 409
    assert client.post("/routes", headers=admin, json={"name": "One point", "waypoints": WP[:1]}).status_code == 422
    last = client.post("/assignments", headers=admin, json={"content_id": setup["c1"]["id"], "route_id": rid, "route_leg": 2}).json()
    short = client.put(f"/routes/{rid}", headers=admin, json={"name": "Test run", "waypoints": WP[:3]})
    assert short.status_code == 409                                                                                                      # would orphan the leg-3 assignment
    client.delete(f"/assignments/{last['id']}", headers=admin)
    assert client.put(f"/routes/{rid}", headers=admin, json={"name": "Test run", "waypoints": WP, "corridor_km": 40}).status_code == 200


def test_history_and_zone_visits(client, admin, setup):
    dh = setup["dh"]
    for p in ((30.7333, 76.7794), (28.6139, 77.2090), (30.7333, 76.7794), (28.6139, 77.2090)):    # Chandigarh, Delhi, Chandigarh, Delhi
        at(client, dh, p)
    pts = client.get("/devices/RT-1/track?hours=1", headers=admin).json()
    assert len(pts) >= 4 and pts == sorted(pts, key=lambda p: p["ts"])
    visits = {v["zone_name"]: v for v in client.get("/monitoring/zone-visits?hours=1", headers=admin).json()}
    assert visits["Delhi Zone"]["visits"] >= 2 and visits["Chandigarh Zone"]["visits"] >= 1
    at(client, dh, (28.6139, 77.2090))                                                            # parked: nothing new is stored
    assert len(client.get("/devices/RT-1/track?hours=1", headers=admin).json()) == len(pts)


def test_screenshot_upload_fetch_and_limits(client, admin, setup):
    dh = setup["dh"]
    assert client.get("/devices/RT-1/screenshot", headers=admin).status_code == 404
    from app.services import deviceauth
    deviceauth.reset()
    r = client.post("/device/screenshot", headers={**dh, "Content-Type": "image/jpeg"}, content=jpeg())
    assert r.status_code == 200, r.text
    got = client.get("/devices/RT-1/screenshot", headers=admin)
    assert got.status_code == 200 and got.headers["content-type"] == "image/jpeg" and got.content.startswith(b"\xff\xd8\xff")
    assert client.get("/devices/RT-1", headers=admin).json()["screenshot_at"]
    assert client.post("/device/screenshot", headers={**dh, "Content-Type": "image/jpeg"}, content=jpeg()).status_code == 429     # too soon
    assert client.post("/device/screenshot", headers=dh, content=png()).status_code in (400, 429)
    assert client.post("/devices/RT-1/screenshot/request", headers=admin).status_code == 200
    token = admin["Authorization"].split()[1]
    assert client.get(f"/devices/RT-1/screenshot?token={token}").status_code == 200                                                # for <img> tags


def test_screenshot_rejects_non_jpeg_and_oversize(client, setup, monkeypatch):
    from app import config
    dh = setup["dh"]
    from app.database import SessionLocal
    from app.models import Device
    with SessionLocal() as db:                                                                                                     # clear the 3 s limiter
        db.query(Device).filter(Device.device_id == "RT-1").update({Device.screenshot_at: None})
        db.commit()
    assert client.post("/device/screenshot", headers=dh, content=png()).status_code == 400
    monkeypatch.setattr(config, "SCREENSHOT_MAX_KB", 1)
    assert client.post("/device/screenshot", headers=dh, content=jpeg() + b"0" * 2048).status_code == 400


def test_other_clients_cannot_see_routes_history_or_screenshots(client, admin, setup):
    b = client.post("/clients", headers=admin, json={"name": "Route Rivals"}).json()
    client.post("/users", headers=admin, json={"username": "rival_admin", "password": "rivalpass123", "role": "admin", "client_id": b["id"]})
    tok = client.post("/auth/login", json={"username": "rival_admin", "password": "rivalpass123"}).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    try:
        assert client.get("/routes", headers=h).json() == []
        assert client.get(f"/routes/{setup['route']['id']}", headers=h).status_code in (404, 405)
        assert client.put(f"/routes/{setup['route']['id']}", headers=h, json={"name": "xx", "waypoints": WP}).status_code == 404
        assert client.delete(f"/routes/{setup['route']['id']}", headers=h).status_code == 404
        assert client.get("/devices/RT-1/track", headers=h).status_code == 404
        assert client.get("/devices/RT-1/screenshot", headers=h).status_code == 404
        assert client.post("/devices/RT-1/screenshot/request", headers=h).status_code == 404
        assert client.get("/monitoring/zone-visits", headers=h).json() == []
        z = client.post("/zones", headers=h, json={"name": "Z", "polygon": [[1, 1], [1, 2], [2, 2]], "priority": 1}).json()
        assert client.post("/assignments", headers=h, json={"content_id": setup["c1"]["id"], "zone_id": z["id"]}).status_code == 400   # foreign content
        r = client.post("/routes", headers=h, json={"name": "Mine", "waypoints": WP}).json()
        assert client.post("/devices", headers=h, json={"device_id": "RV-1", "name": "v", "connection_type": "wifi"}).status_code == 201
        assert client.put("/devices/RT-1", headers=h, json={"route_id": r["id"]}).status_code == 404                                 # not their device
        assert client.put("/devices/RV-1", headers=h, json={"route_id": setup["route"]["id"]}).status_code == 404                     # not their route
    finally:
        client.delete("/devices/RV-1", headers=h)
        for x in client.get("/routes", headers=h).json():
            client.delete(f"/routes/{x['id']}", headers=h)
        for z in client.get("/zones", headers=h).json():
            client.delete(f"/zones/{z['id']}", headers=h)
        uid = next(u["id"] for u in client.get("/users", headers=admin).json() if u["username"] == "rival_admin")
        client.delete(f"/users/{uid}", headers=admin)
        assert client.delete(f"/clients/{b['id']}", headers=admin).status_code == 200


def test_deleting_a_route_frees_devices_and_removes_its_assignments(client, admin, setup):
    r = client.delete(f"/routes/{setup['route']['id']}", headers=admin)
    assert r.status_code == 200 and r.json()["assignments_removed"] == 2
    dev = client.get("/devices/RT-1", headers=admin).json()
    assert dev["route_id"] is None and dev["route"] is None
    client.delete("/devices/RT-1", headers=admin)
    for c in (setup["c1"], setup["c2"]):
        client.delete(f"/content/{c['id']}", headers=admin)
