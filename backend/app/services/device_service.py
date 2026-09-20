from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from .. import config
from ..models import Device, DeviceLog, Zone, utcnow
from ..realtime import hub, notify_admins
from . import routes, tracking
from .geo import zones_containing

DEFAULT_CONFIG = {"heartbeat_interval": 10, "location_interval": 3, "mute": True, "fit": "contain"}


def add_log(db: Session, device_id: str, kind: str, message: str) -> None:
    db.add(DeviceLog(device_id=device_id, kind=kind, message=message))


def is_online(device: Device, now: datetime | None = None) -> bool:
    if not device.last_seen:
        return False
    now = now or datetime.now(timezone.utc)
    last = device.last_seen if device.last_seen.tzinfo else device.last_seen.replace(tzinfo=timezone.utc)
    return (now - last) <= timedelta(seconds=config.OFFLINE_THRESHOLD_SECONDS)


def serialize(device: Device) -> dict:
    from .health import health  # local import: health imports helpers from this module

    score, reasons = health(device)
    last = device.last_seen
    if last is not None and last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return {
        "id": device.id,
        "device_id": device.device_id,
        "client_id": device.client_id,
        "name": device.name,
        "status": "online" if is_online(device) else "offline",
        "registered": device.registered_at is not None,
        "connection_type": device.connection_type,
        "health": score,
        "health_reasons": reasons,
        "group_id": device.group_id,
        "group": device.group.name if device.group else None,
        "latitude": device.latitude,
        "longitude": device.longitude,
        "last_seen": last.isoformat() if last else None,
        "zone_id": device.current_zone_id,
        "zone": device.current_zone.name if device.current_zone else None,
        "content_version": device.current_content_version,
        "current_content": device.current_content_names,
        "software_version": device.software_version,
        "os_name": device.os_name,
        "os_version": device.os_version,
        "os_arch": device.os_arch,
        "runtime_version": device.runtime_version,
        "capabilities": device.capabilities or [],
        "protection": "protected" if device.public_key else "unprotected",
        "key_bound_at": device.key_bound_at.isoformat() if device.key_bound_at else None,
        "tamper_state": device.tamper_state,
        "tamper_flagged_at": device.tamper_flagged_at.isoformat() if device.tamper_flagged_at else None,
        "cpu": device.cpu,
        "memory": device.memory,
        "network": device.network,
        "gps_ok": device.gps_ok,
        "config": {**DEFAULT_CONFIG, **(device.config or {})},
        "ws_connected": hub.is_connected(device.device_id),
        "route_id": device.route_id,
        "route": routes.status(device, device.route),
        "screenshot_at": device.screenshot_at.isoformat() if device.screenshot_at else None,
    }


def effective_config(device: Device) -> dict:
    return {**DEFAULT_CONFIG, **(device.config or {})}


def touch(db: Session, device: Device) -> None:
    """Record proof of life; log the offline->online transition."""
    was_online = device.status == "online" and is_online(device)
    device.last_seen = utcnow()
    device.status = "online"
    if not was_online:
        add_log(db, device.device_id, "online", "Device came online")


def update_location(db: Session, device: Device, lat: float, lng: float, zones: list[Zone] | None = None) -> None:
    """Store the position and refresh which zone the device is in. Pass `zones` to reuse an already loaded list."""
    device.latitude, device.longitude = lat, lng
    hits = zones_containing(lat, lng, db.query(Zone).filter(Zone.client_id == device.client_id).all() if zones is None else zones)
    new_zone = hits[0] if hits else None
    old_id = device.current_zone_id
    new_id = new_zone.id if new_zone else None
    if old_id != new_id:
        device.current_zone_id = new_id
        device.current_zone = new_zone
        add_log(db, device.device_id, "zone", f"Entered zone: {new_zone.name}" if new_zone else "Left all zones")
    routes.track(db, device)
    tracking.record(db, device, new_id, old_id != new_id)


def broadcast_device(device: Device) -> None:
    notify_admins("device_update", device.client_id, device=serialize(device))
