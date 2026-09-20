"""Fleet inventory, device identity keys, signed playlists and the tamper record."""
import base64
import hashlib
import json
import time
import uuid

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.services import deviceauth, manifest


class Display:
    """A test double of the agent's signing behaviour."""

    def __init__(self, client, admin, device_id, **info):
        self.c, self.admin, self.id, self.info = client, admin, device_id, info
        self.key = Ed25519PrivateKey.generate()
        self.pub = base64.b64encode(self.key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode()
        r = client.post("/devices", headers=admin, json={"device_id": device_id, "name": device_id, "connection_type": "wifi"})
        assert r.status_code == 201, r.text
        self.reg_token = r.json()["registration_token"]
        self.token = None

    def headers(self, method, path, body=b"", key=None, nonce=None, ts=None):
        ts, nonce = str(ts or int(time.time())), nonce or uuid.uuid4().hex
        msg = deviceauth.canonical(method, path, ts, nonce, hashlib.sha256(body).hexdigest())
        sig = base64.b64encode((key or self.key).sign(msg)).decode()
        h = {"X-Signature": sig, "X-Timestamp": ts, "X-Nonce": nonce, "Content-Type": "application/json"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    def register(self, pub=None, sign=True, **extra):
        body = json.dumps({"device_id": self.id, "registration_token": self.reg_token, "public_key": pub or self.pub, **self.info, **extra}).encode()
        h = self.headers("POST", "/device/register", body) if sign else {"Content-Type": "application/json"}
        return self.c.post("/device/register", content=body, headers=h)

    def call(self, method, path, payload=None, **kw):
        body = json.dumps(payload).encode() if payload is not None else b""
        return self.c.request(method, path, content=body, headers=self.headers(method, path, body, **kw))


@pytest.fixture()
def fresh(client, admin):
    deviceauth.reset()

    def make(name, **info):
        d = Display(client, admin, name, **info)
        r = d.register()
        assert r.status_code == 200, r.text
        d.token = r.json()["access_token"]
        return d
    return make


def events(client, admin, device_id):
    return [e["kind"] for e in client.get(f"/security/events?device_id={device_id}", headers=admin).json()]


def test_registration_binds_key_and_inventory(client, admin, fresh):
    d = fresh("TP-1", software_version="1.2.0", os_name="macOS", os_version="15.1", os_arch="arm64", capabilities=["gps", "signed"])
    got = client.get("/devices/TP-1", headers=admin).json()
    assert got["protection"] == "protected" and got["os_name"] == "macOS" and got["os_arch"] == "arm64" and "gps" in got["capabilities"]
    assert d.call("POST", "/device/heartbeat", {"cpu": 5}).status_code == 200


def test_signed_requests_are_required_once_bound(client, admin, fresh):
    d = fresh("TP-2")
    assert client.post("/device/heartbeat", json={}, headers={"Authorization": f"Bearer {d.token}"}).status_code == 401
    assert "unsigned_downgrade" in events(client, admin, "TP-2")
    assert client.get("/devices/TP-2", headers=admin).json()["tamper_state"] == "flagged"


def test_stolen_token_with_wrong_key_is_rejected_and_flagged(client, admin, fresh):
    d = fresh("TP-3")
    thief = Ed25519PrivateKey.generate()
    assert d.call("POST", "/device/heartbeat", {}, key=thief).status_code == 401
    assert "bad_signature" in events(client, admin, "TP-3")


def test_replayed_request_is_rejected(client, admin, fresh):
    d = fresh("TP-4")
    assert d.call("POST", "/device/heartbeat", {}, nonce="n" * 16).status_code == 200
    assert d.call("POST", "/device/heartbeat", {}, nonce="n" * 16).status_code == 401
    assert "replayed_request" in events(client, admin, "TP-4")


def test_body_or_path_change_breaks_signature(client, admin, fresh):
    d = fresh("TP-5")
    body = json.dumps({"cpu": 1}).encode()
    h = d.headers("POST", "/device/heartbeat", body)
    assert client.post("/device/heartbeat", content=json.dumps({"cpu": 99}).encode(), headers=h).status_code == 401


def test_old_timestamp_is_only_a_warning(client, admin, fresh):
    d = fresh("TP-6")
    assert d.call("POST", "/device/heartbeat", {}, ts=int(time.time()) - 3600).status_code == 401
    assert client.get("/devices/TP-6", headers=admin).json()["tamper_state"] is None      # clock skew is not proof of tampering
    assert "system_clock_wrong" in events(client, admin, "TP-6")


def test_clone_with_copied_credentials_and_new_key_is_refused(client, admin, fresh):
    d = fresh("TP-7")
    other = Ed25519PrivateKey.generate()
    pub = base64.b64encode(other.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode()
    body = json.dumps({"device_id": "TP-7", "registration_token": d.reg_token, "public_key": pub}).encode()
    r = client.post("/device/register", content=body, headers=d.headers("POST", "/device/register", body, key=other))
    assert r.status_code == 409
    assert "clone_attempt" in events(client, admin, "TP-7")
    # the original display keeps working
    assert d.call("POST", "/device/heartbeat", {}).status_code == 200


def test_registration_must_prove_possession_of_the_key(client, admin, fresh):
    d = Display(client, admin, "TP-8")
    assert d.register(sign=False).status_code == 400


def test_unsigned_registration_of_bound_device_is_refused(client, admin, fresh):
    d = fresh("TP-9")
    r = client.post("/device/register", json={"device_id": "TP-9", "registration_token": d.reg_token})
    assert r.status_code == 409 and "unsigned_downgrade" in events(client, admin, "TP-9")


def test_hardware_fingerprint_change_is_flagged(client, admin, fresh):
    d = fresh("TP-10", )
    assert d.register(hw_fingerprint="a" * 32).status_code == 200
    assert d.register(hw_fingerprint="b" * 32).status_code == 200
    assert "hw_fingerprint_changed" in events(client, admin, "TP-10")


def test_rotate_token_lets_a_replacement_machine_bind(client, admin, fresh):
    fresh("TP-11")
    new = client.post("/devices/TP-11/rotate-token", headers=admin).json()["registration_token"]
    d2 = Display(client, admin, "TP-11-b")
    d2.id, d2.reg_token = "TP-11", new
    assert d2.register().status_code == 200
    assert client.get("/devices/TP-11", headers=admin).json()["protection"] == "protected"


def test_legacy_unsigned_display_still_works_in_optional_mode(client, admin):
    r = client.post("/devices", headers=admin, json={"device_id": "OLD-1", "name": "old", "connection_type": "wifi"})
    tok = client.post("/device/register", json={"device_id": "OLD-1", "registration_token": r.json()["registration_token"], "software_version": "0.9.0"}).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    assert client.post("/device/heartbeat", headers=h, json={"cpu": 3}).status_code == 200
    assert client.get("/device/OLD-1/content", headers=h).status_code == 200
    assert client.get("/devices/OLD-1", headers=admin).json()["protection"] == "unprotected"


def test_required_mode_refuses_unsigned_displays(client, admin, monkeypatch):
    from app import config
    r = client.post("/devices", headers=admin, json={"device_id": "OLD-2", "name": "old", "connection_type": "wifi"})
    tok = client.post("/device/register", json={"device_id": "OLD-2", "registration_token": r.json()["registration_token"]}).json()["access_token"]
    monkeypatch.setattr(config, "DEVICE_AUTH_MODE", "required")
    assert client.post("/device/heartbeat", headers={"Authorization": f"Bearer {tok}"}, json={}).status_code == 401


def test_manifest_is_signed_and_carries_hashes(client, admin, fresh, device):
    d = fresh("TP-12")
    r = d.call("GET", "/device/TP-12/content")
    assert r.status_code == 200
    env = r.json()["signed"]
    pub = client.post("/device/register", json={"device_id": "TP-12", "registration_token": d.reg_token}) # unsigned -> refused
    assert pub.status_code == 409
    key = deviceauth.public_key_from_b64(_server_key(client, d))
    key.verify(base64.b64decode(env["sig"]), env["payload"].encode())
    payload = json.loads(env["payload"])
    assert payload["device_id"] == "TP-12" and "issued_at" in payload
    for item in payload["items"]:
        assert len(item["sha256"]) == 64
    tampered = env["payload"].replace("TP-12", "TP-99")
    with pytest.raises(Exception):
        key.verify(base64.b64decode(env["sig"]), tampered.encode())


def _server_key(client, d):
    body = json.dumps({"device_id": d.id, "registration_token": d.reg_token, "public_key": d.pub}).encode()
    return client.post("/device/register", content=body, headers=d.headers("POST", "/device/register", body)).json()["server_public_key"]


def test_device_reports_tamper_and_admin_clears_flag(client, admin, fresh):
    d = fresh("TP-13")
    r = d.call("POST", "/device/tamper", {"events": [{"kind": "cache_tampered", "detail": "ad.png hash mismatch"}]})
    assert r.status_code == 200 and r.json()["recorded"] == 1
    assert client.get("/devices/TP-13", headers=admin).json()["tamper_state"] == "flagged"
    alerts = client.get("/alerts", headers=admin).json()
    assert any(a["kind"] == "tamper" and a["device_id"] == "TP-13" for a in (alerts["alerts"] if isinstance(alerts, dict) else alerts))
    assert d.call("POST", "/device/heartbeat", {}).status_code == 200            # flag only: the display keeps working
    assert client.post("/devices/TP-13/tamper/clear", headers=admin).status_code == 200
    assert client.get("/devices/TP-13", headers=admin).json()["tamper_state"] is None
    assert "cache_tampered" in events(client, admin, "TP-13")                     # history stays


def test_audit_chain_detects_edits(client, admin, fresh):
    from app.database import SessionLocal
    from app.models import TamperEvent
    d = fresh("TP-14")
    d.call("POST", "/device/tamper", {"events": [{"kind": "clock_rollback", "detail": "x"}]})
    assert client.post("/security/audit/verify", headers=admin).json()["ok"] is True
    with SessionLocal() as db:
        e = db.query(TamperEvent).filter(TamperEvent.device_id == "TP-14").first()
        e.detail = "nothing to see here"
        db.commit()
    res = client.post("/security/audit/verify", headers=admin).json()
    assert res["ok"] is False and res["broken_at"] is not None
    with SessionLocal() as db:                      # restore so later tests see a valid chain
        e = db.query(TamperEvent).filter(TamperEvent.device_id == "TP-14").first()
        e.detail = "x"
        db.commit()


def test_code_baseline_and_trusted_releases(client, admin, fresh):
    d = fresh("TP-15", software_version="1.2.0", code_hash="a" * 64)
    assert d.call("POST", "/device/heartbeat", {"code_hash": "a" * 64}).status_code == 200
    assert client.get("/devices/TP-15", headers=admin).json()["tamper_state"] is None
    d.call("POST", "/device/heartbeat", {"code_hash": "b" * 64})
    assert "code_modified" in events(client, admin, "TP-15")
    # trusted list takes over once any release exists
    rel = client.post("/fleet/releases", headers=admin, json={"version": "1.2.0", "code_hash": "c" * 64, "note": "test"})
    assert rel.status_code == 201
    d2 = fresh("TP-16", software_version="1.2.0", code_hash="c" * 64)
    assert client.get("/devices/TP-16", headers=admin).json()["tamper_state"] is None
    d3 = fresh("TP-17", software_version="1.2.0", code_hash="d" * 64)
    assert "code_modified" in events(client, admin, "TP-17")
    assert d2 and d3
    client.delete(f"/fleet/releases/{rel.json()['id']}", headers=admin)


def test_fleet_inventory_and_policy(client, admin, fresh):
    fresh("FL-1", software_version="1.0.0", os_name="Windows", os_arch="x86_64")
    fresh("FL-2", software_version="1.2.0", os_name="Linux", os_arch="aarch64")
    assert client.put("/fleet/policy", headers=admin, json={"recommended_version": "1.2.0", "supported_version": "1.1.0"}).status_code == 200
    inv = client.get("/fleet/inventory", headers=admin).json()
    by = {r["device_id"]: r for r in inv["devices"]}
    assert by["FL-1"]["compatibility"] == "unsupported" and by["FL-2"]["compatibility"] == "ok"
    assert inv["summary"]["by_os"]["Windows"] >= 1 and inv["summary"]["by_arch"]["aarch64"] >= 1
    assert client.put("/fleet/policy", headers=admin, json={"recommended_version": "banana"}).status_code == 400
    client.put("/fleet/policy", headers=admin, json={})


def test_version_compare():
    from app.services.versions import compare, compatibility, parse
    assert parse("1.2") == (1, 2, 0) and parse("1.2.3-rc1") == (1, 2, 3) and parse("x") is None
    assert compare("1.10.0", "1.2.0") == 1 and compare("1.2.0", "1.2.0") == 0
    assert compatibility(None, "1.0.0", None) == "unknown" and compatibility("0.9", "1.0", "0.5") == "outdated"


def test_server_signing_key_is_stable(client):
    from app.database import SessionLocal
    with SessionLocal() as db:
        assert manifest.public_key_b64(db) == manifest.public_key_b64(db)
