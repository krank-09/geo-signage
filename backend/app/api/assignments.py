"""Content assignments (zone / group / time window / priority) and the emergency override built on them."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Assignment, Content, DeviceGroup, Route, Zone
from ..realtime import announce_changes
from ..schemas import AssignmentIn
from ..scope import Scope, get_scope, get_scoped, scoped, write_scope

router = APIRouter(tags=["assignments"])


def _out(a: Assignment) -> dict:
    return {
        "id": a.id, "client_id": a.client_id, "content_id": a.content_id, "content_name": a.content.name, "content_type": a.content.type,
        "zone_id": a.zone_id, "zone_name": a.zone.name if a.zone else None,
        "group_id": a.group_id, "group_name": a.group.name if a.group else None,
        "route_id": a.route_id, "route_name": a.route.name if a.route else None, "route_leg": a.route_leg,
        "start_time": a.start_time, "end_time": a.end_time, "priority": a.priority,
        "is_emergency": a.is_emergency, "active": a.active, "created_at": a.created_at,
    }


def _validate(db: Session, body: AssignmentIn, scope: Scope) -> None:
    """Everything referenced must belong to the caller's client. A foreign id gets the same answer as an unknown one."""
    def owned(model, ident) -> bool:
        obj = db.get(model, ident)
        return obj is not None and obj.client_id == scope.client_id

    if not owned(Content, body.content_id):
        raise HTTPException(400, "Unknown content")
    if body.zone_id is not None and not owned(Zone, body.zone_id):
        raise HTTPException(400, "Unknown zone")
    if body.group_id is not None and not owned(DeviceGroup, body.group_id):
        raise HTTPException(400, "Unknown group")
    if body.route_id is not None and not owned(Route, body.route_id):
        raise HTTPException(400, "Unknown route")
    if body.route_leg is not None:
        route = db.get(Route, body.route_id) if body.route_id is not None else None
        if route is None:
            raise HTTPException(400, "A route leg needs a route")
        if body.route_leg >= len(route.waypoints) - 1:
            raise HTTPException(400, f"That route has {len(route.waypoints) - 1} legs")
    if bool(body.start_time) != bool(body.end_time):
        raise HTTPException(400, "Provide both start_time and end_time, or neither")


def _create(db: Session, body: AssignmentIn, scope: Scope) -> dict:
    _validate(db, body, scope)
    a = Assignment(client_id=scope.client_id, **body.model_dump())
    db.add(a)
    db.commit()
    db.refresh(a)
    announce_changes("assignments", scope.client_id)
    return _out(a)


@router.get("/assignments")
def list_assignments(db: Session = Depends(get_db), scope: Scope = Depends(get_scope)):
    return [_out(a) for a in scoped(db.query(Assignment), Assignment, scope).order_by(Assignment.id.desc())]


@router.post("/assignments", status_code=201)
def create_assignment(body: AssignmentIn, db: Session = Depends(get_db), scope: Scope = Depends(write_scope)):
    return _create(db, body, scope)


@router.put("/assignments/{assignment_id}")
def update_assignment(assignment_id: int, body: AssignmentIn, db: Session = Depends(get_db), scope: Scope = Depends(write_scope)):
    a = get_scoped(db, Assignment, assignment_id, scope, "Assignment")
    _validate(db, body, scope)
    for k, v in body.model_dump().items():
        setattr(a, k, v)
    db.commit()
    db.refresh(a)
    announce_changes("assignments", scope.client_id)
    return _out(a)


@router.delete("/assignments/{assignment_id}")
def delete_assignment(assignment_id: int, db: Session = Depends(get_db), scope: Scope = Depends(write_scope)):
    db.delete(get_scoped(db, Assignment, assignment_id, scope, "Assignment"))
    db.commit()
    announce_changes("assignments", scope.client_id)
    return {"ok": True}


# Convenience endpoints scoped to a zone
@router.post("/zones/{zone_id}/content", status_code=201)
def assign_to_zone(zone_id: int, body: AssignmentIn, db: Session = Depends(get_db), scope: Scope = Depends(write_scope)):
    return _create(db, body.model_copy(update={"zone_id": zone_id}), scope)


@router.delete("/zones/{zone_id}/content/{content_id}")
def unassign_from_zone(zone_id: int, content_id: int, db: Session = Depends(get_db), scope: Scope = Depends(write_scope)):
    get_scoped(db, Zone, zone_id, scope, "Zone")
    removed = db.query(Assignment).filter(Assignment.zone_id == zone_id, Assignment.content_id == content_id,
                                          Assignment.client_id == scope.client_id).delete()
    db.commit()
    announce_changes("assignments", scope.client_id)
    return {"ok": True, "removed": removed}


# Emergency override: an assignment that outranks everything else while active
@router.get("/emergency")
def list_emergency(db: Session = Depends(get_db), scope: Scope = Depends(get_scope)):
    active = scoped(db.query(Assignment), Assignment, scope).filter(Assignment.is_emergency.is_(True), Assignment.active.is_(True))
    return [_out(a) for a in active]


@router.post("/emergency", status_code=201)
def trigger_emergency(body: AssignmentIn, db: Session = Depends(get_db), scope: Scope = Depends(write_scope)):
    """zone_id and group_id both empty = every device of this client."""
    return _create(db, body.model_copy(update={"is_emergency": True, "active": True, "start_time": None, "end_time": None}), scope)


@router.delete("/emergency")
def clear_emergency(db: Session = Depends(get_db), scope: Scope = Depends(write_scope)):
    cleared = db.query(Assignment).filter(Assignment.is_emergency.is_(True), Assignment.client_id == scope.client_id).delete()
    db.commit()
    announce_changes("assignments", scope.client_id)
    return {"ok": True, "cleared": cleared}
