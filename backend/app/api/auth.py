import time

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..schemas import LoginIn
from ..security import create_admin_token, current_user, verify_secret

router = APIRouter(prefix="/auth", tags=["auth"])

_failures: dict[str, list[float]] = {}
MAX_FAILS, WINDOW = 5, 60


def _throttled(username: str) -> bool:
    now = time.time()
    recent = [t for t in _failures.get(username, []) if now - t < WINDOW]
    _failures[username] = recent
    return len(recent) >= MAX_FAILS


@router.post("/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    if _throttled(body.username):
        raise HTTPException(429, "Too many failed attempts. Try again in a minute.")
    user = db.query(User).filter(User.username == body.username).first()
    if not user or not verify_secret(body.password, user.password_hash):
        _failures.setdefault(body.username, []).append(time.time())
        raise HTTPException(401, "Invalid username or password")
    _failures.pop(body.username, None)
    return {"access_token": create_admin_token(user), "token_type": "bearer", "username": user.username, "role": user.role}


@router.post("/logout")
def logout(_: User = Depends(current_user)):
    # JWTs are stateless; the client discards the token. Kept for API symmetry.
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(current_user)):
    return {"username": user.username, "role": user.role}
