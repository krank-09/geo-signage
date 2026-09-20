"""Content assignments (zone / group / time window / priority) and the emergency override built on them."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Assignment, Content, DeviceGroup, User, Zone
from ..realtime import announce_changes
from ..schemas import AssignmentIn
from ..security import current_user, require_admin
from .deps import get_or_404

router = APIRouter(tags=["assignments"])


def _out(a: Assignment) -> dict:
    return {
        "id": a.id, "content_id": a.content_id, "content_name": a.content.name, "content_type": a.content.type,
        "zone_id": a.zone_id, "zone_name": a.zone.name if a.zone else None,
        "group_id": a.group_id, "group_name": a.group.name if a.group else None,
        "start_time": a.start_time, "end_time": a.end_time, "priority": a.priority,
        "is_emergency": a.is_emergency, "active": a.active, "created_at": a.created_at,
    }


def _validate(db: Session, body: AssignmentIn) -> None:
    if not db.get(Content, body.content_id):
        raise HTTPException(400, "Unknown content")
    if body.zone_id is not None and not db.get(Zone, body.zone_id):
        raise HTTPException(400, "Unknown zone")
    if body.group_id is not None and not db.get(DeviceGroup, body.group_id):
        raise HTTPException(400, "Unknown group")
    if bool(body.start_time) != bool(body.end_time):
        raise HTTPException(400, "Provide both start_time and end_time, or neither")


def _create(db: Session, body: AssignmentIn) -> dict:
    _validate(db, body)
    a = Assignment(**body.model_dump())
    db.add(a)
    db.commit()
    db.refresh(a)
    announce_changes()
    return _out(a)


@router.get("/assignments")
def list_assignments(db: Session = Depends(get_db), _: User = Depends(current_user)):
    return [_out(a) for a in db.query(Assignment).order_by(Assignment.id.desc())]


@router.post("/assignments", status_code=201)
def create_assignment(body: AssignmentIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return _create(db, body)


@router.put("/assignments/{assignment_id}")
def update_assignment(assignment_id: int, body: AssignmentIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    a = get_or_404(db, Assignment, assignment_id, "Assignment")
    _validate(db, body)
    for k, v in body.model_dump().items():
        setattr(a, k, v)
    db.commit()
    db.refresh(a)
    announce_changes()
    return _out(a)


@router.delete("/assignments/{assignment_id}")
def delete_assignment(assignment_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    db.delete(get_or_404(db, Assignment, assignment_id, "Assignment"))
    db.commit()
    announce_changes()
    return {"ok": True}


# Convenience endpoints scoped to a zone
@router.post("/zones/{zone_id}/content", status_code=201)
def assign_to_zone(zone_id: int, body: AssignmentIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return _create(db, body.model_copy(update={"zone_id": zone_id}))


@router.delete("/zones/{zone_id}/content/{content_id}")
def unassign_from_zone(zone_id: int, content_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    removed = db.query(Assignment).filter(Assignment.zone_id == zone_id, Assignment.content_id == content_id).delete()
    db.commit()
    announce_changes()
    return {"ok": True, "removed": removed}


# Emergency override: an assignment that outranks everything else while active
@router.get("/emergency")
def list_emergency(db: Session = Depends(get_db), _: User = Depends(current_user)):
    active = db.query(Assignment).filter(Assignment.is_emergency.is_(True), Assignment.active.is_(True))
    return [_out(a) for a in active]


@router.post("/emergency", status_code=201)
def trigger_emergency(body: AssignmentIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """zone_id and group_id both empty = every device."""
    return _create(db, body.model_copy(update={"is_emergency": True, "active": True, "start_time": None, "end_time": None}))


@router.delete("/emergency")
def clear_emergency(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    cleared = db.query(Assignment).filter(Assignment.is_emergency.is_(True)).delete()
    db.commit()
    announce_changes()
    return {"ok": True, "cleared": cleared}
