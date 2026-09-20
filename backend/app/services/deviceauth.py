"""Device identity keys: every request from a display that has a bound Ed25519 key must be signed.

Signed string:  METHOD \\n PATH[?QUERY] \\n TIMESTAMP \\n NONCE \\n SHA256(body)
Headers:        X-Signature (base64), X-Timestamp (unix seconds), X-Nonce (random)

A copied token or .env is useless without the private key. The timestamp window plus a nonce cache stop a recorded request
from being replayed.
"""
import base64
import hashlib
import threading
import time
from dataclasses import dataclass

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

MAX_SKEW = 120        # seconds either side of server time
NONCE_TTL = 300
MAX_NONCES = 50000

_lock = threading.Lock()
_nonces: dict[tuple[str, str], float] = {}
_failures: dict[str, list[float]] = {}


class SignatureError(Exception):
    def __init__(self, reason: str, kind: str = "bad_signature"):
        super().__init__(reason)
        self.reason, self.kind = reason, kind


@dataclass
class SigInfo:
    signature: str | None
    timestamp: str | None
    nonce: str | None
    method: str
    target: str        # path plus query, as the backend sees it
    body_sha256: str

    @property
    def present(self) -> bool:
        return bool(self.signature and self.timestamp and self.nonce)


def canonical(method: str, target: str, timestamp: str, nonce: str, body_sha256: str) -> bytes:
    return f"{method.upper()}\n{target}\n{timestamp}\n{nonce}\n{body_sha256}".encode()


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def public_key_from_b64(value: str) -> Ed25519PublicKey:
    raw = base64.b64decode(value, validate=True)
    if len(raw) != 32:
        raise ValueError("an Ed25519 public key is 32 bytes")
    return Ed25519PublicKey.from_public_bytes(raw)


def check_fresh(device_id: str, timestamp: str, nonce: str, now: float | None = None) -> None:
    now = now or time.time()
    try:
        ts = float(timestamp)
    except ValueError:
        raise SignatureError("bad timestamp")
    if abs(now - ts) > MAX_SKEW:
        raise SignatureError("timestamp outside the allowed window (clock skew or old request)", "clock_skew")
    if not (8 <= len(nonce) <= 64):
        raise SignatureError("bad nonce")
    with _lock:
        if len(_nonces) > MAX_NONCES or (_nonces and len(_nonces) % 500 == 0):
            for k in [k for k, exp in _nonces.items() if exp < now]:
                del _nonces[k]
        if (device_id, nonce) in _nonces:
            raise SignatureError("nonce already used (replayed request)", "replay")
        _nonces[(device_id, nonce)] = now + NONCE_TTL


def verify(public_key_b64: str, message: bytes, signature_b64: str) -> bool:
    try:
        public_key_from_b64(public_key_b64).verify(base64.b64decode(signature_b64, validate=True), message)
        return True
    except (InvalidSignature, ValueError):
        return False


def verify_request(device_id: str, public_key_b64: str, sig: SigInfo) -> None:
    if not sig.present:
        raise SignatureError("this device must sign its requests", "unsigned_request")
    check_fresh(device_id, sig.timestamp, sig.nonce)
    if not verify(public_key_b64, canonical(sig.method, sig.target, sig.timestamp, sig.nonce, sig.body_sha256), sig.signature):
        raise SignatureError("signature does not match")


def note_failure(device_id: str, now: float | None = None) -> int:
    """Count recent failures for a device so repeated attempts (not one clock hiccup) raise a tamper event."""
    now = now or time.time()
    with _lock:
        recent = [t for t in _failures.get(device_id, []) if now - t < 300] + [now]
        _failures[device_id] = recent
        return len(recent)


def reset() -> None:  # for tests
    with _lock:
        _nonces.clear()
        _failures.clear()
