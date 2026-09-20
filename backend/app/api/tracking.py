"""Location history (trail on the map, zone visits) and remote screenshots."""
from datetime import timedelta

from fastapi import APIRouter, Depends, Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import LocationPoint, User, Zone, utcnow
from ..realtime import notify_devices
from ..scope import Scope, get_scope, get_scoped_device, resolve_scope, scoped, write_scope
from ..security import current_user_or_query
from ..storage import get_storage

router = APIRouter(tags=["tracking"])


@router.get("/devices/{device_id}/track")
def track(device_id: str, hours: int = 24, limit: int = 1500, db: Session = Depends(get_db), scope: Scope = Depends(get_scope)):
    """The display's remembered positions, oldest first. `limit` keeps the newest points if there are more."""
    get_scoped_device(db, device_id, scope)
    since = utcnow() - timedelta(hours=max(1, min(hours, 24 * 30)))
    rows = (db.query(LocationPoint).filter(LocationPoint.device_id == device_id, LocationPoint.ts >= since)
            .order_by(LocationPoint.id.desc()).limit(max(1, min(limit, 5000))).all())
    rows.reverse()
    return [{"lat": p.latitude, "lng": p.longitude, "ts": p.ts, "zone_id": p.zone_id, "entered": p.entered} for p in rows]


@router.get("/monitoring/zone-visits")
def zone_visits(hours: int = 24, db: Session = Depends(get_db), scope: Scope = Depends(get_scope)):
    """How many times displays entered each zone in the period, and how many different displays did."""
    since = utcnow() - timedelta(hours=max(1, min(hours, 24 * 30)))
    q = scoped(db.query(LocationPoint.zone_id, func.count(LocationPoint.id), func.count(func.distinct(LocationPoint.device_id))),
               LocationPoint, scope).filter(LocationPoint.entered.is_(True), LocationPoint.ts >= since).group_by(LocationPoint.zone_id)
    names = {z.id: z.name for z in scoped(db.query(Zone), Zone, scope)}
    out = [{"zone_id": zid, "zone_name": names.get(zid, "(deleted zone)"), "visits": n, "devices": d} for zid, n, d in q]
    return sorted(out, key=lambda r: -r["visits"])


# ---- screenshots ---------------------------------------------------------------------------------------
@router.get("/devices/{device_id}/screenshot")
def get_screenshot(device_id: str, db: Session = Depends(get_db), user: User = Depends(current_user_or_query)):
    """The last picture the display sent of its own screen. `?token=` works so an <img> tag can load it."""
    d = get_scoped_device(db, device_id, resolve_scope(user, None, db))
    if not d.screenshot_key:
        return Response(status_code=404)
    storage = get_storage()
    data = b"".join(storage.read(d.screenshot_key, 0, storage.size(d.screenshot_key)))
    return Response(data, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@router.post("/devices/{device_id}/screenshot/request")
def request_screenshot(device_id: str, db: Session = Depends(get_db), scope: Scope = Depends(write_scope)):
    """Ask the display for a fresh picture now. It arrives within a few seconds if the display is online."""
    d = get_scoped_device(db, device_id, scope)
    notify_devices(d.device_id, "screenshot", d.client_id)
    return {"ok": True}


