"""Health alerts and the threshold that triggers them."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Alert, Device, User, utcnow
from ..realtime import notify_admins
from ..schemas import HealthSettingIn
from ..security import current_user, require_admin
from ..services.health import alert_threshold, evaluate_alerts, serialize_alert
from ..services.settings import set_setting
from .deps import get_or_404

router = APIRouter(tags=["alerts"])


@router.get("/alerts")
def list_alerts(state: str = "open", limit: int = 50, db: Session = Depends(get_db), _: User = Depends(current_user)):
    q = db.query(Alert)
    if state == "open":
        q = q.filter(Alert.resolved_at.is_(None))
    names = {d.device_id: d.name for d in db.query(Device)}
    return [{**serialize_alert(a), "device_name": names.get(a.device_id)} for a in q.order_by(Alert.id.desc()).limit(min(limit, 200))]


@router.post("/alerts/{alert_id}/ack")
def acknowledge(alert_id: int, db: Session = Depends(get_db), me: User = Depends(require_admin)):
    a = get_or_404(db, Alert, alert_id, "Alert")
    if a.acknowledged_at is None:
        a.acknowledged_at, a.acknowledged_by = utcnow(), me.username
        db.commit()
        notify_admins("alerts_changed")
    return serialize_alert(a)


@router.get("/settings/health")
def get_health_settings(db: Session = Depends(get_db), _: User = Depends(current_user)):
    return {"threshold": alert_threshold(db)}


@router.put("/settings/health")
def set_health_settings(body: HealthSettingIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    set_setting(db, "health_alert_threshold", str(body.threshold))
    result = evaluate_alerts(db)  # apply the new threshold immediately instead of at the next sweep
    for alert in result["raised"]:
        notify_admins("alert", alert=alert)
    for alert in result["resolved"]:
        notify_admins("alert_resolved", alert=alert)
    return {"threshold": body.threshold}
