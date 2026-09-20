"""What each display runs (inventory) and whether its software is what we shipped (integrity)."""
import time

from sqlalchemy.orm import Session

from ..models import AgentRelease, Device
from ..schemas import Inventory
from . import tamper
from .settings import get_setting, set_setting
from .versions import compatibility

RESTART_LOOP = (5, 600)     # this many boots within this many seconds is a loop, not a maintenance restart
POLICY_KEY = "fleet_policy"


def get_policy(db: Session, client_id: int | None) -> dict:
    import json

    for key in (f"{POLICY_KEY}:{client_id}", POLICY_KEY):
        raw = get_setting(db, key, "")
        if raw:
            try:
                return {"recommended_version": None, "supported_version": None, **json.loads(raw)}
            except ValueError:
                pass
    return {"recommended_version": None, "supported_version": None}


def set_policy(db: Session, client_id: int | None, recommended: str | None, supported: str | None) -> dict:
    import json

    policy = {"recommended_version": recommended or None, "supported_version": supported or None}
    set_setting(db, f"{POLICY_KEY}:{client_id}" if client_id is not None else POLICY_KEY, json.dumps(policy))
    return policy


def device_compat(device: Device, policy: dict) -> str:
    return compatibility(device.software_version, policy["recommended_version"], policy["supported_version"])


def apply_inventory(db: Session, device: Device, body: Inventory) -> None:
    """Store what the agent reports and run the code-integrity and restart checks. Caller commits."""
    if body.software_version and body.software_version != device.software_version:
        device.software_version = body.software_version
        device.code_baseline = None          # a real upgrade legitimately changes the code
    for f in ("os_name", "os_version", "os_arch", "runtime_version"):
        v = getattr(body, f)
        if v:
            setattr(device, f, v)
    if body.capabilities is not None:
        device.capabilities = sorted(set(body.capabilities))[:32]
    if body.boot_id and body.boot_id != device.boot_id:
        device.boot_id = body.boot_id
        now = time.time()
        recent = [t for t in (device.restarts or []) if now - t < RESTART_LOOP[1]] + [now]
        device.restarts = recent[-20:]
        if len(recent) >= RESTART_LOOP[0]:
            tamper.record(db, device, "restart_loop", f"{len(recent)} starts in {RESTART_LOOP[1] // 60} minutes", "warning", "server")
    if body.code_hash:
        device.code_hash = body.code_hash
        check_code(db, device)


def check_code(db: Session, device: Device) -> None:
    """Compare the agent's code hash with the trusted release list, or (if none is configured) with the first hash this
    device reported for its version."""
    h = device.code_hash
    if not h:
        return
    if db.query(AgentRelease).count():
        if db.query(AgentRelease).filter(AgentRelease.code_hash == h).first() is None:
            tamper.record(db, device, "code_modified", "Agent code does not match any trusted release", "critical", "server")
        return
    if not device.code_baseline:
        device.code_baseline = h
    elif device.code_baseline != h:
        tamper.record(db, device, "code_modified", "Agent code changed without a version change", "critical", "server")


def protection(device: Device) -> str:
    """protected (bound key) | unprotected (older agent, no key) - shown in the fleet table."""
    return "protected" if device.public_key else "unprotected"
