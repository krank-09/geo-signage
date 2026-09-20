"""First-run seed: admin user + demo devices, city zones and generated media."""
import hashlib
import logging
import os
import secrets
import tempfile
import uuid

from PIL import Image, ImageDraw, ImageFont
from sqlalchemy.orm import Session

from . import config
from .models import Assignment, Client, Content, Device, DeviceGroup, User, Zone
from .security import hash_secret
from .services.device_service import DEFAULT_CONFIG
from .storage import get_storage

log = logging.getLogger("seed")

# name, centre (lat, lng), radius km, colour
CITIES = [
    ("Chandigarh", (30.7333, 76.7794), 30, "#2563eb", ((37, 99, 235), (14, 165, 233))),
    ("Delhi", (28.6139, 77.2090), 40, "#16a34a", ((22, 163, 74), (132, 204, 22))),
    ("Mumbai", (19.0760, 72.8777), 40, "#dc2626", ((220, 38, 38), (249, 115, 22))),
]


def circle(center, radius_km, n=32):
    import math

    lat0, lng0 = center
    pts = []
    for i in range(n):
        a = 2 * math.pi * i / n
        pts.append([round(lat0 + (radius_km / 111.0) * math.sin(a), 5),
                    round(lng0 + (radius_km / (111.0 * math.cos(math.radians(lat0)))) * math.cos(a), 5)])
    return pts


def _font(size: int):
    for path in ("/System/Library/Fonts/Helvetica.ttc", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                 "/Library/Fonts/Arial Bold.ttf"):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def make_slide(title: str, subtitle: str, c1, c2) -> str:
    w, h = 1280, 720
    # Diagonal gradient: a 2x2 image of the corner colours, bilinearly upscaled (instant, unlike a per-pixel loop).
    mix = lambda t: tuple(round(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))  # noqa: E731
    corners = Image.new("RGB", (2, 2))
    corners.putdata([c1, mix(0.6), mix(0.4), c2])
    img = corners.resize((w, h), Image.Resampling.BILINEAR)
    d = ImageDraw.Draw(img)
    d.text((w // 2, h // 2 - 30), title, font=_font(150), fill="white", anchor="mm")
    d.text((w // 2, h // 2 + 110), subtitle, font=_font(48), fill=(255, 255, 255), anchor="mm")
    path = os.path.join(tempfile.gettempdir(), f"{uuid.uuid4().hex}.png")
    img.save(path, "PNG")
    return path


def _add_content(db: Session, cid: int, name: str, title: str, sub: str, c1, c2, duration=8) -> Content:
    path = make_slide(title, sub, c1, c2)
    key = f"{uuid.uuid4().hex}.png"
    try:
        with open(path, "rb") as f:
            digest = hashlib.sha256(f.read()).hexdigest()   # hashed before the temp file goes away
        get_storage().put(key, path, "image/png")
        size = os.path.getsize(path)
    finally:
        os.remove(path)
    c = Content(client_id=cid, name=name, type="image", storage_key=key, mime="image/png", size=size, sha256=digest, duration=duration)
    db.add(c)
    db.flush()
    return c


def seed(db: Session) -> None:
    if not db.query(User).first():
        db.add(User(username=config.DEFAULT_ADMIN_USER, password_hash=hash_secret(config.DEFAULT_ADMIN_PASSWORD), role="admin"))
        db.commit()
        log.info("Created default admin user '%s'", config.DEFAULT_ADMIN_USER)

    if not config.SEED_DEMO_DATA or db.query(Device).first() or db.query(Zone).first():
        return

    cid = db.query(Client).order_by(Client.id).first().id   # ensure_default_client() has run
    north = DeviceGroup(name="North India", client_id=cid)
    west = DeviceGroup(name="West India", client_id=cid)
    db.add_all([north, west])
    db.flush()

    zones = {}
    for name, center, radius, color, _ in CITIES:
        z = Zone(client_id=cid, name=f"{name} Zone", polygon=circle(center, radius), priority=10, color=color)
        db.add(z)
        zones[name] = z
    db.flush()

    welcome = _add_content(db, cid, "Welcome (default)", "Welcome", "Geo Signage - default content", (30, 41, 59), (100, 116, 139), 8)
    db.add(Assignment(client_id=cid, content_id=welcome.id, priority=0))
    for name, _, _, _, (c1, c2) in CITIES:
        c = _add_content(db, cid, f"{name} Advertisement", name, f"Advertisement for {name}", c1, c2)
        db.add(Assignment(client_id=cid, content_id=c.id, zone_id=zones[name].id, priority=10))
    _add_content(db, cid, "EMERGENCY ALERT", "ALERT", "Please follow official instructions", (127, 29, 29), (239, 68, 68), 6)

    devices = [  # id, name, group, registration token, connection type
        ("DEV-001", "Roadshow Van", north, "DEMO-REG-001", "cellular_4g"),
        ("DEV-002", "Connaught Place Kiosk", north, "DEMO-REG-002", "ethernet"),
        ("DEV-003", "Bandra Billboard", west, "DEMO-REG-003", "wifi"),
    ]
    for did, name, group, token, connection in devices:
        if not config.FIXED_DEMO_TOKENS:
            token = "-".join(secrets.token_hex(2).upper() for _ in range(3))
            log.warning("Registration token for %s: %s", did, token)  # shown once; rotate in the dashboard if lost
        db.add(Device(device_id=did, client_id=cid, name=name, group_id=group.id, registration_token_hash=hash_secret(token),
                      connection_type=connection, config=dict(DEFAULT_CONFIG)))
    db.commit()
    log.info("Seeded demo data (3 devices, 3 zones, 5 content items)")
