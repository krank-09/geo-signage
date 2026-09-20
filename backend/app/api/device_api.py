"""Endpoints called by device agents (device-token auth)."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .. import config
from ..database import get_db
from ..models import Content, Device, Impression, Zone, utcnow
from ..schemas import HeartbeatIn, ImpressionsIn, LocationIn, RegisterIn
from ..security import create_device_token, current_device, verify_secret
from ..services.device_service import add_log, broadcast_device, effective_config, touch, update_location
from ..services.media import stream_content
from ..services.resolver import resolve
from .deps import get_or_404

router = APIRouter(prefix="/device", tags=["device"])


def _own(device: Device, device_id: str) -> Device:
    if device.device_id != device_id:
        raise HTTPException(403, "Token does not belong to this device")
    return device


def _sync_state(db: Session, device: Device, zones: list[Zone] | None = None) -> dict:
    r = resolve(db, device, zones=zones)
    return {
        "ok": True,
        "server_time": datetime.now(timezone.utc).isoformat(),
        "manifest_version": r["manifest_version"],
        "zone": r["zone"],
        "config": effective_config(device),
    }


@router.post("/register")
def register(body: RegisterIn, db: Session = Depends(get_db)):
    device = db.query(Device).filter(Device.device_id == body.device_id).first()
    # Same error for unknown device / bad token so IDs cannot be enumerated.
    if not device or not verify_secret(body.registration_token, device.registration_token_hash):
        raise HTTPException(401, "Invalid device ID or registration token")
    device.registered_at = utcnow()
    device.token_version += 1  # a re-registration invalidates older credentials
    if body.software_version:
        device.software_version = body.software_version
    touch(db, device)
    add_log(db, device.device_id, "register", "Device registered")
    db.commit()
    broadcast_device(device)
    return {"access_token": create_device_token(device), "token_type": "bearer", "device_id": device.device_id,
            "config": effective_config(device)}


@router.post("/heartbeat")
def heartbeat(body: HeartbeatIn, db: Session = Depends(get_db), device: Device = Depends(current_device)):
    touch(db, device)
    for field in ("cpu", "memory", "network", "software_version"):
        v = getattr(body, field)
        if v is not None:
            setattr(device, field, v)
    if body.gps is not None:
        device.gps_ok = body.gps
    if body.content_version is not None:
        device.current_content_version = body.content_version
        device.current_content_names = (body.content_names or "")[:500]
    zones = db.query(Zone).all()
    if body.latitude is not None and body.longitude is not None:
        update_location(db, device, body.latitude, body.longitude, zones)
    db.commit()
    broadcast_device(device)
    return _sync_state(db, device, zones)


@router.post("/location")
def location(body: LocationIn, db: Session = Depends(get_db), device: Device = Depends(current_device)):
    if body.device_id and body.device_id != device.device_id:
        raise HTTPException(403, "Token does not belong to this device")
    touch(db, device)
    device.gps_ok = True
    zones = db.query(Zone).all()
    update_location(db, device, body.latitude, body.longitude, zones)
    db.commit()
    broadcast_device(device)
    return _sync_state(db, device, zones)


@router.get("/{device_id}/configuration")
def configuration(device_id: str, device: Device = Depends(current_device)):
    _own(device, device_id)
    return {
        "device_id": device.device_id,
        "config": effective_config(device),
        "offline_threshold_seconds": config.OFFLINE_THRESHOLD_SECONDS,
        "server_time": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/{device_id}/content")
def content(device_id: str, db: Session = Depends(get_db), device: Device = Depends(current_device)):
    _own(device, device_id)
    r = resolve(db, device)
    for item in r["items"]:
        item["url"] = f"/device/{device.device_id}/media/{item['content_id']}"
    return {**r, "config": effective_config(device)}


@router.get("/{device_id}/media/{content_id}")
def media(device_id: str, content_id: int, request: Request, db: Session = Depends(get_db),
          device: Device = Depends(current_device)):
    _own(device, device_id)
    return stream_content(get_or_404(db, Content, content_id, "Content"), request)


@router.post("/impressions")
def impressions(body: ImpressionsIn, db: Session = Depends(get_db), device: Device = Depends(current_device)):
    for i in body.items:
        try:
            started = datetime.fromisoformat(i.started_at) if i.started_at else utcnow()
        except ValueError:
            started = utcnow()
        db.add(Impression(device_id=device.device_id, content_id=i.content_id, zone_id=i.zone_id,
                          started_at=started, duration=i.duration))
    db.commit()
    return {"ok": True, "accepted": len(body.items)}
