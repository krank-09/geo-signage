from sqlalchemy.orm import Session

from ..models import Device, Zone
from ..realtime import announce_changes
from .device_service import broadcast_device, update_location


def relocate_devices(db: Session) -> None:
    """Zone geometry changed: re-locate every device against the new polygons, then tell everyone."""
    zones = db.query(Zone).all()
    devices = db.query(Device).all()
    for d in devices:
        if d.latitude is not None:
            update_location(db, d, d.latitude, d.longitude, zones)
    db.commit()
    for d in devices:
        broadcast_device(d)
    announce_changes()
