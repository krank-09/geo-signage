"""Background task that flips devices to offline once their heartbeats stop."""
import asyncio
import logging

from .. import config
from ..database import SessionLocal
from ..models import Device
from ..realtime import hub
from .device_service import add_log, is_online, serialize

log = logging.getLogger("monitor")


def sweep_offline() -> list[dict]:
    """Mark stale devices offline (with a log row). Returns the serialized devices that changed."""
    with SessionLocal() as db:
        changed = []
        for d in db.query(Device).filter(Device.status == "online").all():
            if not is_online(d):
                d.status = "offline"
                add_log(db, d.device_id, "offline", "No heartbeat received - device offline")
                changed.append(d)
        db.commit()
        return [serialize(d) for d in changed]


async def monitor_loop() -> None:
    while True:
        await asyncio.sleep(config.MONITOR_INTERVAL_SECONDS)
        try:
            for dev in await asyncio.to_thread(sweep_offline):
                await hub.to_admins({"event": "device_update", "device": dev})
        except Exception:
            log.exception("offline monitor failed")
