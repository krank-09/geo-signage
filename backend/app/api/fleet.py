"""Fleet inventory (what OS / agent version each display runs) and the tamper record."""
from collections import Counter

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import config
from ..database import get_db
from ..models import AgentRelease, Device, TamperEvent
from ..schemas import PolicyIn, ReleaseIn
from ..scope import Scope, get_scope, get_scoped_device, platform_admin, scoped, write_scope
from ..security import current_user
from ..services import fleet, manifest, tamper
from ..services.versions import parse

router = APIRouter(tags=["fleet"])


@router.get("/fleet/inventory")
def inventory(db: Session = Depends(get_db), scope: Scope = Depends(get_scope)):
    policy = fleet.get_policy(db, scope.client_id)
    devices = scoped(db.query(Device), Device, scope).order_by(Device.device_id).all()
    rows = [{
        "device_id": d.device_id, "name": d.name, "client_id": d.client_id, "status": d.status,
        "software_version": d.software_version, "os_name": d.os_name, "os_version": d.os_version, "os_arch": d.os_arch,
        "runtime_version": d.runtime_version, "capabilities": d.capabilities or [],
        "compatibility": fleet.device_compat(d, policy), "protection": fleet.protection(d), "tamper_state": d.tamper_state,
    } for d in devices]
    count = lambda key: dict(Counter(r[key] or "unknown" for r in rows))  # noqa: E731
    return {
        "policy": policy, "devices": rows,
        "summary": {"total": len(rows), "by_os": count("os_name"), "by_version": count("software_version"), "by_arch": count("os_arch"),
                    "by_compatibility": count("compatibility"), "by_protection": count("protection"),
                    "tampered": sum(1 for r in rows if r["tamper_state"] == "flagged")},
    }


@router.put("/fleet/policy")
def set_policy(body: PolicyIn, db: Session = Depends(get_db), scope: Scope = Depends(write_scope)):
    for v in (body.recommended_version, body.supported_version):
        if v and parse(v) is None:
            raise HTTPException(400, f"'{v}' is not a version number (use e.g. 1.2.0)")
    return fleet.set_policy(db, scope.client_id, body.recommended_version, body.supported_version)


@router.get("/fleet/releases")
def releases(db: Session = Depends(get_db), _=Depends(current_user)):
    return [{"id": r.id, "version": r.version, "code_hash": r.code_hash, "note": r.note, "created_at": r.created_at}
            for r in db.query(AgentRelease).order_by(AgentRelease.id.desc())]


@router.post("/fleet/releases", status_code=201)
def add_release(body: ReleaseIn, db: Session = Depends(get_db), _=Depends(platform_admin)):
    """Trust a build of the agent. Once any release is listed, a display whose code hash is not listed is flagged."""
    if db.query(AgentRelease).filter(AgentRelease.code_hash == body.code_hash).first():
        raise HTTPException(409, "That code hash is already trusted")
    r = AgentRelease(version=body.version, code_hash=body.code_hash, note=body.note)
    db.add(r)
    db.commit()
    return {"id": r.id, "version": r.version, "code_hash": r.code_hash, "note": r.note}


@router.delete("/fleet/releases/{release_id}")
def remove_release(release_id: int, db: Session = Depends(get_db), _=Depends(platform_admin)):
    r = db.get(AgentRelease, release_id)
    if r is None:
        raise HTTPException(404, "Release not found")
    db.delete(r)
    db.commit()
    return {"ok": True}


# ---- tamper record ----
@router.get("/security/events")
def events(device_id: str | None = None, limit: int = 100, db: Session = Depends(get_db), scope: Scope = Depends(get_scope)):
    q = scoped(db.query(TamperEvent), TamperEvent, scope)
    if device_id:
        get_scoped_device(db, device_id, scope)
        q = q.filter(TamperEvent.device_id == device_id)
    return [tamper.serialize(e) for e in q.order_by(TamperEvent.id.desc()).limit(min(limit, 500))]


@router.get("/security/status")
def security_status(db: Session = Depends(get_db), scope: Scope = Depends(get_scope)):
    devices = scoped(db.query(Device), Device, scope).all()
    return {
        "mode": config.DEVICE_AUTH_MODE,
        "server_key_fingerprint": manifest.fingerprint(db),
        "protected": sum(1 for d in devices if d.public_key), "unprotected": sum(1 for d in devices if not d.public_key),
        "flagged": [d.device_id for d in devices if d.tamper_state == "flagged"],
        "audit": tamper.verify_chain(db, scope.client_id) if scope.client_id is not None else None,
    }


@router.post("/security/audit/verify")
def verify(db: Session = Depends(get_db), scope: Scope = Depends(write_scope)):
    return tamper.verify_chain(db, scope.client_id)


@router.post("/devices/{device_id}/tamper/clear")
def clear(device_id: str, db: Session = Depends(get_db), scope: Scope = Depends(write_scope), user=Depends(current_user)):
    d = get_scoped_device(db, device_id, scope)
    tamper.clear_flag(db, d, user.username)
    return {"ok": True}
