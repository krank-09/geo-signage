"""Small helpers shared by the routers."""
from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..models import Device


def get_or_404(db: Session, model, ident, what: str):
    obj = db.get(model, ident)
    if obj is None:
        raise HTTPException(404, f"{what} not found")
    return obj


def get_device_or_404(db: Session, device_id: str) -> Device:
    device = db.query(Device).filter(Device.device_id == device_id).first()
    if device is None:
        raise HTTPException(404, "Device not found")
    return device
