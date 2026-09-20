"""Location history: remember where a display has been, cheaply.

A point is stored when the display first reports, when it enters a different zone, or when it has moved at least
MIN_MOVE_KM since the last stored point and at least MIN_SECONDS have passed. A parked display therefore stores nothing."""
from datetime import timedelta

from sqlalchemy.orm import Session

from .. import config
from ..models import Device, LocationPoint, utcnow
from .geo import haversine_km

MIN_MOVE_KM = 0.05
MIN_SECONDS = 5


def record(db: Session, device: Device, zone_id: int | None, zone_changed: bool) -> None:
    now = utcnow()
    if device.track_at is not None and not zone_changed:
        last = device.track_at if device.track_at.tzinfo else device.track_at.replace(tzinfo=now.tzinfo)
        if (now - last).total_seconds() < MIN_SECONDS:
            return
        if haversine_km(device.track_lat, device.track_lng, device.latitude, device.longitude) < MIN_MOVE_KM:
            return
    db.add(LocationPoint(client_id=device.client_id, device_id=device.device_id, latitude=device.latitude, longitude=device.longitude,
                         zone_id=zone_id, entered=bool(zone_changed and zone_id is not None), ts=now))
    device.track_lat, device.track_lng, device.track_at = device.latitude, device.longitude, now


def prune(db: Session) -> int:
    cutoff = utcnow() - timedelta(days=config.TRACK_RETENTION_DAYS)
    n = db.query(LocationPoint).filter(LocationPoint.ts < cutoff).delete()
    db.commit()
    return n
