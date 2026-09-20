"""Health alerts and the threshold that triggers them."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Alert, Device, utcnow
from ..realtime import notify_admins
from ..schemas import HealthSettingIn
from ..scope import Scope, get_scope, get_scoped, scoped, write_scope
from ..services.health import alert_threshold, evaluate_alerts, serialize_alert
from ..services.settings import set_setting

router = APIRouter(tags=["alerts"])


@router.get("/alerts")
def list_alerts(state: str = "open", limit: int = 50, db: Session = Depends(get_db), scope: Scope = Depends(get_scope)):
    q = scoped(db.query(Alert), Alert, scope)
    if state == "open":
        q = q.filter(Alert.resolved_at.is_(None))
    names = {d.device_id: d.name for d in scoped(db.query(Device), Device, scope)}
    return [{**serialize_alert(a), "device_name": names.get(a.device_id)} for a in q.order_by(Alert.id.desc()).limit(min(limit, 200))]


@router.post("/alerts/{alert_id}/ack")
def acknowledge(alert_id: int, db: Session = Depends(get_db), scope: Scope = Depends(get_scope)):
    if not scope.is_admin:
        raise HTTPException(403, "Administrator role required")
    a = get_scoped(db, Alert, alert_id, scope, "Alert")
    if a.acknowledged_at is None:
        a.acknowledged_at, a.acknowledged_by = utcnow(), scope.user.username
        db.commit()
        notify_admins("alerts_changed", a.client_id)
    return serialize_alert(a)


@router.get("/settings/health")
def get_health_settings(db: Session = Depends(get_db), scope: Scope = Depends(get_scope)):
    return {"threshold": alert_threshold(db, scope.client_id)}


@router.put("/settings/health")
def set_health_settings(body: HealthSettingIn, db: Session = Depends(get_db), scope: Scope = Depends(write_scope)):
    set_setting(db, f"health_alert_threshold:{scope.client_id}", str(body.threshold))
    result = evaluate_alerts(db)  # apply the new threshold immediately instead of at the next sweep
    for alert in result["raised"]:
        notify_admins("alert", alert["client_id"], alert=alert)
    for alert in result["resolved"]:
        notify_admins("alert_resolved", alert["client_id"], alert=alert)
    return {"threshold": body.threshold}
