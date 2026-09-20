import time

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import config
from ..database import get_db
from ..models import Client, User
from ..schemas import FirebaseLoginIn, LoginIn
from ..security import create_admin_token, current_user, verify_secret
from ..services import firebase

router = APIRouter(prefix="/auth", tags=["auth"])

_failures: dict[str, list[float]] = {}
MAX_FAILS, WINDOW = 5, 60


def _throttled(username: str) -> bool:
    now = time.time()
    recent = [t for t in _failures.get(username, []) if now - t < WINDOW]
    _failures[username] = recent
    return len(recent) >= MAX_FAILS


def _identity(user: User, db: Session) -> dict:
    client = db.get(Client, user.client_id) if user.client_id is not None else None
    return {"username": user.username, "role": user.role, "platform": user.client_id is None,
            "client_id": user.client_id, "client_name": client.name if client else None}


def _session(user: User, db: Session) -> dict:
    return {"access_token": create_admin_token(user), "token_type": "bearer", **_identity(user, db)}


@router.get("/config")
def auth_config():
    """What the login page needs to know. The Firebase web config is public by design (it is not a secret)."""
    fb = None
    if firebase.enabled():
        fb = {"apiKey": config.FIREBASE_API_KEY, "authDomain": config.FIREBASE_AUTH_DOMAIN,
              "projectId": config.FIREBASE_PROJECT_ID, "appId": config.FIREBASE_APP_ID,
              "emulatorHost": config.FIREBASE_AUTH_EMULATOR_HOST or None}
    return {"local_login": True, "firebase": fb}


def _username_for(db: Session, email: str) -> str:
    base = "".join(ch for ch in email.split("@")[0].lower() if ch.isalnum() or ch in "._-")[:40] or "user"
    if len(base) < 3:
        base += "user"
    name, n = base, 1
    while db.query(User).filter(User.username == name).first():
        n += 1
        name = f"{base}{n}"
    return name


@router.post("/firebase")
def firebase_login(body: FirebaseLoginIn, db: Session = Depends(get_db)):
    """Exchange a Firebase ID token for our own session token. New people start as `pending` until an admin approves
    them (or their verified email is in FIREBASE_ADMIN_EMAILS), so 'anyone with a Google account' is not an admin."""
    if not firebase.enabled():
        raise HTTPException(404, "Firebase sign-in is not configured on this server")
    try:
        claims = firebase.verify(body.id_token)
    except firebase.InvalidToken:
        raise HTTPException(401, "Invalid or expired Firebase sign-in")
    if not claims["email"]:
        raise HTTPException(403, "This Firebase account has no email address")
    if not claims["email_verified"]:
        raise HTTPException(403, "Verify your email address first (check your inbox), then sign in again")

    user = db.query(User).filter(User.firebase_uid == claims["uid"]).first()
    if user is None:
        # The same verified email under a new Firebase UID (account recreated, or a second sign-in provider): re-link
        # the existing person instead of creating a duplicate. The email is verified, so they demonstrably own it.
        user = db.query(User).filter(User.email == claims["email"]).first()
        if user is not None:
            user.firebase_uid = claims["uid"]
            db.commit()
    if user is None:
        role = "admin" if claims["email"] in config.FIREBASE_ADMIN_EMAILS else "pending"
        user = User(username=_username_for(db, claims["email"]), password_hash="!firebase", role=role,
                    email=claims["email"], firebase_uid=claims["uid"])
        db.add(user)
        db.commit()
    elif user.email != claims["email"]:
        user.email = claims["email"]
        db.commit()
    if user.role == "admin" or user.role == "viewer":
        return _session(user, db)
    raise HTTPException(403, "Your account is waiting for an administrator's approval")


@router.post("/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    if _throttled(body.username):
        raise HTTPException(429, "Too many failed attempts. Try again in a minute.")
    user = db.query(User).filter(User.username == body.username).first()
    if not user or not verify_secret(body.password, user.password_hash):
        _failures.setdefault(body.username, []).append(time.time())
        raise HTTPException(401, "Invalid username or password")
    _failures.pop(body.username, None)
    return _session(user, db)


@router.post("/logout")
def logout(_: User = Depends(current_user)):
    # JWTs are stateless; the client discards the token. Kept for API symmetry.
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _identity(user, db)
