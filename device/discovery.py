"""Discovery mode: an agent with no device identity announces itself so an admin can claim it from the dashboard
(Devices > Add device). Once claimed, the server hands this agent its device ID and registration token directly, so
nobody has to type them. The identity is saved and used on every later start."""
import hashlib
import json
import logging
import os
import secrets
import socket
import time

import requests

log = logging.getLogger("agent")
ANNOUNCE_EVERY = 4  # seconds


def load_identity(root: str) -> tuple[str, str] | None:
    try:
        with open(os.path.join(root, "identity.json"), encoding="utf-8") as f:
            data = json.load(f)
        return data["device_id"], data["reg_token"]
    except (FileNotFoundError, KeyError, json.JSONDecodeError):
        return None


def save_identity(root: str, device_id: str, reg_token: str) -> None:
    os.makedirs(root, exist_ok=True)
    with open(os.path.join(root, "identity.json"), "w", encoding="utf-8") as f:
        json.dump({"device_id": device_id, "reg_token": reg_token}, f)


def _secret(root: str) -> str:
    """Random per-installation secret. Stable across restarts so the dashboard keeps showing the same entry."""
    path = os.path.join(root, "discovery_secret")
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        os.makedirs(root, exist_ok=True)
        value = secrets.token_hex(24)
        with open(path, "w", encoding="utf-8") as f:
            f.write(value)
        return value


def display_code(root: str) -> str:
    """Short code shown here and in the dashboard so two similar laptops can be told apart."""
    return hashlib.sha256(_secret(root).encode()).hexdigest()[:6]


def discover(server: str, gps, root: str, version: str, connection_type: str | None = None) -> tuple[str, str]:
    """Announce until an admin claims this display. Blocks; returns (device_id, registration_token)."""
    secret, name = _secret(root), socket.gethostname()[:80] or "display"
    headers = {"ngrok-skip-browser-warning": "1"}
    log.info("No device ID configured: waiting to be claimed. In the dashboard open Devices > Add device and pick "
             "'%s' (code %s).", name, display_code(root))
    last_warn = 0.0
    while True:
        pos = gps.read()
        body = {"secret": secret, "name": name, "software_version": version,
                "latitude": pos[0] if pos else None, "longitude": pos[1] if pos else None,
                "connection_type": connection_type}
        try:
            r = requests.post(server + "/discovery/announce", json=body, headers=headers, timeout=8)
            if r.status_code == 200:
                data = r.json()
                if data.get("claimed"):
                    save_identity(root, data["device_id"], data["registration_token"])
                    log.info("Claimed by the dashboard as %s", data["device_id"])
                    return data["device_id"], data["registration_token"]
            elif time.time() - last_warn > 30:
                last_warn = time.time()
                log.warning("Discovery rejected (%s): %s", r.status_code, r.text[:120])
        except requests.RequestException as e:
            if time.time() - last_warn > 30:
                last_warn = time.time()
                log.warning("Cannot reach the server yet (%s); still trying", e.__class__.__name__)
        time.sleep(ANNOUNCE_EVERY)
