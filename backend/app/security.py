from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import Depends, Header, HTTPException, Query, status
from sqlalchemy.orm import Session

from . import config
from .database import get_db
from .models import Device, User

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


def current_device(authorization: str | None = Header(None), db: Session = Depends(get_db)) -> Device:
    return device_from_token(_bearer(authorization), db)
