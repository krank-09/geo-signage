"""Unclaimed display agents announce themselves here so an admin can claim one while adding a device.

In memory only: entries expire after TTL seconds without an announcement, and a server restart simply makes agents
announce again. An agent proves ownership with a random secret it never shares; the dashboard only ever sees a hash of
it (`id`), so knowing an entry's id does not let anyone collect its credentials.
"""
import hashlib
import threading
import time

TTL = 45              # seconds without an announcement before an agent disappears from the list
CLAIM_TTL = 600       # a claim waits this long for the agent to collect it
MAX_AGENTS = 100      # the announce endpoint is unauthenticated: bound its memory

_lock = threading.Lock()
_agents: dict[str, dict] = {}
_claims: dict[str, dict] = {}


class TooManyAgents(Exception):
    pass


def public_id(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()[:16]


def _prune(now: float) -> None:
    for pid in [p for p, a in _agents.items() if now - a["last_seen"] > TTL]:
        del _agents[pid]
    for pid in [p for p, c in _claims.items() if now - c["at"] > CLAIM_TTL]:
        del _claims[pid]


def announce(secret: str, info: dict) -> dict:
    """Record an agent. Returns {"claimed": False}, or the credentials once an admin has claimed it (collected once)."""
    pid, now = public_id(secret), time.time()
    with _lock:
        _prune(now)
        claim = _claims.pop(pid, None)
        if claim:
            _agents.pop(pid, None)
            return {"claimed": True, "device_id": claim["device_id"], "registration_token": claim["registration_token"]}
        if pid not in _agents and len(_agents) >= MAX_AGENTS:
            raise TooManyAgents
        _agents[pid] = {**info, "id": pid, "last_seen": now}
    return {"claimed": False}


def list_agents() -> list[dict]:
    now = time.time()
    with _lock:
        _prune(now)
        return [{**a, "seconds_ago": round(now - a["last_seen"])} for a in sorted(_agents.values(), key=lambda a: a["name"].lower())]


def is_listed(pid: str) -> bool:
    with _lock:
        _prune(time.time())
        return pid in _agents


def claim(pid: str, device_id: str, registration_token: str) -> bool:
    with _lock:
        _prune(time.time())
        if pid not in _agents:
            return False
        _claims[pid] = {"device_id": device_id, "registration_token": registration_token, "at": time.time()}
        return True


def reset() -> None:  # for tests
    with _lock:
        _agents.clear()
        _claims.clear()
