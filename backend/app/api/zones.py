from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Assignment, Device, Zone
from ..schemas import ZoneIn
from ..scope import Scope, get_scope, get_scoped, scoped, write_scope
from ..services.zone_service import relocate_devices

router = APIRouter(prefix="/zones", tags=["zones"])


def _out(z: Zone) -> dict:
    return {"id": z.id, "client_id": z.client_id, "name": z.name, "polygon": z.polygon, "priority": z.priority, "color": z.color}


def _ensure_unique_name(db: Session, name: str, client_id: int, ignore_id: int | None = None) -> None:
    q = db.query(Zone).filter(Zone.name == name, Zone.client_id == client_id)   # names only need to be unique within a client
    if ignore_id is not None:
        q = q.filter(Zone.id != ignore_id)
    if q.first():
        raise HTTPException(409, "Zone name already exists")


@router.get("")
def list_zones(db: Session = Depends(get_db), scope: Scope = Depends(get_scope)):
    return [_out(z) for z in scoped(db.query(Zone), Zone, scope).order_by(Zone.id)]


@router.post("", status_code=201)
def create_zone(body: ZoneIn, db: Session = Depends(get_db), scope: Scope = Depends(write_scope)):
    _ensure_unique_name(db, body.name, scope.client_id)
    z = Zone(client_id=scope.client_id, **body.model_dump())
    db.add(z)
    db.commit()
    relocate_devices(db, scope.client_id)
    return _out(z)


@router.put("/{zone_id}")
def update_zone(zone_id: int, body: ZoneIn, db: Session = Depends(get_db), scope: Scope = Depends(write_scope)):
    z = get_scoped(db, Zone, zone_id, scope, "Zone")
    _ensure_unique_name(db, body.name, scope.client_id, ignore_id=zone_id)
    for k, v in body.model_dump().items():
        setattr(z, k, v)
    db.commit()
    relocate_devices(db, scope.client_id)
    return _out(z)


@router.delete("/{zone_id}")
def delete_zone(zone_id: int, db: Session = Depends(get_db), scope: Scope = Depends(write_scope)):
    z = get_scoped(db, Zone, zone_id, scope, "Zone")
    db.query(Device).filter(Device.current_zone_id == zone_id).update({Device.current_zone_id: None})
    db.query(Assignment).filter(Assignment.zone_id == zone_id).delete()
    db.delete(z)
    db.commit()
    relocate_devices(db, scope.client_id)
    return {"ok": True}
