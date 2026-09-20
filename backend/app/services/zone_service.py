from sqlalchemy.orm import Session

from ..models import Device, Zone
from ..realtime import announce_changes
from .device_service import broadcast_device, update_location


def relocate_devices(db: Session, client_id: int | None) -> None:
    """Zone geometry changed: re-locate that client's devices against its new polygons, then tell its dashboards and displays."""
    zones = db.query(Zone).filter(Zone.client_id == client_id).all()
    devices = db.query(Device).filter(Device.client_id == client_id).all()
    for d in devices:
        if d.latitude is not None:
            update_location(db, d, d.latitude, d.longitude, zones)
    db.commit()
    for d in devices:
        broadcast_device(d)
    announce_changes("assignments", client_id)
