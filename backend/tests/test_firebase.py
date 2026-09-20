"""Firebase sign-in, exercised with tokens we sign ourselves the way Google does (RS256, x509 certificate by kid)."""
import time
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from app import config
from app.services import firebase

PROJECT = "geo-signage-test"


def _keypair(kid_name: str):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, kid_name)])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(days=1))
            .not_valid_after(now + timedelta(days=30)).sign(key, hashes.SHA256()))
    return key, cert.public_bytes(serialization.Encoding.PEM).decode()


GOOD_KEY, GOOD_CERT = _keypair("good")
OTHER_KEY, _ = _keypair("other")


@pytest.fixture(autouse=True)
def configured(monkeypatch):
    monkeypatch.setattr(config, "FIREBASE_PROJECT_ID", PROJECT)
    monkeypatch.setattr(config, "FIREBASE_API_KEY", "web-key")
    monkeypatch.setattr(config, "FIREBASE_AUTH_DOMAIN", f"{PROJECT}.firebaseapp.com")
    monkeypatch.setattr(config, "FIREBASE_APP_ID", "1:123:web:abc")
    monkeypatch.setattr(config, "FIREBASE_ADMIN_EMAILS", {"boss@example.com"})
    monkeypatch.setattr(config, "FIREBASE_AUTH_EMULATOR_HOST", "")
    monkeypatch.setattr(firebase, "_certs", lambda force=False: {"good-kid": GOOD_CERT})


def token(uid="uid-1", email="boss@example.com", verified=True, *, key=GOOD_KEY, kid="good-kid", aud=PROJECT, iss=None,
          exp_in=3600, name="Test Person"):
    now = int(time.time())
    claims = {"sub": uid, "aud": aud, "iss": iss or f"https://securetoken.google.com/{PROJECT}", "iat": now, "exp": now + exp_in,
              "email": email, "email_verified": verified, "name": name}
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": kid})


def exchange(client, tok):
    return client.post("/auth/firebase", json={"id_token": tok})


# ------------------------------------------------------------------ config endpoint
def test_config_exposes_firebase_only_when_enabled(client, monkeypatch):
    cfg = client.get("/auth/config").json()
    assert cfg["local_login"] is True and cfg["firebase"]["projectId"] == PROJECT and cfg["firebase"]["apiKey"] == "web-key"
    monkeypatch.setattr(config, "FIREBASE_PROJECT_ID", "")
    assert client.get("/auth/config").json()["firebase"] is None
    assert exchange(client, token()).status_code == 404


# ------------------------------------------------------------------ token verification rules
@pytest.mark.parametrize("bad", [
    lambda: token(key=OTHER_KEY),                          # signed by someone else
    lambda: token(kid="unknown-kid"),                      # key id Google never published
    lambda: token(aud="another-project"),                  # token for a different Firebase project
    lambda: token(iss="https://evil.example.com/"),        # wrong issuer
    lambda: token(exp_in=-3600),                           # expired
    lambda: "not.a.jwt" + "x" * 30,                        # garbage
])
def test_invalid_tokens_are_rejected(client, bad):
    assert exchange(client, bad()).status_code == 401


def test_unverified_email_is_rejected(client):
    r = exchange(client, token(uid="uid-unverified", email="new@example.com", verified=False))
    assert r.status_code == 403 and "Verify your email" in r.json()["detail"]


# ------------------------------------------------------------------ authorization: allow-list, approval, roles
def test_allow_listed_email_becomes_admin(client):
    r = exchange(client, token(uid="uid-boss", email="boss@example.com"))
    assert r.status_code == 200
    body = r.json()
    assert body["role"] == "admin" and body["username"] == "boss"
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"}).json()
    assert me == {"username": "boss", "role": "admin"}
    assert exchange(client, token(uid="uid-boss", email="boss@example.com")).json()["username"] == "boss"   # same account again


