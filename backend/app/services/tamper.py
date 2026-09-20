"""Tamper events: a hash-chained, append-only record plus the device flag and critical alert they raise.

Response policy is deliberately 'alert and flag only': a tampered device keeps working, a critical alert appears and the
device is marked as tampered until an administrator clears it. Nothing is revoked automatically, so a false positive
cannot take a display offline."""
import hashlib
import json
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..models import Alert, Device, DeviceLog, TamperEvent, utcnow
from ..realtime import notify_admins

# What a display may report about itself, with the severity each deserves.
DEVICE_KINDS = {
    "cache_tampered": "critical",       # a cached media file no longer matches its signed hash
    "media_hash_mismatch": "critical",  # a download did not match the hash the server signed
    "manifest_signature_invalid": "critical",  # a playlist was not signed by the pinned server key
    "config_tampered": "critical",      # the agent's saved state failed its integrity check
    "code_modified": "critical",        # the agent's own files changed while running
    "clock_rollback": "critical",       # the system clock jumped backwards
    "unexpected_restart": "warning",    # the agent started without having shut down cleanly
    "system_clock_wrong": "warning",
}
FLAGGING = {"critical"}


def _stamp(dt: datetime) -> str:
    """Same text whether the database hands the time back naive (SQLite) or aware (Postgres)."""
    return dt.astimezone(timezone.utc).replace(tzinfo=None).isoformat() if dt.tzinfo else dt.isoformat()


def _digest(prev: str, e: TamperEvent) -> str:
    body = json.dumps([prev, e.client_id, e.device_id, e.kind, e.severity, e.source, e.detail, _stamp(e.created_at)], sort_keys=False)
    return hashlib.sha256(body.encode()).hexdigest()


def serialize(e: TamperEvent) -> dict:
    return {"id": e.id, "client_id": e.client_id, "device_id": e.device_id, "kind": e.kind, "severity": e.severity, "source": e.source,
            "detail": e.detail, "created_at": e.created_at, "hash": e.hash[:12]}


def record(db: Session, device: Device, kind: str, detail: str, severity: str = "critical", source: str = "server",
           dedupe_seconds: int = 60, now: datetime | None = None) -> TamperEvent | None:
    """Append an event. Returns None if the same kind was just recorded for this device (a burst is one incident)."""
    now = now or utcnow()
    since = now - timedelta(seconds=dedupe_seconds)
    recent = db.query(TamperEvent).filter(TamperEvent.device_id == device.device_id, TamperEvent.kind == kind,
                                          TamperEvent.created_at >= since).first()
    if recent is not None:
        return None
    last = db.query(TamperEvent).filter(TamperEvent.client_id == device.client_id).order_by(TamperEvent.id.desc()).first()
    e = TamperEvent(client_id=device.client_id, device_id=device.device_id, kind=kind, severity=severity, source=source,
                    detail=detail[:500], created_at=now, prev_hash=last.hash if last else "")
    e.hash = _digest(e.prev_hash, e)
    db.add(e)
    db.add(DeviceLog(device_id=device.device_id, kind="tamper", message=f"{kind}: {detail[:200]}"))
    raised = None
    if severity in FLAGGING:
        if device.tamper_state != "flagged":
            device.tamper_state, device.tamper_flagged_at = "flagged", now
        if db.query(Alert).filter(Alert.device_id == device.device_id, Alert.kind == "tamper", Alert.resolved_at.is_(None)).first() is None:
            raised = Alert(client_id=device.client_id, device_id=device.device_id, kind="tamper", health=0,
                           message=f"TAMPER: {device.name} ({device.device_id}): {kind.replace('_', ' ')}. {detail[:160]}")
            db.add(raised)
    db.commit()
    db.refresh(e)
    if raised is not None:
        from .health import serialize_alert
        notify_admins("alert", device.client_id, alert=serialize_alert(raised))
    notify_admins("tamper", device.client_id, entry=serialize(e), device_id=device.device_id)
    return e


def clear_flag(db: Session, device: Device, admin: str) -> None:
    """An administrator has investigated. Clears the flag and closes the tamper alert; the history stays."""
    device.tamper_state, device.tamper_flagged_at = None, None
    for a in db.query(Alert).filter(Alert.device_id == device.device_id, Alert.kind == "tamper", Alert.resolved_at.is_(None)):
        a.resolved_at = utcnow()
    record(db, device, "flag_cleared", f"Cleared by {admin}", severity="info", source="admin", dedupe_seconds=0)
    db.commit()
    notify_admins("alerts_changed", device.client_id)


def verify_chain(db: Session, client_id: int | None) -> dict:
    """Recompute every hash for a client. Editing or deleting any past event breaks the chain from that point on."""
    prev, count = "", 0
    for e in db.query(TamperEvent).filter(TamperEvent.client_id == client_id).order_by(TamperEvent.id):
        count += 1
        if e.prev_hash != prev or _digest(prev, e) != e.hash:
            return {"ok": False, "events": count, "broken_at": e.id}
        prev = e.hash
    return {"ok": True, "events": count, "broken_at": None}


def utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
