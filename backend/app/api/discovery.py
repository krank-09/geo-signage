"""Discovery: unclaimed display agents announce themselves; admins list and claim them when adding a device.

An agent may present its client's enrollment key. Then it is visible only to that client (and platform admins);
without a key it lands in an unassigned pool that only platform admins can see and claim."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Client, Zone
from ..schemas import AnnounceIn
from ..scope import Scope, get_scope, get_scoped
from ..services import cities, discovery
from ..services.geo import point_in_polygon

router = APIRouter(prefix="/discovery", tags=["discovery"])


@router.post("/announce")
def announce(body: AnnounceIn, db: Session = Depends(get_db)):
    """Called by agents that have no device identity yet. No login: possession of `secret` is the credential."""
    client_id = None
    if body.enrollment_key:
        client = db.query(Client).filter(Client.enrollment_key == body.enrollment_key).first()
        if client is None or not client.active:
            raise HTTPException(403, "Invalid enrollment key")
        client_id = client.id
    info = {"name": body.name, "latitude": body.latitude, "longitude": body.longitude, "client_id": client_id,
            "connection_type": body.connection_type, "software_version": body.software_version}
    try:
        return discovery.announce(body.secret, info)
    except discovery.TooManyAgents:
        raise HTTPException(429, "Too many unclaimed displays are announcing right now")


@router.get("/agents")
def list_agents(zone_id: int | None = None, city_id: str | None = None, db: Session = Depends(get_db), scope: Scope = Depends(get_scope)):
    """Unclaimed agents currently announcing, optionally only those located inside a zone or a city."""
    polygon, area_name = None, None
    if zone_id is not None:
        z = get_scoped(db, Zone, zone_id, scope, "Zone")
        polygon, area_name = z.polygon, z.name
    elif city_id:
        c = cities.get_city(city_id)
        if c is None:
            raise HTTPException(404, "City not found")
        polygon, area_name = c["polygon"], c["name"]
    zones = [z for z in db.query(Zone).filter(Zone.client_id == scope.client_id)] if scope.client_id is not None else db.query(Zone).all()
    if scope.client_id is None:                     # platform user looking at everything
        visible = discovery.list_agents(everything=True)
    elif scope.platform:                            # platform user acting inside one client: that client + the unassigned pool
        visible = discovery.list_agents(scope.client_id) + discovery.list_agents(None)
    else:                                           # client user: their own client's displays only
        visible = discovery.list_agents(scope.client_id, include_unassigned=False)
    out = []
    for a in visible:
        located = a["latitude"] is not None and a["longitude"] is not None
        if polygon is not None and not (located and point_in_polygon(a["latitude"], a["longitude"], polygon)):
            continue
        inside = [z.name for z in zones if located and point_in_polygon(a["latitude"], a["longitude"], z.polygon)]
        out.append({**a, "zones": inside})
    return {"area": area_name, "agents": out}
