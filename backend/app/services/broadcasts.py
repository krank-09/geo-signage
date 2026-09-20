"""Live announcements: which broadcasts a device should show right now."""
import hashlib
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..models import Broadcast, Device


def _aware(dt: datetime | None) -> datetime | None:
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def is_active(b: Broadcast, now: datetime) -> bool:
    expires = _aware(b.expires_at)
    return b.ended_at is None and (expires is None or expires > now)


def remaining_seconds(b: Broadcast, now: datetime) -> int | None:
    expires = _aware(b.expires_at)
    return None if expires is None else max(0, int((expires - now).total_seconds()))


def targets(b: Broadcast, device: Device, zone_ids: set[int]) -> bool:
    """A target left empty means 'everyone' for that dimension; all set targets must match."""
    return ((b.zone_id is None or b.zone_id in zone_ids)
            and (b.group_id is None or b.group_id == device.group_id)
            and (b.device_id is None or b.device_id == device.device_id))


def active_for_device(db: Session, device: Device, zone_ids: set[int], now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    rows = [b for b in db.query(Broadcast).filter(Broadcast.ended_at.is_(None), Broadcast.client_id == device.client_id).order_by(Broadcast.id)
            if is_active(b, now) and targets(b, device, zone_ids)]
    return [{"id": b.id, "message": b.message, "style": b.style, "severity": b.severity,
             "remaining_seconds": remaining_seconds(b, now)} for b in rows]


def version(items: list[dict]) -> str:
    """Changes whenever the set of visible broadcasts changes (start, end or expiry)."""
    return hashlib.sha1("|".join(str(i["id"]) for i in items).encode()).hexdigest()[:6] if items else ""
