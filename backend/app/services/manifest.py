"""Signed playlists. The server signs what each display should play (items with their SHA-256, broadcasts, emergency flag)
with an Ed25519 key. Displays pin the public key at registration and refuse anything else, so a compromised proxy or tunnel
(which terminates TLS) cannot change what plays, and tampered media is caught by its hash."""
import base64
import json
import time

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy.orm import Session

from .. import config
from .settings import get_setting, set_setting

_key_cache: Ed25519PrivateKey | None = None


def _load_key(db: Session) -> Ed25519PrivateKey:
    global _key_cache
    if _key_cache is not None:
        return _key_cache
    seed_b64 = config.SERVER_SIGNING_KEY or get_setting(db, "server_signing_key", "")
    if not seed_b64:
        seed = Ed25519PrivateKey.generate().private_bytes(
            serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
        seed_b64 = base64.b64encode(seed).decode()
        set_setting(db, "server_signing_key", seed_b64)
    _key_cache = Ed25519PrivateKey.from_private_bytes(base64.b64decode(seed_b64))
    return _key_cache


def public_key_b64(db: Session) -> str:
    raw = _load_key(db).public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return base64.b64encode(raw).decode()


def fingerprint(db: Session) -> str:
    import hashlib

    return hashlib.sha256(base64.b64decode(public_key_b64(db))).hexdigest()[:16]


def canonical_json(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sign_manifest(db: Session, payload: dict) -> dict:
    text = canonical_json({**payload, "issued_at": int(time.time())})
    sig = _load_key(db).sign(text.encode())
    return {"alg": "ed25519", "payload": text, "sig": base64.b64encode(sig).decode()}


def reset_cache() -> None:  # for tests
    global _key_cache
    _key_cache = None
