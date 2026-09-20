"""Background task that flips devices to offline once their heartbeats stop."""
import asyncio
import logging

from .. import config
from ..database import SessionLocal
from ..models import Device
from ..realtime import hub
from .device_service import add_log, is_online, serialize
from .health import evaluate_alerts

log = logging.getLogger("monitor")


def sweep_offline() -> dict:
    """Mark stale devices offline (with a log row), then raise/resolve health alerts.
    Returns the serialized devices that changed plus the alerts raised and resolved."""
    with SessionLocal() as db:
        changed = []
        for d in db.query(Device).filter(Device.status == "online").all():
            if not is_online(d):
                d.status = "offline"
                add_log(db, d.device_id, "offline", "No heartbeat received - device offline")
                changed.append(d)
        db.commit()
        result = evaluate_alerts(db)
        return {"devices": [serialize(d) for d in changed], **result}


async def monitor_loop() -> None:
    while True:
        await asyncio.sleep(config.MONITOR_INTERVAL_SECONDS)
        try:
            result = await asyncio.to_thread(sweep_offline)
            for dev in result["devices"]:
                await hub.to_admins({"event": "device_update", "client_id": dev["client_id"], "device": dev}, dev["client_id"])
            for alert in result["raised"]:
                await hub.to_admins({"event": "alert", "client_id": alert["client_id"], "alert": alert}, alert["client_id"])
            for alert in result["resolved"]:
                await hub.to_admins({"event": "alert_resolved", "client_id": alert["client_id"], "alert": alert}, alert["client_id"])
        except Exception:
            log.exception("offline monitor failed")
