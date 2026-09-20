"""Clients (customers): creation helpers and the one-time backfill for databases from before multi-client support."""
import logging
import re
import secrets

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..models import Client

log = logging.getLogger("clients")

# tables whose rows belong to a client
CLIENT_OWNED = ("devices", "content", "zones", "device_groups", "assignments", "broadcasts", "alerts")


def new_enrollment_key() -> str:
    return "enr_" + secrets.token_urlsafe(18)


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "client"


def unique_slug(db: Session, name: str) -> str:
    base, slug, n = slugify(name), slugify(name), 1
    while db.query(Client).filter(Client.slug == slug).first():
        n += 1
        slug = f"{base}-{n}"
    return slug


def create_client(db: Session, name: str, device_limit: int | None = None) -> Client:
    client = Client(name=name.strip(), slug=unique_slug(db, name), enrollment_key=new_enrollment_key(), device_limit=device_limit)
    db.add(client)
    db.flush()
    return client


def ensure_default_client(db: Session) -> Client:
    """Every deployment has at least one client. Data created before multi-client support (client_id IS NULL) is moved into
    the first client, so an upgraded single-customer installation behaves exactly as before."""
    client = db.query(Client).order_by(Client.id).first()
    if client is None:
        client = create_client(db, "Default")
        log.info("Created the Default client")
    for table in CLIENT_OWNED:
        moved = db.execute(text(f"UPDATE {table} SET client_id = :cid WHERE client_id IS NULL"), {"cid": client.id}).rowcount
        if moved:
            log.info("Moved %s existing %s row(s) into client '%s'", moved, table, client.name)
    db.commit()
    return client
