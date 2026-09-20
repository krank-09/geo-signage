"""The core decision: (device location, group, time) -> what to play.

Ranking (highest wins, ties play together as a playlist):
  1. emergency assignments
  2. assignment.priority
  3. specificity (zone+group > zone or group > global default)
"""
import hashlib
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from .. import config
from ..models import Assignment, Device, Zone
from .geo import zones_containing


def local_now(now: datetime | None = None) -> datetime:
    now = now or datetime.now(timezone.utc)
    return now + timedelta(minutes=config.SCHEDULE_TZ_OFFSET_MINUTES)


def _minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def in_window(start: str | None, end: str | None, now: datetime | None = None) -> bool:
    if not start or not end:
        return True
    t = local_now(now)
    cur = t.hour * 60 + t.minute
    s, e = _minutes(start), _minutes(end)
    if s == e:
        return True
    return s <= cur < e if s < e else (cur >= s or cur < e)  # overnight window wraps midnight


def resolve(db: Session, device: Device, now: datetime | None = None, zones: list[Zone] | None = None) -> dict:
    hits = zones_containing(device.latitude, device.longitude, db.query(Zone).all() if zones is None else zones)
    zone_ids = {z.id for z in hits}
    primary = hits[0] if hits else None

    candidates = []
    for a in db.query(Assignment).filter(Assignment.active.is_(True)).all():
        if a.zone_id is not None and a.zone_id not in zone_ids:
            continue
        if a.group_id is not None and a.group_id != device.group_id:
            continue
        if not in_window(a.start_time, a.end_time, now):
            continue
        specificity = (a.zone_id is not None) + (a.group_id is not None)
        candidates.append(((int(a.is_emergency), a.priority, specificity), a))

    items, reason = [], "no content assigned"
    if candidates:
        top = max(rank for rank, _ in candidates)
        winners = sorted((a for rank, a in candidates if rank == top), key=lambda a: a.id)
        seen = set()
        for a in winners:
            if a.content_id in seen:
                continue
            seen.add(a.content_id)
            c = a.content
            items.append(
                {
                    "content_id": c.id,
                    "name": c.name,
                    "type": c.type,
                    "duration": c.duration,
                    "version": c.version,
                    "mime": c.mime,
                    "assignment_id": a.id,
                }
            )
        if top[0]:
            reason = "emergency override"
        elif top[2] == 0:
            reason = "default content"
        else:
            reason = f"zone: {winners[0].zone.name}" if winners[0].zone else f"group: {winners[0].group.name}"

    digest = hashlib.sha1(
        "|".join(f"{i['content_id']}:{i['version']}:{i['duration']}" for i in items).encode()
    ).hexdigest()[:12]
    return {
        "manifest_version": digest,
        "zone": {"id": primary.id, "name": primary.name} if primary else None,
        "reason": reason,
        "emergency": bool(candidates) and top[0] == 1,
        "items": items,
    }
