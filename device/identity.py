"""Device identity and integrity: a private key that never leaves the machine, a hardware fingerprint, a code hash,
and the checks that use them. See DOCUMENTATION.md > Security for what this does and does not protect against."""
import base64
import hashlib
import hmac
import json
import os
import platform
import re
import secrets
import subprocess
import sys
import time
import uuid

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

HERE = os.path.dirname(os.path.abspath(__file__))


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode()


class Identity:
    """Ed25519 keypair stored next to the cache (mode 0600). Requests are signed with it, so a copied token or .env
    is not enough to impersonate this display."""

    def __init__(self, root: str):
        os.makedirs(root, exist_ok=True)
        self.path = os.path.join(root, "identity.key")
        self.clock_offset = 0.0     # server time minus local time, learned from responses
        try:
            with open(self.path, encoding="ascii") as f:
                self.key = Ed25519PrivateKey.from_private_bytes(base64.b64decode(f.read().strip()))
        except (FileNotFoundError, ValueError):
            self.key = Ed25519PrivateKey.generate()
            seed = self.key.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="ascii") as f:
                f.write(_b64(seed))
        try:
            os.chmod(self.path, 0o600)      # no-op on Windows, where the profile's ACL applies
        except OSError:
            pass
        self.public_b64 = _b64(self.key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw))
        seed = self.key.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
        self._mac_key = hashlib.sha256(b"geo-signage/state-mac/" + seed).digest()

    # -- request signing ---------------------------------------------------------------------
    def sign_headers(self, method: str, path: str, body: bytes = b"") -> dict:
        ts, nonce = str(int(time.time() + self.clock_offset)), secrets.token_hex(12)
        msg = f"{method.upper()}\n{path}\n{ts}\n{nonce}\n{hashlib.sha256(body).hexdigest()}".encode()
        return {"X-Signature": _b64(self.key.sign(msg)), "X-Timestamp": ts, "X-Nonce": nonce}

    # -- tamper-evident local state ------------------------------------------------------------
    def mac(self, payload: str) -> str:
        return hmac.new(self._mac_key, payload.encode(), hashlib.sha256).hexdigest()

    def mac_ok(self, payload: str, tag: str) -> bool:
        return hmac.compare_digest(self.mac(payload), tag or "")


def verify_manifest(envelope: dict, server_key_b64: str, device_id: str) -> dict:
    """Return the signed payload, or raise ValueError. The payload text is what was signed; nothing outside it is trusted."""
    try:
        Ed25519PublicKey.from_public_bytes(base64.b64decode(server_key_b64)).verify(
            base64.b64decode(envelope["sig"]), envelope["payload"].encode())
        payload = json.loads(envelope["payload"])
    except (InvalidSignature, KeyError, ValueError, TypeError):
        raise ValueError("playlist is not signed by the pinned server key")
    if payload.get("device_id") != device_id:
        raise ValueError("playlist was signed for a different device")
    return payload


def file_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def code_hash() -> str:
    """One hash over the agent's own source files, so a modified agent is noticed."""
    h = hashlib.sha256()
    files = sorted(f for f in os.listdir(HERE) if f.endswith(".py")) + ["display/index.html", "VERSION"]
    for name in files:
        p = os.path.join(HERE, name)
        if os.path.isfile(p):
            h.update(name.encode() + b"\0")
            with open(p, "rb") as f:
                h.update(f.read().replace(b"\r\n", b"\n"))   # same hash whether git checked it out with LF or CRLF
    return h.hexdigest()


def _run(cmd: list[str]) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def machine_id() -> str:
    """A stable per-machine identifier from the operating system; hashed before it leaves the machine."""
    raw = ""
    if sys.platform == "darwin":
        m = re.search(r'"IOPlatformUUID" = "([^"]+)"', _run(["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"]))
        raw = m.group(1) if m else ""
    elif sys.platform.startswith("win"):
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography") as k:
                raw = winreg.QueryValueEx(k, "MachineGuid")[0]
        except OSError:
            raw = ""
    else:
        for p in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
            try:
                with open(p, encoding="ascii") as f:
                    raw = f.read().strip()
                    break
            except OSError:
                continue
    return raw or f"mac-{uuid.getnode():x}"


def hw_fingerprint() -> str:
    return hashlib.sha256(("geo-signage/hw/" + machine_id()).encode()).hexdigest()[:32]


def system_info() -> dict:
    name = {"Darwin": "macOS", "Windows": "Windows", "Linux": "Linux"}.get(platform.system(), platform.system() or "unknown")
    version = platform.mac_ver()[0] if name == "macOS" else platform.release() if name == "Windows" else platform.release()
    if name == "Windows":
        version = f"{platform.release()} ({platform.version()})"
    return {"os_name": name, "os_version": version[:64], "os_arch": (platform.machine() or "unknown").lower()[:24],
            "runtime_version": platform.python_version()}
