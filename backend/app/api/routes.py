"""Routes: an ordered path for vehicle-mounted displays. Content can be assigned to a whole route or to one leg of it."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Assignment, Device, Route
from ..realtime import announce_changes, notify_admins
from ..schemas import RouteIn
from ..scope import Scope, get_scope, get_scoped, scoped, write_scope
from ..services import routes as route_service
from ..services.device_service import broadcast_device

router = APIRouter(tags=["routes"])


def _out(db: Session, r: Route) -> dict:
    devices = db.query(Device).filter(Device.route_id == r.id).order_by(Device.device_id).all()
    return {
        "id": r.id, "client_id": r.client_id, "name": r.name, "waypoints": r.waypoints, "corridor_km": r.corridor_km, "color": r.color,
        "legs": len(r.waypoints) - 1,
        "devices": [{"device_id": d.device_id, "name": d.name, **(route_service.status(d, r) or {})} for d in devices],
    }


@router.get("/routes")
def list_routes(db: Session = Depends(get_db), scope: Scope = Depends(get_scope)):
    return [_out(db, r) for r in scoped(db.query(Route), Route, scope).order_by(Route.name)]


@router.post("/routes", status_code=201)
def create_route(body: RouteIn, db: Session = Depends(get_db), scope: Scope = Depends(write_scope)):
    if db.query(Route).filter(Route.client_id == scope.client_id, Route.name == body.name).first():
        raise HTTPException(409, "A route with that name already exists")
    r = Route(client_id=scope.client_id, name=body.name, waypoints=[w.model_dump() for w in body.waypoints], corridor_km=body.corridor_km, color=body.color)
    db.add(r)
    db.commit()
    return _out(db, r)


@router.put("/routes/{route_id}")
def update_route(route_id: int, body: RouteIn, db: Session = Depends(get_db), scope: Scope = Depends(write_scope)):
    r = get_scoped(db, Route, route_id, scope, "Route")
    clash = db.query(Route).filter(Route.client_id == scope.client_id, Route.name == body.name, Route.id != r.id).first()
    if clash:
        raise HTTPException(409, "A route with that name already exists")
    if len(body.waypoints) - 1 < max((a.route_leg + 1 for a in db.query(Assignment).filter(Assignment.route_id == r.id, Assignment.route_leg.isnot(None))), default=0):
        raise HTTPException(409, "Content is assigned to a leg that this shorter route no longer has. Remove that assignment first.")
    r.name, r.corridor_km, r.color = body.name, body.corridor_km, body.color
    r.waypoints = [w.model_dump() for w in body.waypoints]
    devices = db.query(Device).filter(Device.route_id == r.id).all()
    for d in devices:
        route_service.track(db, d)
    db.commit()
    for d in devices:
        broadcast_device(d)
    announce_changes("assignments", r.client_id)
    return _out(db, r)


@router.delete("/routes/{route_id}")
def delete_route(route_id: int, db: Session = Depends(get_db), scope: Scope = Depends(write_scope)):
    r = get_scoped(db, Route, route_id, scope, "Route")
    devices = db.query(Device).filter(Device.route_id == r.id).all()
    for d in devices:
        d.route_id = None
        route_service.track(db, d)
    removed = db.query(Assignment).filter(Assignment.route_id == r.id).delete()
    client_id = r.client_id
    db.delete(r)
    db.commit()
    for d in devices:
        broadcast_device(d)
    notify_admins("assignments_changed", client_id)
    announce_changes("assignments", client_id)
    return {"ok": True, "assignments_removed": removed}
