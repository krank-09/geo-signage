import secrets

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Assignment, Device, DeviceGroup, DeviceLog, Impression, User
from ..realtime import announce_changes, notify_admins, notify_devices
from ..schemas import DeviceIn, DeviceUpdate, GroupIn
from ..security import current_user, hash_secret, require_admin
from ..services import discovery
from ..services.device_service import DEFAULT_CONFIG, add_log, broadcast_device, serialize, update_location
from ..services.resolver import resolve
from .deps import get_device_or_404, get_or_404

router = APIRouter(tags=["devices"])


def _new_reg_token() -> str:
    return "-".join(secrets.token_hex(2).upper() for _ in range(3))


@router.get("/devices")
def list_devices(db: Session = Depends(get_db), _: User = Depends(current_user)):
    return [serialize(d) for d in db.query(Device).order_by(Device.device_id)]


@router.post("/devices", status_code=201)
def create_device(body: DeviceIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    if db.query(Device).filter(Device.device_id == body.device_id).first():
        raise HTTPException(409, "Device ID already exists")
    if body.group_id and not db.get(DeviceGroup, body.group_id):
        raise HTTPException(400, "Unknown group")
    if body.discovery_id and not discovery.is_listed(body.discovery_id):
        raise HTTPException(409, "That display is no longer announcing itself. Refresh the list and pick it again.")
    token = _new_reg_token()
    d = Device(
        device_id=body.device_id, name=body.name, group_id=body.group_id, connection_type=body.connection_type,
        registration_token_hash=hash_secret(token), config=dict(DEFAULT_CONFIG),
    )
    db.add(d)
    db.flush()
    if body.latitude is not None and body.longitude is not None:
        update_location(db, d, body.latitude, body.longitude)
    add_log(db, d.device_id, "register", "Device created by administrator")
    db.commit()
    db.refresh(d)
    broadcast_device(d)
    # A claimed agent collects its credentials itself on its next announcement; nobody has to type the token.
    claimed = bool(body.discovery_id) and discovery.claim(body.discovery_id, d.device_id, token)
    # The registration token is shown exactly once.
    return {**serialize(d), "registration_token": token, "claimed_agent": claimed}


@router.get("/devices/{device_id}")
def get_device(device_id: str, db: Session = Depends(get_db), _: User = Depends(current_user)):
    d = get_device_or_404(db, device_id)
    return {**serialize(d), "resolved": resolve(db, d)}


@router.put("/devices/{device_id}")
def update_device(device_id: str, body: DeviceUpdate, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    d = get_device_or_404(db, device_id)
    if body.name is not None:
        d.name = body.name
    if body.connection_type is not None:
        d.connection_type = body.connection_type
    if body.clear_group:
        d.group_id = None
    elif body.group_id is not None:
        if not db.get(DeviceGroup, body.group_id):
            raise HTTPException(400, "Unknown group")
        d.group_id = body.group_id
    if body.config is not None:
        d.config = body.config.model_dump()
        add_log(db, d.device_id, "config", "Configuration changed remotely")
    db.commit()
    db.refresh(d)
    broadcast_device(d)
    notify_devices(d.device_id, "config")
    return serialize(d)


@router.delete("/devices/{device_id}")
def delete_device(device_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    d = get_device_or_404(db, device_id)
    db.query(DeviceLog).filter(DeviceLog.device_id == device_id).delete()
    db.query(Impression).filter(Impression.device_id == device_id).delete()
    db.delete(d)
    db.commit()
    notify_admins("device_removed", device_id=device_id)
    return {"ok": True}


@router.post("/devices/{device_id}/rotate-token")
def rotate_token(device_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """Revoke every credential the device holds and issue a fresh registration token."""
    d = get_device_or_404(db, device_id)
    token = _new_reg_token()
    d.registration_token_hash = hash_secret(token)
    d.token_version += 1
    d.registered_at = None
    add_log(db, d.device_id, "register", "Credentials revoked; new registration token issued")
    db.commit()
    return {"device_id": d.device_id, "registration_token": token}


@router.post("/devices/{device_id}/sync")
def force_sync(device_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    d = get_device_or_404(db, device_id)
    notify_devices(d.device_id, "manual")
    return {"ok": True}


@router.get("/devices/{device_id}/logs")
def device_logs(device_id: str, limit: int = 50, db: Session = Depends(get_db), _: User = Depends(current_user)):
    rows = (
        db.query(DeviceLog).filter(DeviceLog.device_id == device_id)
        .order_by(DeviceLog.id.desc()).limit(min(limit, 500)).all()
    )
    return [{"id": r.id, "ts": r.ts, "kind": r.kind, "message": r.message, "device_id": r.device_id} for r in rows]


# ---- device groups ----
@router.get("/groups")
def list_groups(db: Session = Depends(get_db), _: User = Depends(current_user)):
    return [
        {"id": g.id, "name": g.name, "device_count": db.query(Device).filter(Device.group_id == g.id).count()}
        for g in db.query(DeviceGroup).order_by(DeviceGroup.name)
    ]


@router.post("/groups", status_code=201)
def create_group(body: GroupIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    if db.query(DeviceGroup).filter(DeviceGroup.name == body.name).first():
        raise HTTPException(409, "Group already exists")
    g = DeviceGroup(name=body.name)
    db.add(g)
    db.commit()
    return {"id": g.id, "name": g.name, "device_count": 0}


@router.delete("/groups/{group_id}")
def delete_group(group_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    g = get_or_404(db, DeviceGroup, group_id, "Group")
    db.query(Assignment).filter(Assignment.group_id == group_id).delete()
    db.query(Device).filter(Device.group_id == group_id).update({Device.group_id: None})
    db.delete(g)
    db.commit()
    announce_changes()
    return {"ok": True}
