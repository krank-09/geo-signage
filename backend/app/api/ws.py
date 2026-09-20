"""WebSocket endpoints: one channel for admin dashboards, one for device agents."""
import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..database import SessionLocal
from ..realtime import hub
from ..security import device_from_token, user_from_token

router = APIRouter()


async def _authorized(check) -> bool:
    try:
        return bool(await asyncio.to_thread(check))
    except Exception:
        return False


async def _hold_open(ws: WebSocket, join, leave) -> None:
    await ws.accept()
    join()
    try:
        while True:
            await ws.receive_text()  # clients may send pings; the content is ignored
    except WebSocketDisconnect:
        pass
    finally:
        leave()


@router.websocket("/ws/admin")
async def ws_admin(ws: WebSocket, token: str | None = None):
    holder: dict = {}

    def check():
        with SessionLocal() as db:
            holder["client_id"] = user_from_token(token, db).client_id
            return True

    if not await _authorized(check):
        await ws.close(code=4401)
        return
    await _hold_open(ws, lambda: hub.admins.__setitem__(ws, holder["client_id"]), lambda: hub.admins.pop(ws, None))


@router.websocket("/ws/device/{device_id}")
async def ws_device(ws: WebSocket, device_id: str, token: str | None = None):
    holder: dict = {}

    def check():
        with SessionLocal() as db:
            device = device_from_token(token, db)
            holder["client_id"] = device.client_id
            return device.device_id == device_id

    if not await _authorized(check):
        await ws.close(code=4401)
        return

    def join():
        hub.devices.setdefault(device_id, set()).add(ws)
        hub.device_client[device_id] = holder["client_id"]

    await _hold_open(ws, join, lambda: hub.devices.get(device_id, set()).discard(ws))
