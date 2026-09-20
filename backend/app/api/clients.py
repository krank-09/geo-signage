"""Clients (customers). Platform admins manage them all; a client's own users can see their client and rotate its enrollment key."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Alert, Assignment, Broadcast, Client, Content, Device, DeviceGroup, TamperEvent, User, Zone
from ..schemas import ClientIn, ClientUpdate
from ..scope import platform_admin
from ..security import current_user, require_admin
from ..services.clients import create_client, new_enrollment_key
from ..services.device_service import is_online

router = APIRouter(prefix="/clients", tags=["clients"])


def _out(db: Session, c: Client, with_key: bool) -> dict:
    devices = db.query(Device).filter(Device.client_id == c.id).all()
    return {
        "id": c.id, "name": c.name, "slug": c.slug, "active": c.active, "device_limit": c.device_limit, "created_at": c.created_at,
        "enrollment_key": c.enrollment_key if with_key else None,
        "devices": len(devices), "devices_online": sum(1 for d in devices if is_online(d)),
        "tampered": sum(1 for d in devices if d.tamper_state == "flagged"),
        "content": db.query(Content).filter(Content.client_id == c.id).count(),
        "zones": db.query(Zone).filter(Zone.client_id == c.id).count(),
        "users": db.query(User).filter(User.client_id == c.id).count(),
    }


@router.get("")
def list_clients(db: Session = Depends(get_db), me: User = Depends(current_user)):
    q = db.query(Client).order_by(Client.name)
    if me.client_id is not None:
        q = q.filter(Client.id == me.client_id)
    # enrollment keys are only shown to administrators (they let a display join that client)
    return [_out(db, c, with_key=me.role == "admin") for c in q]


@router.post("", status_code=201)
def add_client(body: ClientIn, db: Session = Depends(get_db), _: User = Depends(platform_admin)):
    if db.query(Client).filter(Client.name == body.name.strip()).first():
        raise HTTPException(409, "A client with that name already exists")
    c = create_client(db, body.name, body.device_limit)
    db.commit()
    return _out(db, c, with_key=True)


@router.put("/{client_id}")
def update_client(client_id: int, body: ClientUpdate, db: Session = Depends(get_db), _: User = Depends(platform_admin)):
    c = db.get(Client, client_id)
    if c is None:
        raise HTTPException(404, "Client not found")
    if body.name is not None:
        clash = db.query(Client).filter(Client.name == body.name.strip(), Client.id != client_id).first()
        if clash:
            raise HTTPException(409, "A client with that name already exists")
        c.name = body.name.strip()
    if body.active is not None:
        c.active = body.active
    if body.clear_device_limit:
        c.device_limit = None
    elif body.device_limit is not None:
        c.device_limit = body.device_limit
    db.commit()
    return _out(db, c, with_key=True)


@router.post("/{client_id}/rotate-key")
def rotate_key(client_id: int, db: Session = Depends(get_db), me: User = Depends(require_admin)):
    """New enrollment key: displays still holding the old one can no longer announce themselves to this client."""
    if me.client_id is not None and me.client_id != client_id:
        raise HTTPException(404, "Client not found")
    c = db.get(Client, client_id)
    if c is None:
        raise HTTPException(404, "Client not found")
    c.enrollment_key = new_enrollment_key()
    db.commit()
    return {"id": c.id, "enrollment_key": c.enrollment_key}


@router.delete("/{client_id}")
def delete_client(client_id: int, db: Session = Depends(get_db), _: User = Depends(platform_admin)):
    c = db.get(Client, client_id)
    if c is None:
        raise HTTPException(404, "Client not found")
    if db.query(Client).count() <= 1:
        raise HTTPException(409, "You cannot delete the only client")
    owned = sum(db.query(m).filter(m.client_id == client_id).count() for m in (Device, Content, Zone, DeviceGroup, Assignment, User))
    if owned:
        raise HTTPException(409, "This client still has data. Suspend it instead, or remove its devices, content and users first.")
    for history in (Broadcast, Alert, TamperEvent):        # nothing live is left, only the record of what happened
        db.query(history).filter(history.client_id == client_id).delete()
    db.delete(c)
    db.commit()
    return {"ok": True}
