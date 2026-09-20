from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Client, User
from ..schemas import PasswordChangeIn, RoleIn, UserIn
from ..security import current_user, hash_secret, require_admin, verify_secret
from .deps import get_or_404

router = APIRouter(prefix="/users", tags=["users"])


def _out(u: User, names: dict[int, str]) -> dict:
    return {"id": u.id, "username": u.username, "role": u.role, "created_at": u.created_at, "email": u.email,
            "source": "firebase" if u.firebase_uid else "local", "client_id": u.client_id,
            "client_name": names.get(u.client_id) if u.client_id is not None else None}


def _names(db: Session) -> dict[int, str]:
    return {c.id: c.name for c in db.query(Client)}


def _visible(db: Session, me: User, user_id: int) -> User:
    """A client admin only ever sees (and can only touch) people in their own client; anything else is a 404."""
    user = get_or_404(db, User, user_id, "User")
    if me.client_id is not None and user.client_id != me.client_id:
        raise HTTPException(404, "User not found")
    return user


@router.post("/me/password")
def change_password(body: PasswordChangeIn, db: Session = Depends(get_db), me: User = Depends(current_user)):
    if not verify_secret(body.current_password, me.password_hash):
        raise HTTPException(400, "Current password is incorrect")
    if body.new_password == body.current_password:
        raise HTTPException(400, "New password must differ from the current one")
    me.password_hash = hash_secret(body.new_password)
    db.commit()
    return {"ok": True}


@router.get("")
def list_users(db: Session = Depends(get_db), me: User = Depends(require_admin)):
    q = db.query(User)
    if me.client_id is not None:
        q = q.filter(User.client_id == me.client_id)
    names = _names(db)
    return [_out(u, names) for u in q.order_by(User.id)]


@router.post("", status_code=201)
def create_user(body: UserIn, db: Session = Depends(get_db), me: User = Depends(require_admin)):
    if db.query(User).filter(User.username == body.username).first():
        raise HTTPException(409, "Username already exists")
    client_id = me.client_id if me.client_id is not None else body.client_id     # client admins cannot place users elsewhere
    if client_id is not None and db.get(Client, client_id) is None:
        raise HTTPException(400, "Unknown client")
    user = User(username=body.username, password_hash=hash_secret(body.password), role=body.role, client_id=client_id)
    db.add(user)
    db.commit()
    return _out(user, _names(db))


@router.put("/{user_id}/role")
def set_role(user_id: int, body: RoleIn, db: Session = Depends(get_db), me: User = Depends(require_admin)):
    """Approve a pending person (viewer/admin) or change someone's role. Only platform admins can move people between clients."""
    user = _visible(db, me, user_id)
    if user.id == me.id:
        raise HTTPException(400, "You cannot change your own role")
    if body.client_id is not None and me.client_id is None:
        if db.get(Client, body.client_id) is None:
            raise HTTPException(400, "Unknown client")
        user.client_id = body.client_id
    user.role = body.role
    db.commit()
    return _out(user, _names(db))


@router.delete("/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db), me: User = Depends(require_admin)):
    user = _visible(db, me, user_id)
    if user.id == me.id:
        raise HTTPException(400, "You cannot delete yourself")
    db.delete(user)
    db.commit()
    return {"ok": True}
