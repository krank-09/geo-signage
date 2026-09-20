"""Route following: where a display is along its route, and an alert when it leaves the corridor."""
from sqlalchemy.orm import Session

from ..models import Alert, Device, DeviceLog, Route
from ..realtime import notify_admins
from .geo import route_position


def status(device: Device, route: Route | None = None) -> dict | None:
    """What the dashboard shows for a display on a route (stored values, so it costs no extra query)."""
    if device.route_id is None or device.route_leg is None:
        return None
    wp = route.waypoints if route else None
    leg = device.route_leg
    label = f"{wp[leg]['name']} → {wp[leg + 1]['name']}" if wp and leg + 1 < len(wp) else None
    return {"route_id": device.route_id, "leg": leg, "leg_label": label, "progress": device.route_progress,
            "offset_km": device.route_offset_km, "off_route": bool(device.route_off)}


def track(db: Session, device: Device) -> None:
    """Recompute the display's place on its route. Logs leg changes and raises/resolves an off-route alert. Caller commits."""
    if device.route_id is None or device.latitude is None:
        device.route_leg = device.route_progress = device.route_offset_km = None
        device.route_off = None
        return
    route = db.get(Route, device.route_id)
    pos = route_position(route.waypoints, device.latitude, device.longitude) if route else None
    if pos is None:
        return
    if device.route_leg != pos["leg"]:
        wp = route.waypoints
        add = f"Route '{route.name}': now heading {wp[pos['leg']]['name']} → {wp[pos['leg'] + 1]['name']}"
        db.add(DeviceLog(device_id=device.device_id, kind="route", message=add))
    device.route_leg, device.route_progress, device.route_offset_km = pos["leg"], pos["progress"], pos["offset_km"]
    off = pos["offset_km"] > route.corridor_km
    if off != bool(device.route_off):
        device.route_off = off
        open_alert = db.query(Alert).filter(Alert.device_id == device.device_id, Alert.kind == "off_route", Alert.resolved_at.is_(None)).first()
        if off:
            db.add(DeviceLog(device_id=device.device_id, kind="route", message=f"Left route '{route.name}' ({pos['offset_km']} km away)"))
            if open_alert is None:
                a = Alert(client_id=device.client_id, device_id=device.device_id, kind="off_route", health=0,
                          message=f"{device.name} ({device.device_id}) left its route '{route.name}': {pos['offset_km']} km from the path")
                db.add(a)
                db.flush()
                from .health import serialize_alert
                notify_admins("alert", device.client_id, alert=serialize_alert(a))
        else:
            db.add(DeviceLog(device_id=device.device_id, kind="route", message=f"Back on route '{route.name}'"))
            if open_alert is not None:
                from .. import models
                open_alert.resolved_at = models.utcnow()
                db.flush()
                from .health import serialize_alert
                notify_admins("alert_resolved", device.client_id, alert=serialize_alert(open_alert))
