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


async def _hold_open(ws: WebSocket, registry: set[WebSocket]) -> None:
    await ws.accept()
    registry.add(ws)
    try:
        while True:
            await ws.receive_text()  # clients may send pings; the content is ignored
    except WebSocketDisconnect:
        pass
    finally:
        registry.discard(ws)


@router.websocket("/ws/admin")
async def ws_admin(ws: WebSocket, token: str | None = None):
    def check():
        with SessionLocal() as db:
            return user_from_token(token, db)

    if not await _authorized(check):
        await ws.close(code=4401)
        return
    await _hold_open(ws, hub.admins)


@router.websocket("/ws/device/{device_id}")
async def ws_device(ws: WebSocket, device_id: str, token: str | None = None):
    def check():
        with SessionLocal() as db:
            return device_from_token(token, db).device_id == device_id

    if not await _authorized(check):
        await ws.close(code=4401)
        return
    await _hold_open(ws, hub.devices.setdefault(device_id, set()))
