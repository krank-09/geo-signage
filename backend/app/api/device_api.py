"""Endpoints called by device agents (device-token auth)."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from .. import config
from ..database import get_db
from ..models import Client, Content, Device, Impression, Zone, utcnow
from ..schemas import HeartbeatIn, ImpressionsIn, LocationIn, RegisterIn, TamperBatchIn
from ..security import create_device_token, current_device, verify_secret
from ..services import broadcasts as live
from ..services import deviceauth, fleet, manifest, tamper
from ..services.device_service import add_log, broadcast_device, effective_config, touch, update_location
from ..services.media import ensure_hash, stream_content
from ..services.resolver import resolve
from .deps import get_or_404

router = APIRouter(prefix="/device", tags=["device"])


def _own(device: Device, device_id: str) -> Device:
    if device.device_id != device_id:
        raise HTTPException(403, "Token does not belong to this device")
    return device


def _with_broadcasts(db: Session, device: Device, r: dict) -> tuple[str, list[dict]]:
    """Combined version = playlist hash + broadcast hash, so starting/ending/expiring a broadcast is noticed on the next
    heartbeat or location reply even if the push was missed."""
    items = live.active_for_device(db, device, set(r["zone_ids"]))
    return r["manifest_version"] + live.version(items), items


def _sync_state(db: Session, device: Device, zones: list[Zone] | None = None) -> dict:
    r = resolve(db, device, zones=zones)
    version, _ = _with_broadcasts(db, device, r)
    return {
        "ok": True,
        "server_time": datetime.now(timezone.utc).isoformat(),
        "manifest_version": version,
        "zone": r["zone"],
        "config": effective_config(device),
    }


def _bind_identity(db: Session, device: Device, body: RegisterIn, request: Request, sig: deviceauth.SigInfo) -> None:
    """Bind the display's Ed25519 key on first registration; afterwards the same key must come back.
    The registration request itself is signed with the new key, which proves the display really holds it."""
    if not body.public_key:
        if device.public_key:
            tamper.record(db, device, "unsigned_downgrade", "Registration without the bound identity key", "critical", "server")
            raise HTTPException(409, "This device is bound to an identity key and must register with it")
        if config.DEVICE_AUTH_MODE == "required":
            raise HTTPException(400, "This server requires displays to hold an identity key; update the display agent")
        return
    try:
        deviceauth.public_key_from_b64(body.public_key)
        deviceauth.verify_request(device.device_id, body.public_key, sig)
    except (ValueError, deviceauth.SignatureError):
        raise HTTPException(400, "Registration must be signed with the identity key it presents")
    if device.public_key and device.public_key != body.public_key:
        tamper.record(db, device, "clone_attempt", "Registration with valid credentials but a different identity key", "critical", "server")
        raise HTTPException(409, "This device is already bound to another machine. An administrator must reset its credentials.")
    if device.public_key is None:
        device.public_key, device.key_bound_at = body.public_key, utcnow()
        add_log(db, device.device_id, "register", "Identity key bound to this display")
    if body.hw_fingerprint:
        if device.hw_fingerprint and device.hw_fingerprint != body.hw_fingerprint:
            tamper.record(db, device, "hw_fingerprint_changed", "Same key, different hardware fingerprint (disk image moved to other hardware?)", "critical", "server")
        device.hw_fingerprint = device.hw_fingerprint or body.hw_fingerprint


@router.post("/register")
async def register(body: RegisterIn, request: Request, db: Session = Depends(get_db)):
    device = db.query(Device).filter(Device.device_id == body.device_id).first()
    # Same error for unknown device / bad token so IDs cannot be enumerated.
    if not device or not verify_secret(body.registration_token, device.registration_token_hash):
        raise HTTPException(401, "Invalid device ID or registration token")
    client = db.get(Client, device.client_id) if device.client_id is not None else None
    if client is not None and not client.active:
        raise HTTPException(403, "This client account is suspended")
    sig = deviceauth.SigInfo(request.headers.get("x-signature"), request.headers.get("x-timestamp"), request.headers.get("x-nonce"),
                             request.method, request.url.path, deviceauth.sha256_hex(await request.body()))
    _bind_identity(db, device, body, request, sig)
    device.registered_at = utcnow()
    device.token_version += 1  # a re-registration invalidates older credentials
    fleet.apply_inventory(db, device, body)
    touch(db, device)
    add_log(db, device.device_id, "register", "Device registered")
    db.commit()
    broadcast_device(device)
    return {"access_token": create_device_token(device), "token_type": "bearer", "device_id": device.device_id,
            "config": effective_config(device), "server_public_key": manifest.public_key_b64(db),
            "signed": bool(device.public_key)}


@router.post("/heartbeat")
def heartbeat(body: HeartbeatIn, db: Session = Depends(get_db), device: Device = Depends(current_device)):
    touch(db, device)
    fleet.apply_inventory(db, device, body)
    for field in ("cpu", "memory", "network"):
        v = getattr(body, field)
        if v is not None:
            setattr(device, field, v)
    if body.gps is not None:
        device.gps_ok = body.gps
    if body.content_version is not None:
        device.current_content_version = body.content_version
        device.current_content_names = (body.content_names or "")[:500]
    zones = db.query(Zone).filter(Zone.client_id == device.client_id).all()
    if body.latitude is not None and body.longitude is not None:
        update_location(db, device, body.latitude, body.longitude, zones)
    db.commit()
    broadcast_device(device)
    return _sync_state(db, device, zones)


@router.post("/location")
def location(body: LocationIn, db: Session = Depends(get_db), device: Device = Depends(current_device)):
    if body.device_id and body.device_id != device.device_id:
        raise HTTPException(403, "Token does not belong to this device")
    touch(db, device)
    device.gps_ok = True
    zones = db.query(Zone).filter(Zone.client_id == device.client_id).all()
    update_location(db, device, body.latitude, body.longitude, zones)
    db.commit()
    broadcast_device(device)
    return _sync_state(db, device, zones)


@router.get("/{device_id}/configuration")
def configuration(device_id: str, device: Device = Depends(current_device)):
    _own(device, device_id)
    return {
        "device_id": device.device_id,
        "config": effective_config(device),
        "offline_threshold_seconds": config.OFFLINE_THRESHOLD_SECONDS,
        "server_time": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/{device_id}/content")
def content(device_id: str, db: Session = Depends(get_db), device: Device = Depends(current_device)):
    _own(device, device_id)
    r = resolve(db, device)
    for item in r["items"]:
        item["url"] = f"/device/{device.device_id}/media/{item['content_id']}"
    for item in r["items"]:
        if not item.get("sha256"):
            item["sha256"] = ensure_hash(db, db.get(Content, item["content_id"]))
    version, items = _with_broadcasts(db, device, r)
    body = {**r, "manifest_version": version, "broadcasts": items, "config": effective_config(device)}
    # The signed copy is what a display trusts; the plain fields stay for older agents.
    return {**body, "signed": manifest.sign_manifest(db, jsonable_encoder({"device_id": device.device_id, **body}))}


@router.get("/{device_id}/media/{content_id}")
def media(device_id: str, content_id: int, request: Request, db: Session = Depends(get_db),
          device: Device = Depends(current_device)):
    _own(device, device_id)
    c = get_or_404(db, Content, content_id, "Content")
    if c.client_id != device.client_id:
        raise HTTPException(404, "Content not found")     # never serve another client's files, whatever the id
    return stream_content(c, request)


@router.post("/tamper")
def report_tamper(body: TamperBatchIn, db: Session = Depends(get_db), device: Device = Depends(current_device)):
    """Self-reported detections (modified cache, hash mismatch, clock rollback ...). Unknown kinds are kept as warnings."""
    recorded = 0
    for e in body.events:
        severity = tamper.DEVICE_KINDS.get(e.kind, "warning")
        if tamper.record(db, device, e.kind[:40], e.detail or e.kind, severity, "device"):
            recorded += 1
    return {"ok": True, "recorded": recorded}


@router.post("/impressions")
def impressions(body: ImpressionsIn, db: Session = Depends(get_db), device: Device = Depends(current_device)):
    for i in body.items:
        try:
            started = datetime.fromisoformat(i.started_at) if i.started_at else utcnow()
        except ValueError:
            started = utcnow()
        db.add(Impression(device_id=device.device_id, content_id=i.content_id, zone_id=i.zone_id,
                          started_at=started, duration=i.duration))
    db.commit()
    return {"ok": True, "accepted": len(body.items)}
