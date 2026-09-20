"""Discovery: unclaimed display agents announce themselves; admins list and claim them when adding a device."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User, Zone
from ..schemas import AnnounceIn
from ..security import current_user
from ..services import cities, discovery
from ..services.geo import point_in_polygon
from .deps import get_or_404

router = APIRouter(prefix="/discovery", tags=["discovery"])


@router.post("/announce")
def announce(body: AnnounceIn):
    """Called by agents that have no device identity yet. No login: possession of `secret` is the credential."""
    info = {"name": body.name, "latitude": body.latitude, "longitude": body.longitude,
            "connection_type": body.connection_type, "software_version": body.software_version}
    try:
        return discovery.announce(body.secret, info)
    except discovery.TooManyAgents:
        raise HTTPException(429, "Too many unclaimed displays are announcing right now")


@router.get("/agents")
def list_agents(zone_id: int | None = None, city_id: str | None = None, db: Session = Depends(get_db), _: User = Depends(current_user)):
    """Unclaimed agents currently announcing, optionally only those located inside a zone or a city."""
    polygon, area_name = None, None
    if zone_id is not None:
        z = get_or_404(db, Zone, zone_id, "Zone")
        polygon, area_name = z.polygon, z.name
    elif city_id:
        c = cities.get_city(city_id)
        if c is None:
            raise HTTPException(404, "City not found")
        polygon, area_name = c["polygon"], c["name"]
    zones = db.query(Zone).all()
    out = []
    for a in discovery.list_agents():
        located = a["latitude"] is not None and a["longitude"] is not None
        if polygon is not None and not (located and point_in_polygon(a["latitude"], a["longitude"], polygon)):
            continue
        inside = [z.name for z in zones if located and point_in_polygon(a["latitude"], a["longitude"], z.polygon)]
        out.append({**a, "zones": inside})
    return {"area": area_name, "agents": out}
