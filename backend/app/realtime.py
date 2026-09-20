"""WebSocket fan-out to admin dashboards and device agents."""
import json
import logging

import anyio
from fastapi import WebSocket

log = logging.getLogger("realtime")


class Hub:
    def __init__(self) -> None:
        self.admins: set[WebSocket] = set()
        self.devices: dict[str, set[WebSocket]] = {}

    async def _send(self, ws: WebSocket, msg: dict) -> bool:
        try:
            await ws.send_text(json.dumps(msg, default=str))
            return True
        except Exception:
            return False

    async def to_admins(self, msg: dict) -> None:
        for ws in list(self.admins):
            if not await self._send(ws, msg):
                self.admins.discard(ws)

    async def to_devices(self, msg: dict, device_id: str | None = None) -> None:
        targets = {device_id: self.devices.get(device_id, set())} if device_id else self.devices
        for did, sockets in list(targets.items()):
            for ws in list(sockets):
                if not await self._send(ws, msg):
                    sockets.discard(ws)

    def is_connected(self, device_id: str) -> bool:
        return bool(self.devices.get(device_id))


hub = Hub()


def _run(fn, *args) -> None:
    """Bridge from sync endpoints (worker threads) or async code into the hub."""
    try:
        anyio.from_thread.run(fn, *args)
    except RuntimeError:
        # Not inside an anyio worker thread (e.g. tests / startup) - nothing is listening anyway.
        pass
    except Exception:  # pragma: no cover
        log.exception("realtime dispatch failed")


def notify_admins(event: str, **data) -> None:
    _run(hub.to_admins, {"event": event, **data})


def notify_devices(device_id: str | None = None, reason: str = "sync") -> None:
    _run(hub.to_devices, {"type": "sync", "reason": reason}, device_id)


def announce_changes(reason: str = "assignments") -> None:
    """Something that affects what displays should play changed: refresh dashboards and every display."""
    notify_admins("assignments_changed")
    notify_devices(None, reason)
