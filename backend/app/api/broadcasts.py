"""Live broadcasting: announcements pushed instantly to displays as a ticker, banner or fullscreen message."""
from datetime import timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Broadcast, DeviceGroup, Zone, utcnow
from ..realtime import notify_admins, notify_devices
from ..schemas import BroadcastIn
from ..scope import Scope, get_scope, get_scoped, get_scoped_device, scoped, write_scope
from ..services.broadcasts import is_active, remaining_seconds

router = APIRouter(prefix="/broadcasts", tags=["broadcasts"])


def _out(b: Broadcast, now) -> dict:
    return {
        "id": b.id, "client_id": b.client_id, "message": b.message, "style": b.style, "severity": b.severity,
        "zone_id": b.zone_id, "zone_name": b.zone.name if b.zone else None,
        "group_id": b.group_id, "group_name": b.group.name if b.group else None, "device_id": b.device_id,
        "created_by": b.created_by, "created_at": b.created_at, "expires_at": b.expires_at, "ended_at": b.ended_at,
        "active": is_active(b, now), "remaining_seconds": remaining_seconds(b, now),
    }


def _changed(client_id: int | None) -> None:
    notify_admins("broadcasts_changed", client_id)
    notify_devices(None, "broadcast", client_id)


@router.get("")
def list_broadcasts(state: str = "all", limit: int = 30, db: Session = Depends(get_db), scope: Scope = Depends(get_scope)):
    now = utcnow()
    rows = scoped(db.query(Broadcast), Broadcast, scope).order_by(Broadcast.id.desc()).limit(min(limit, 200)).all()
    out = [_out(b, now) for b in rows]
    return [b for b in out if b["active"]] if state == "active" else out


@router.post("", status_code=201)
def create_broadcast(body: BroadcastIn, db: Session = Depends(get_db), scope: Scope = Depends(write_scope)):
    if body.zone_id is not None:
        get_scoped(db, Zone, body.zone_id, scope, "Zone")
    if body.group_id is not None:
        get_scoped(db, DeviceGroup, body.group_id, scope, "Group")
    if body.device_id:
        get_scoped_device(db, body.device_id, scope)
    now = utcnow()
    b = Broadcast(
        client_id=scope.client_id, message=body.message.strip(), style=body.style, severity=body.severity, zone_id=body.zone_id,
        group_id=body.group_id, device_id=body.device_id or None, created_by=scope.user.username,
        expires_at=now + timedelta(seconds=body.duration_seconds) if body.duration_seconds else None,
    )
    db.add(b)
    db.commit()
    db.refresh(b)
    _changed(scope.client_id)
    return _out(b, now)


@router.delete("/{broadcast_id}")
def end_broadcast(broadcast_id: int, db: Session = Depends(get_db), scope: Scope = Depends(write_scope)):
    b = get_scoped(db, Broadcast, broadcast_id, scope, "Broadcast")
    if b.ended_at is None:
        b.ended_at = utcnow()
        db.commit()
        _changed(scope.client_id)
    return {"ok": True}


@router.delete("")
def end_all(db: Session = Depends(get_db), scope: Scope = Depends(write_scope)):
    ended = (db.query(Broadcast).filter(Broadcast.ended_at.is_(None), Broadcast.client_id == scope.client_id)
             .update({Broadcast.ended_at: utcnow()}))
    db.commit()
    _changed(scope.client_id)
    return {"ok": True, "ended": ended}
