"""Client isolation. Every request resolves to a Scope; every query and lookup goes through it.

* A client user (users.client_id set) is pinned to that client. Any X-Client-Id header is ignored.
* A platform user (client_id NULL) may send X-Client-Id to act inside one client. With no header they see all clients
  (read-only aggregates), except that if the platform has exactly one client it is used implicitly, so a single-customer
  installation behaves as it always did. Writes need a concrete client.
* Looking up an object by ID from another client is a 404, never a 403, so IDs cannot be probed.
"""
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from .database import get_db
from .models import Client, Device, User
from .security import current_user


@dataclass
class Scope:
    user: User
    client_id: int | None            # None = all clients (platform users only)

    @property
    def platform(self) -> bool:
        return self.user.client_id is None

    @property
    def is_admin(self) -> bool:
        return self.user.role == "admin"


def resolve_scope(user: User, header: str | None, db: Session) -> Scope:
    if user.client_id is not None:
        client = db.get(Client, user.client_id)
        if client is None or not client.active:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "This client account is suspended")
        return Scope(user, user.client_id)
    if header:
        try:
            client = db.get(Client, int(header))
        except ValueError:
            client = None
        if client is None:
            raise HTTPException(404, "Client not found")
        return Scope(user, client.id)
    ids = [c.id for c in db.query(Client.id).limit(2)]
    return Scope(user, ids[0] if len(ids) == 1 else None)


def get_scope(user: User = Depends(current_user), x_client_id: str | None = Header(None), db: Session = Depends(get_db)) -> Scope:
    return resolve_scope(user, x_client_id, db)


def write_scope(scope: Scope = Depends(get_scope)) -> Scope:
    """An administrator acting inside one concrete client."""
    if not scope.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Administrator role required")
    if scope.client_id is None:
        raise HTTPException(400, "Select a client first")
    return scope


def platform_admin(user: User = Depends(current_user)) -> User:
    if user.role != "admin" or user.client_id is not None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Platform administrator required")
    return user


def scoped(query, model, scope: Scope):
    return query if scope.client_id is None else query.filter(model.client_id == scope.client_id)


def get_scoped(db: Session, model, ident, scope: Scope, what: str):
    obj = db.get(model, ident)
    if obj is None or (scope.client_id is not None and obj.client_id != scope.client_id):
        raise HTTPException(404, f"{what} not found")
    return obj


def get_scoped_device(db: Session, device_id: str, scope: Scope) -> Device:
    d = db.query(Device).filter(Device.device_id == device_id).first()
    if d is None or (scope.client_id is not None and d.client_id != scope.client_id):
        raise HTTPException(404, "Device not found")
    return d


def scoped_device_ids(db: Session, scope: Scope) -> list[str] | None:
    """None means 'no restriction' (platform, all clients)."""
    if scope.client_id is None:
        return None
    return [d for (d,) in db.query(Device.device_id).filter(Device.client_id == scope.client_id)]
