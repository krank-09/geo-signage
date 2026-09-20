"""Predefined cities: pick a city and get its zone instantly instead of drawing the boundary by hand."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User, Zone
from ..schemas import CityZoneIn
from ..security import current_user, require_admin
from ..services import cities
from ..services.zone_service import relocate_devices
from .zones import _out as zone_out

router = APIRouter(prefix="/cities", tags=["cities"])


def _get(city_id: str) -> dict:
    c = cities.get_city(city_id)
    if c is None:
        raise HTTPException(404, "City not found")
    return c


@router.get("")
def list_cities(q: str = "", db: Session = Depends(get_db), _: User = Depends(current_user)):
    """All cities (optionally filtered by name or state), flagged with whether a zone for them already exists."""
    existing = {z.name for z in db.query(Zone)}
    needle = q.strip().lower()
    return [
        {**cities.summary(c), "zone_exists": f"{c['name']} Zone" in existing}
        for c in cities.all_cities()
        if not needle or needle in c["name"].lower() or needle in c["state"].lower()
    ]


@router.get("/{city_id}")
def get_city(city_id: str, _: User = Depends(current_user)):
    return _get(city_id)  # includes the polygon, for previewing the boundary on the map


@router.post("/{city_id}/zone", status_code=201)
def create_zone_from_city(city_id: str, body: CityZoneIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    c = _get(city_id)
    name = body.name or f"{c['name']} Zone"
    if db.query(Zone).filter(Zone.name == name).first():
        raise HTTPException(409, f"A zone named '{name}' already exists")
    zone = Zone(name=name, polygon=c["polygon"], priority=body.priority, color=body.color)
    db.add(zone)
    db.commit()
    relocate_devices(db)
    return zone_out(zone)
