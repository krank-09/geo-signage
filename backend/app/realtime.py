"""WebSocket fan-out to admin dashboards and device agents."""
import json
import logging

import anyio
from fastapi import WebSocket

log = logging.getLogger("realtime")


class Hub:
    """Fan-out to dashboards and agents. Sockets remember which client they belong to so events never cross clients."""

    def __init__(self) -> None:
        self.admins: dict[WebSocket, int | None] = {}     # socket -> user's client (None = platform user, receives everything)
        self.devices: dict[str, set[WebSocket]] = {}
        self.device_client: dict[str, int | None] = {}    # device id -> its client

    async def _send(self, ws: WebSocket, msg: dict) -> bool:
        try:
            await ws.send_text(json.dumps(msg, default=str))
            return True
        except Exception:
            return False

    async def to_admins(self, msg: dict, client_id: int | None = None) -> None:
        """client_id=None is a platform-wide message. Otherwise only that client's users (and platform users) get it."""
        for ws, scope in list(self.admins.items()):
            if client_id is not None and scope is not None and scope != client_id:
                continue
            if not await self._send(ws, msg):
                self.admins.pop(ws, None)

    async def to_devices(self, msg: dict, device_id: str | None = None, client_id: int | None = None) -> None:
        targets = {device_id: self.devices.get(device_id, set())} if device_id else self.devices
        for did, sockets in list(targets.items()):
            if client_id is not None and self.device_client.get(did) != client_id:
                continue
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


def notify_admins(event: str, client_id: int | None = None, **data) -> None:
    _run(hub.to_admins, {"event": event, "client_id": client_id, **data}, client_id)


def notify_devices(device_id: str | None = None, reason: str = "sync", client_id: int | None = None) -> None:
    _run(hub.to_devices, {"type": "sync", "reason": reason}, device_id, client_id)


def announce_changes(reason: str = "assignments", client_id: int | None = None) -> None:
    """Something that affects what displays should play changed: refresh dashboards and the displays of that client."""
    notify_admins("assignments_changed", client_id)
    notify_devices(None, reason, client_id)
