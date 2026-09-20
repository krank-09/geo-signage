from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Assignment, Device, User, Zone
from ..schemas import ZoneIn
from ..security import current_user, require_admin
from ..services.zone_service import relocate_devices
from .deps import get_or_404

router = APIRouter(prefix="/zones", tags=["zones"])


def _out(z: Zone) -> dict:
    return {"id": z.id, "name": z.name, "polygon": z.polygon, "priority": z.priority, "color": z.color}


def _ensure_unique_name(db: Session, name: str, ignore_id: int | None = None) -> None:
    q = db.query(Zone).filter(Zone.name == name)
    if ignore_id is not None:
        q = q.filter(Zone.id != ignore_id)
    if q.first():
        raise HTTPException(409, "Zone name already exists")


@router.get("")
def list_zones(db: Session = Depends(get_db), _: User = Depends(current_user)):
    return [_out(z) for z in db.query(Zone).order_by(Zone.id)]


@router.post("", status_code=201)
def create_zone(body: ZoneIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    _ensure_unique_name(db, body.name)
    z = Zone(**body.model_dump())
    db.add(z)
    db.commit()
    relocate_devices(db)
    return _out(z)


@router.put("/{zone_id}")
def update_zone(zone_id: int, body: ZoneIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    z = get_or_404(db, Zone, zone_id, "Zone")
    _ensure_unique_name(db, body.name, ignore_id=zone_id)
    for k, v in body.model_dump().items():
        setattr(z, k, v)
    db.commit()
    relocate_devices(db)
    return _out(z)


@router.delete("/{zone_id}")
def delete_zone(zone_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    z = get_or_404(db, Zone, zone_id, "Zone")
    db.query(Device).filter(Device.current_zone_id == zone_id).update({Device.current_zone_id: None})
    db.query(Assignment).filter(Assignment.zone_id == zone_id).delete()
    db.delete(z)
    db.commit()
    relocate_devices(db)
    return {"ok": True}