def test_new_person_waits_for_approval_then_gets_the_role_given(client, admin):
    r = exchange(client, token(uid="uid-anna", email="anna@example.com", name="Anna"))
    assert r.status_code == 403 and "approval" in r.json()["detail"]
    users = {u["email"]: u for u in client.get("/users", headers=admin).json()}
    anna = users["anna@example.com"]
    assert anna["role"] == "pending" and anna["source"] == "firebase" and anna["username"] == "anna"
    assert exchange(client, token(uid="uid-anna", email="anna@example.com")).status_code == 403     # still waiting

    assert client.put(f"/users/{anna['id']}/role", headers=admin, json={"role": "viewer"}).json()["role"] == "viewer"
    ok = exchange(client, token(uid="uid-anna", email="anna@example.com"))
    assert ok.status_code == 200 and ok.json()["role"] == "viewer"
    viewer = {"Authorization": f"Bearer {ok.json()['access_token']}"}
    assert client.get("/devices", headers=viewer).status_code == 200
    assert client.post("/zones", headers=viewer, json={"name": "nope", "polygon": [[0, 0], [0, 1], [1, 1]]}).status_code == 403

    # demoting her back to pending locks out the token she already holds, not just future sign-ins
    client.put(f"/users/{anna['id']}/role", headers=admin, json={"role": "pending"})
    assert client.get("/devices", headers=viewer).status_code == 403
    client.delete(f"/users/{anna['id']}", headers=admin)


def test_usernames_are_unique_and_valid(client, admin):
    a = exchange(client, token(uid="uid-c1", email="sam@one.example", verified=True))
    b = exchange(client, token(uid="uid-c2", email="sam@two.example", verified=True))
    assert a.status_code == b.status_code == 403
    names = sorted(u["username"] for u in client.get("/users", headers=admin).json() if u["email"] and u["email"].startswith("sam@"))
    assert names == ["sam", "sam2"]
    for u in client.get("/users", headers=admin).json():
        if u["email"] and u["email"].startswith("sam@"):
            client.delete(f"/users/{u['id']}", headers=admin)
    assert exchange(client, token(uid="uid-x", email="a@x.example")).status_code == 403
    short = [u for u in client.get("/users", headers=admin).json() if u["email"] == "a@x.example"][0]
    assert len(short["username"]) >= 3                       # "a" is padded to a valid username
    client.delete(f"/users/{short['id']}", headers=admin)


def test_firebase_only_accounts_cannot_use_password_login(client):
    exchange(client, token(uid="uid-boss", email="boss@example.com"))
    assert client.post("/auth/login", json={"username": "boss", "password": "!firebase"}).status_code == 401
    assert client.post("/auth/login", json={"username": "boss", "password": ""}).status_code == 401


def test_admin_cannot_change_own_role_and_local_login_still_works(client, admin):
    me = next(u for u in client.get("/users", headers=admin).json() if u["username"] == "admin")
    assert client.put(f"/users/{me['id']}/role", headers=admin, json={"role": "viewer"}).status_code == 400
    assert client.put(f"/users/{me['id']}/role", headers=admin, json={"role": "root"}).status_code == 422
    assert me["source"] == "local"
    assert client.post("/auth/login", json={"username": "admin", "password": "admin123"}).status_code == 200


def test_unknown_key_triggers_one_refetch(client, monkeypatch):
    calls = []

    def certs(force=False):
        calls.append(force)
        return {"good-kid": GOOD_CERT} if force else {}

    monkeypatch.setattr(firebase, "_certs", certs)
    assert exchange(client, token(uid="uid-rot", email="boss@example.com")).status_code == 200
    assert calls == [False, True]                             # stale cache, then a single forced refresh (key rotation)


def test_emulator_mode_accepts_unsigned_tokens_for_the_right_project(client, monkeypatch):
    monkeypatch.setattr(config, "FIREBASE_AUTH_EMULATOR_HOST", "localhost:9099")
    now = int(time.time())
    claims = {"sub": "emu-1", "aud": PROJECT, "iss": f"https://securetoken.google.com/{PROJECT}", "exp": now + 600,
              "email": "boss@example.com", "email_verified": True}
    assert exchange(client, jwt.encode(claims, None, algorithm="none")).status_code == 200
    assert exchange(client, jwt.encode({**claims, "aud": "other"}, None, algorithm="none")).status_code == 401
    monkeypatch.setattr(config, "FIREBASE_AUTH_EMULATOR_HOST", "")
    assert exchange(client, jwt.encode(claims, None, algorithm="none")).status_code == 401       # never accepted in normal mode


def test_same_verified_email_with_a_new_uid_relinks_instead_of_duplicating(client, admin):
    first = exchange(client, token(uid="uid-old", email="boss@example.com"))
    again = exchange(client, token(uid="uid-recreated", email="boss@example.com"))   # deleted and re-created in Firebase
    assert first.status_code == again.status_code == 200 and first.json()["username"] == again.json()["username"] == "boss"
    assert len([u for u in client.get("/users", headers=admin).json() if u["email"] == "boss@example.com"]) == 1
