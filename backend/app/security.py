from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import Depends, Header, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from . import config
from .database import get_db
from .models import Client, Device, User

_ph = PasswordHasher()
ALGO = "HS256"


def hash_secret(value: str) -> str:
    return _ph.hash(value)


def verify_secret(value: str, hashed: str) -> bool:
    try:
        return _ph.verify(hashed, value)
    except (VerifyMismatchError, InvalidHashError):
        return False


def _encode(payload: dict, expires: timedelta) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode({**payload, "iat": now, "exp": now + expires}, config.SECRET_KEY, algorithm=ALGO)


def _decode(token: str) -> dict:
    return jwt.decode(token, config.SECRET_KEY, algorithms=[ALGO])


def create_admin_token(user: User) -> str:
    return _encode({"sub": user.username, "role": user.role, "typ": "admin"}, timedelta(minutes=config.ADMIN_TOKEN_MINUTES))


def create_device_token(device: Device) -> str:
    return _encode(
        {"sub": device.device_id, "ver": device.token_version, "typ": "device"},
        timedelta(days=config.DEVICE_TOKEN_DAYS),
    )


def _bearer(authorization: str | None) -> str | None:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


def user_from_token(token: str | None, db: Session) -> User:
    unauthorized = HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or missing credentials")
    if not token:
        raise unauthorized
    try:
        payload = _decode(token)
    except jwt.PyJWTError:
        raise unauthorized
    if payload.get("typ") != "admin":
        raise unauthorized
    user = db.query(User).filter(User.username == payload.get("sub")).first()
    if not user:
        raise unauthorized
    if user.role == "pending":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Your account is waiting for an administrator's approval")
    if user.client_id is not None:
        client = db.get(Client, user.client_id)
        if client is None or not client.active:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "This client account is suspended")
    return user


def device_from_token(token: str | None, db: Session) -> Device:
    unauthorized = HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid, expired or revoked device token")
    if not token:
        raise unauthorized
    try:
        payload = _decode(token)
    except jwt.PyJWTError:
        raise unauthorized
    if payload.get("typ") != "device":
        raise unauthorized
    device = db.query(Device).filter(Device.device_id == payload.get("sub")).first()
    if not device or device.token_version != payload.get("ver"):
        raise unauthorized
    if device.client_id is not None:
        client = db.get(Client, device.client_id)
        if client is None or not client.active:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "This client account is suspended")
    return device


def current_user(authorization: str | None = Header(None), db: Session = Depends(get_db)) -> User:
    return user_from_token(_bearer(authorization), db)


def current_user_or_query(
    authorization: str | None = Header(None), token: str | None = Query(None), db: Session = Depends(get_db)
) -> User:
    """For <img>/<video> tags that cannot send headers."""
    return user_from_token(_bearer(authorization) or token, db)


def require_admin(user: User = Depends(current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Administrator role required")
    return user


async def current_device(request: Request, authorization: str | None = Header(None), db: Session = Depends(get_db)) -> Device:
    """Token check plus, for displays with a bound identity key, a signature check. A stolen token or copied .env alone
    is not enough to act as a bound display."""
    from .services import deviceauth, tamper

    device = device_from_token(_bearer(authorization), db)
    sig = deviceauth.SigInfo(
        signature=request.headers.get("x-signature"), timestamp=request.headers.get("x-timestamp"), nonce=request.headers.get("x-nonce"),
        method=request.method, target=request.url.path + (f"?{request.url.query}" if request.url.query else ""),
        body_sha256=deviceauth.sha256_hex(await request.body()))
    if device.public_key:
        try:
            deviceauth.verify_request(device.device_id, device.public_key, sig)
        except deviceauth.SignatureError as e:
            if e.kind == "clock_skew":
                tamper.record(db, device, "system_clock_wrong", e.reason, "warning", "server")
            else:
                label = {"unsigned_request": "unsigned_downgrade", "replay": "replayed_request"}.get(e.kind, "bad_signature")
                tamper.record(db, device, label, f"{request.method} {request.url.path}: {e.reason}", "critical", "server")
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid device signature")
    elif config.DEVICE_AUTH_MODE == "required":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "This server requires displays to hold an identity key; update the display agent")
    return device
