"""Live broadcasting: announcements pushed instantly to displays as a ticker, banner or fullscreen message."""
from datetime import timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Broadcast, DeviceGroup, User, Zone, utcnow
from ..realtime import notify_admins, notify_devices
from ..schemas import BroadcastIn
from ..security import current_user, require_admin
from ..services.broadcasts import is_active, remaining_seconds
from .deps import get_device_or_404, get_or_404

router = APIRouter(prefix="/broadcasts", tags=["broadcasts"])


def _out(b: Broadcast, now) -> dict:
    return {
        "id": b.id, "message": b.message, "style": b.style, "severity": b.severity,
        "zone_id": b.zone_id, "zone_name": b.zone.name if b.zone else None,
        "group_id": b.group_id, "group_name": b.group.name if b.group else None, "device_id": b.device_id,
        "created_by": b.created_by, "created_at": b.created_at, "expires_at": b.expires_at, "ended_at": b.ended_at,
        "active": is_active(b, now), "remaining_seconds": remaining_seconds(b, now),
    }


def _changed() -> None:
    notify_admins("broadcasts_changed")
    notify_devices(None, "broadcast")


@router.get("")
def list_broadcasts(state: str = "all", limit: int = 30, db: Session = Depends(get_db), _: User = Depends(current_user)):
    now = utcnow()
    rows = db.query(Broadcast).order_by(Broadcast.id.desc()).limit(min(limit, 200)).all()
    out = [_out(b, now) for b in rows]
    return [b for b in out if b["active"]] if state == "active" else out


@router.post("", status_code=201)
def create_broadcast(body: BroadcastIn, db: Session = Depends(get_db), me: User = Depends(require_admin)):
    if body.zone_id is not None:
        get_or_404(db, Zone, body.zone_id, "Zone")
    if body.group_id is not None:
        get_or_404(db, DeviceGroup, body.group_id, "Group")
    if body.device_id:
        get_device_or_404(db, body.device_id)
    now = utcnow()
    b = Broadcast(
        message=body.message.strip(), style=body.style, severity=body.severity, zone_id=body.zone_id,
        group_id=body.group_id, device_id=body.device_id or None, created_by=me.username,
        expires_at=now + timedelta(seconds=body.duration_seconds) if body.duration_seconds else None,
    )
    db.add(b)
    db.commit()
    db.refresh(b)
    _changed()
    return _out(b, now)


@router.delete("/{broadcast_id}")
def end_broadcast(broadcast_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    b = get_or_404(db, Broadcast, broadcast_id, "Broadcast")
    if b.ended_at is None:
        b.ended_at = utcnow()
        db.commit()
        _changed()
    return {"ok": True}


@router.delete("")
def end_all(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    now = utcnow()
    ended = db.query(Broadcast).filter(Broadcast.ended_at.is_(None)).update({Broadcast.ended_at: now})
    db.commit()
    _changed()
    return {"ok": True, "ended": ended}
