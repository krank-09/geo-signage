import secrets

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Assignment, Client, Device, DeviceGroup, DeviceLog, Impression, LocationPoint, Route
from ..realtime import announce_changes, notify_admins, notify_devices
from ..schemas import DeviceIn, DeviceUpdate, GroupIn
from ..scope import Scope, get_scope, get_scoped, get_scoped_device, scoped, write_scope
from ..security import hash_secret
from ..services import discovery
from ..services import routes as route_service
from ..services.device_service import DEFAULT_CONFIG, add_log, broadcast_device, serialize, update_location
from ..services.resolver import resolve
from ..storage import get_storage

router = APIRouter(tags=["devices"])


def _new_reg_token() -> str:
    return "-".join(secrets.token_hex(2).upper() for _ in range(3))


@router.get("/devices")
def list_devices(db: Session = Depends(get_db), scope: Scope = Depends(get_scope)):
    return [serialize(d) for d in scoped(db.query(Device), Device, scope).order_by(Device.device_id)]


@router.post("/devices", status_code=201)
def create_device(body: DeviceIn, db: Session = Depends(get_db), scope: Scope = Depends(write_scope)):
    if db.query(Device).filter(Device.device_id == body.device_id).first():
        raise HTTPException(409, "That Device ID is not available")   # same answer whoever owns it: IDs cannot be probed
    client = db.get(Client, scope.client_id)
    if client.device_limit is not None and db.query(Device).filter(Device.client_id == client.id).count() >= client.device_limit:
        raise HTTPException(409, f"Device limit reached for {client.name} ({client.device_limit})")
    if body.group_id:
        get_scoped(db, DeviceGroup, body.group_id, scope, "Group")
    claim = None
    if body.discovery_id:
        claim = discovery.get(body.discovery_id)
        if claim is None:
            raise HTTPException(409, "That display is no longer announcing itself. Refresh the list and pick it again.")
        if claim.get("client_id") != client.id and not (claim.get("client_id") is None and scope.platform):
            raise HTTPException(409, "That display belongs to a different client")
    token = _new_reg_token()
    d = Device(
        device_id=body.device_id, client_id=client.id, name=body.name, group_id=body.group_id, connection_type=body.connection_type,
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
def get_device(device_id: str, db: Session = Depends(get_db), scope: Scope = Depends(get_scope)):
    d = get_scoped_device(db, device_id, scope)
    return {**serialize(d), "resolved": resolve(db, d)}


@router.put("/devices/{device_id}")
def update_device(device_id: str, body: DeviceUpdate, db: Session = Depends(get_db), scope: Scope = Depends(write_scope)):
    d = get_scoped_device(db, device_id, scope)
    if body.name is not None:
        d.name = body.name
    if body.connection_type is not None:
        d.connection_type = body.connection_type
    if body.clear_group:
        d.group_id = None
    elif body.group_id is not None:
        get_scoped(db, DeviceGroup, body.group_id, scope, "Group")
        d.group_id = body.group_id
    if body.clear_route:
        d.route_id = None
        route_service.track(db, d)
    elif body.route_id is not None:
        get_scoped(db, Route, body.route_id, scope, "Route")
        d.route_id = body.route_id
        d.route_leg = None
        route_service.track(db, d)
    if body.config is not None:
        d.config = body.config.model_dump()
        add_log(db, d.device_id, "config", "Configuration changed remotely")
    db.commit()
    db.refresh(d)
    broadcast_device(d)
    notify_devices(d.device_id, "config")
    return serialize(d)


@router.delete("/devices/{device_id}")
def delete_device(device_id: str, db: Session = Depends(get_db), scope: Scope = Depends(write_scope)):
    d = get_scoped_device(db, device_id, scope)
    client_id = d.client_id
    db.query(DeviceLog).filter(DeviceLog.device_id == device_id).delete()
    db.query(Impression).filter(Impression.device_id == device_id).delete()
    db.query(LocationPoint).filter(LocationPoint.device_id == device_id).delete()
    shot = d.screenshot_key
    db.delete(d)
    db.commit()
    if shot:
        get_storage().delete(shot)
    notify_admins("device_removed", client_id, device_id=device_id)
    return {"ok": True}


@router.post("/devices/{device_id}/rotate-token")
def rotate_token(device_id: str, db: Session = Depends(get_db), scope: Scope = Depends(write_scope)):
    """Revoke every credential the device holds and issue a fresh registration token.
    Also forgets the device's bound key and hardware fingerprint, so a replacement machine can enrol as this device."""
    d = get_scoped_device(db, device_id, scope)
    token = _new_reg_token()
    d.registration_token_hash = hash_secret(token)
    d.token_version += 1
    d.registered_at = None
    d.public_key = d.key_bound_at = d.hw_fingerprint = d.code_baseline = None
    add_log(db, d.device_id, "register", "Credentials revoked; new registration token issued (key binding reset)")
    db.commit()
    return {"device_id": d.device_id, "registration_token": token}


@router.post("/devices/{device_id}/sync")
def force_sync(device_id: str, db: Session = Depends(get_db), scope: Scope = Depends(write_scope)):
    d = get_scoped_device(db, device_id, scope)
    notify_devices(d.device_id, "manual")
    return {"ok": True}


@router.get("/devices/{device_id}/logs")
def device_logs(device_id: str, limit: int = 50, db: Session = Depends(get_db), scope: Scope = Depends(get_scope)):
    get_scoped_device(db, device_id, scope)          # 404 for another client's device
    rows = (
        db.query(DeviceLog).filter(DeviceLog.device_id == device_id)
        .order_by(DeviceLog.id.desc()).limit(min(limit, 500)).all()
    )
    return [{"id": r.id, "ts": r.ts, "kind": r.kind, "message": r.message, "device_id": r.device_id} for r in rows]


# ---- device groups ----
@router.get("/groups")
def list_groups(db: Session = Depends(get_db), scope: Scope = Depends(get_scope)):
    return [
        {"id": g.id, "name": g.name, "client_id": g.client_id, "device_count": db.query(Device).filter(Device.group_id == g.id).count()}
        for g in scoped(db.query(DeviceGroup), DeviceGroup, scope).order_by(DeviceGroup.name)
    ]


@router.post("/groups", status_code=201)
def create_group(body: GroupIn, db: Session = Depends(get_db), scope: Scope = Depends(write_scope)):
    if db.query(DeviceGroup).filter(DeviceGroup.name == body.name, DeviceGroup.client_id == scope.client_id).first():
        raise HTTPException(409, "Group already exists")
    g = DeviceGroup(name=body.name, client_id=scope.client_id)
    db.add(g)
    db.commit()
    return {"id": g.id, "name": g.name, "client_id": g.client_id, "device_count": 0}


@router.delete("/groups/{group_id}")
def delete_group(group_id: int, db: Session = Depends(get_db), scope: Scope = Depends(write_scope)):
    g = get_scoped(db, DeviceGroup, group_id, scope, "Group")
    db.query(Assignment).filter(Assignment.group_id == group_id).delete()
    db.query(Device).filter(Device.group_id == group_id).update({Device.group_id: None})
    db.delete(g)
    db.commit()
    announce_changes("assignments", scope.client_id)
    return {"ok": True}
