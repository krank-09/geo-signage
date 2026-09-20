from bisect import bisect_right
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Content, Device, DeviceLog, Impression, Zone
from ..scope import Scope, get_scope, scoped, scoped_device_ids
from ..services.device_service import is_online

router = APIRouter(prefix="/monitoring", tags=["monitoring"])


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _log(r: DeviceLog) -> dict:
    return {"id": r.id, "ts": _aware(r.ts), "kind": r.kind, "message": r.message, "device_id": r.device_id}


def uptime_24h(db: Session, device: Device, now: datetime) -> float:
    """Fraction of the last 24h (or since creation) the device was online, from online/offline log events."""
    start = max(now - timedelta(hours=24), _aware(device.created_at))
    span = (now - start).total_seconds()
    if span <= 0:
        return 0.0
    events = (
        db.query(DeviceLog)
        .filter(DeviceLog.device_id == device.device_id, DeviceLog.kind.in_(("online", "offline")))
        .order_by(DeviceLog.ts).all()
    )
    state, cursor, online = False, start, 0.0
    for e in events:
        ts = _aware(e.ts)
        if ts <= start:
            state = e.kind == "online"
            continue
        if state:
            online += (ts - cursor).total_seconds()
        state, cursor = e.kind == "online", ts
    if state:
        online += (now - cursor).total_seconds()
    return round(min(online / span, 1.0) * 100, 1)


def _by_devices(q, column, ids: list[str] | None):
    """Restrict a query on a device_id column to the caller's devices (None = everything, platform view)."""
    return q if ids is None else q.filter(column.in_(ids))


@router.get("/overview")
def overview(db: Session = Depends(get_db), scope: Scope = Depends(get_scope)):
    devices = scoped(db.query(Device), Device, scope).all()
    online = sum(1 for d in devices if is_online(d))
    ids = scoped_device_ids(db, scope)
    logs = _by_devices(db.query(DeviceLog), DeviceLog.device_id, ids).order_by(DeviceLog.id.desc()).limit(15).all()
    return {
        "devices_total": len(devices), "devices_online": online, "devices_offline": len(devices) - online,
        "content_total": scoped(db.query(Content), Content, scope).count(), "zones_total": scoped(db.query(Zone), Zone, scope).count(),
        "recent_logs": [_log(r) for r in logs],
    }


@router.get("/logs")
def logs(limit: int = 100, kind: str | None = None, db: Session = Depends(get_db), scope: Scope = Depends(get_scope)):
    q = _by_devices(db.query(DeviceLog), DeviceLog.device_id, scoped_device_ids(db, scope))
    if kind:
        q = q.filter(DeviceLog.kind == kind)
    return [_log(r) for r in q.order_by(DeviceLog.id.desc()).limit(min(limit, 500))]


@router.get("/analytics")
def analytics(db: Session = Depends(get_db), scope: Scope = Depends(get_scope)):
    now = datetime.now(timezone.utc)
    ids = scoped_device_ids(db, scope)
    names = {c.id: c.name for c in scoped(db.query(Content), Content, scope)}
    per_content = (
        _by_devices(db.query(Impression.content_id, func.count(Impression.id), func.coalesce(func.sum(Impression.duration), 0)),
                    Impression.device_id, ids)
        .group_by(Impression.content_id).all()
    )
    zone_visits: dict[str, int] = {}
    for r in _by_devices(db.query(DeviceLog), DeviceLog.device_id, ids).filter(DeviceLog.kind == "zone"):
        zone_visits[r.message] = zone_visits.get(r.message, 0) + 1
    return {
        "content": sorted(
            [{"content_id": cid, "name": names.get(cid, f"#{cid}"), "views": n, "seconds": round(s)}
             for cid, n, s in per_content if cid in names or scope.client_id is None], key=lambda x: -x["views"]),
        "uptime": [{"device_id": d.device_id, "name": d.name, "uptime_24h": uptime_24h(db, d, now)}
                   for d in scoped(db.query(Device), Device, scope).order_by(Device.device_id)],
        "zone_visits": [{"event": k, "count": v} for k, v in sorted(zone_visits.items(), key=lambda kv: -kv[1])],
    }


@router.get("/timeline")
def timeline(db: Session = Depends(get_db), scope: Scope = Depends(get_scope)):
    """Chart series: devices online per 10 min (last 3h) and impressions per hour (last 12h)."""
    now = datetime.now(timezone.utc)
    devices = scoped(db.query(Device), Device, scope).all()
    ids = [d.device_id for d in devices]
    events: dict[str, tuple[list[datetime], list[bool]]] = {d.device_id: ([], []) for d in devices}
    for e in _by_devices(db.query(DeviceLog), DeviceLog.device_id, ids).filter(DeviceLog.kind.in_(("online", "offline"))).order_by(DeviceLog.ts):
        if e.device_id in events:
            events[e.device_id][0].append(_aware(e.ts))
            events[e.device_id][1].append(e.kind == "online")

    online = []
    for i in range(17, -1, -1):
        t = now - timedelta(minutes=10 * i)
        count = 0
        for d in devices:
            if i == 0:
                count += is_online(d, now)
                continue
            stamps, states = events[d.device_id]
            k = bisect_right(stamps, t)
            count += bool(k and states[k - 1])
        online.append({"ts": t, "value": count})

    views = [0] * 12
    q = _by_devices(db.query(Impression.started_at), Impression.device_id, ids).filter(Impression.started_at >= now - timedelta(hours=12))
    for (started,) in q:
        idx = int((now - _aware(started)).total_seconds() // 3600)
        if 0 <= idx < 12:
            views[11 - idx] += 1
    return {
        "devices_total": len(devices),
        "online": online,
        "views": [{"ts": now - timedelta(hours=11 - i), "value": v} for i, v in enumerate(views)],
    }
