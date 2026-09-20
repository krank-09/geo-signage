"""Device health (0-100) and the alerts raised when it drops below the threshold.

Score = 100 minus penalties, or 0 when the device is offline:
  CPU above 60%            up to -30 (linear to 100%)
  memory above 70%         up to -30 (linear to 100%)
  no GPS fix               -10
  heartbeat running late   up to -20 (once older than two heartbeat intervals, growing until it counts as offline)
"""
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from .. import config
from ..models import Alert, Device, DeviceLog, utcnow
from .device_service import effective_config, is_online
from .settings import get_setting

RECOVERY_MARGIN = 5  # an alert clears only when health is this far above the threshold (avoids flapping)


def health(device: Device, now: datetime | None = None) -> tuple[int, list[str]]:
    """Return (score, reasons). Reasons explain every penalty; empty when the device is fully healthy."""
    now = now or datetime.now(timezone.utc)
    if device.last_seen is None:
        return 0, ["Never connected"]
    if not is_online(device, now):
        return 0, ["Offline"]
    score, reasons = 100.0, []
    if device.cpu is not None and device.cpu > 60:
        score -= (device.cpu - 60) / 40 * 30
        reasons.append(f"CPU {device.cpu:.0f}%")
    if device.memory is not None and device.memory > 70:
        score -= (device.memory - 70) / 30 * 30
        reasons.append(f"Memory {device.memory:.0f}%")
    if not device.gps_ok:
        score -= 10
        reasons.append("No GPS fix")
    last = device.last_seen if device.last_seen.tzinfo else device.last_seen.replace(tzinfo=timezone.utc)
    age = (now - last).total_seconds()
    late_after = 2 * effective_config(device)["heartbeat_interval"]
    if age > late_after:
        score -= min((age - late_after) / max(config.OFFLINE_THRESHOLD_SECONDS - late_after, 1), 1) * 20
        reasons.append("Heartbeat running late")
    return max(0, round(score)), reasons


def alert_threshold(db: Session, client_id: int | None = None) -> int:
    """A client's own threshold if it set one, otherwise the platform default."""
    default = get_setting(db, "health_alert_threshold", str(config.HEALTH_ALERT_THRESHOLD))
    raw = get_setting(db, f"health_alert_threshold:{client_id}", default) if client_id is not None else default
    try:
        return max(0, min(100, int(raw)))
    except ValueError:
        return config.HEALTH_ALERT_THRESHOLD


def serialize_alert(a: Alert) -> dict:
    return {"id": a.id, "client_id": a.client_id, "device_id": a.device_id, "kind": a.kind, "message": a.message, "health": a.health,
            "created_at": a.created_at, "resolved_at": a.resolved_at,
            "acknowledged_at": a.acknowledged_at, "acknowledged_by": a.acknowledged_by}


def evaluate_alerts(db: Session, now: datetime | None = None) -> dict[str, list[dict]]:
    """Raise an alert for each device below the threshold and resolve the ones that recovered.
    Devices that have never connected are skipped (they are not 'dropping', they are not deployed yet)."""
    thresholds: dict[int | None, int] = {}
    open_alerts = {a.device_id: a for a in db.query(Alert).filter(Alert.resolved_at.is_(None), Alert.kind.in_(("offline", "health_low")))}
    raised, resolved = [], []
    for d in db.query(Device).filter(Device.last_seen.is_not(None)).all():
        score, reasons = health(d, now)
        if d.client_id not in thresholds:
            thresholds[d.client_id] = alert_threshold(db, d.client_id)
        threshold = thresholds[d.client_id]
        current = open_alerts.get(d.device_id)
        if score < threshold and current is None:
            kind = "offline" if reasons == ["Offline"] else "health_low"
            detail = ", ".join(reasons) or "below threshold"
            alert = Alert(client_id=d.client_id, device_id=d.device_id, kind=kind, health=score,
                          message=f"{d.name} ({d.device_id}) health {score}%, below {threshold}%: {detail}")
            db.add(alert)
            db.add(DeviceLog(device_id=d.device_id, kind="alert", message=f"Health alert: {score}% ({detail})"))
            db.flush()
            raised.append(serialize_alert(alert))
        elif current is not None and score >= min(threshold + RECOVERY_MARGIN, 100):
            current.resolved_at = utcnow()
            db.add(DeviceLog(device_id=d.device_id, kind="alert", message=f"Health recovered: {score}%"))
            resolved.append(serialize_alert(current))
    db.commit()
    return {"raised": raised, "resolved": resolved}
