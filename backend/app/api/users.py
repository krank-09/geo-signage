from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..schemas import PasswordChangeIn, UserIn
from ..security import current_user, hash_secret, require_admin, verify_secret
from .deps import get_or_404

router = APIRouter(prefix="/users", tags=["users"])


def _out(u: User) -> dict:
    return {"id": u.id, "username": u.username, "role": u.role, "created_at": u.created_at}


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
def list_users(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return [_out(u) for u in db.query(User).order_by(User.id)]


@router.post("", status_code=201)
def create_user(body: UserIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    if db.query(User).filter(User.username == body.username).first():
        raise HTTPException(409, "Username already exists")
    user = User(username=body.username, password_hash=hash_secret(body.password), role=body.role)
    db.add(user)
    db.commit()
    return _out(user)


@router.delete("/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db), me: User = Depends(require_admin)):
    user = get_or_404(db, User, user_id, "User")
    if user.id == me.id:
        raise HTTPException(400, "You cannot delete yourself")
    db.delete(user)
    db.commit()
    return {"ok": True}
