from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Client(Base):
    """A customer of the platform. Everything below (devices, content, zones, ...) belongs to exactly one client."""

    __tablename__ = "clients"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    slug: Mapped[str] = mapped_column(String(100), unique=True)
    enrollment_key: Mapped[str] = mapped_column(String(64), unique=True)  # lets a display announce itself to this client only
    active: Mapped[bool] = mapped_column(Boolean, default=True)  # a suspended client's users and devices are locked out
    device_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)  # None = unlimited
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))  # "!firebase" for accounts that only sign in via Firebase
    role: Mapped[str] = mapped_column(String(16), default="admin")  # admin | viewer | pending (awaiting approval)
    email: Mapped[str | None] = mapped_column(String(255), unique=True, index=True, nullable=True)
    firebase_uid: Mapped[str | None] = mapped_column(String(128), unique=True, index=True, nullable=True)
    # NULL = platform user (sees and manages every client); set = belongs to that client only
    client_id: Mapped[int | None] = mapped_column(ForeignKey("clients.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DeviceGroup(Base):
    __tablename__ = "device_groups"
    __table_args__ = (Index("uq_groups_client_name", "client_id", "name", unique=True),)
    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int | None] = mapped_column(ForeignKey("clients.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(100))


class Content(Base):
    __tablename__ = "content"
    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int | None] = mapped_column(ForeignKey("clients.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    type: Mapped[str] = mapped_column(String(16))  # image | video
    storage_key: Mapped[str] = mapped_column(String(255))
    mime: Mapped[str] = mapped_column(String(64))
    size: Mapped[int] = mapped_column(Integer, default=0)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)  # lets displays verify what they download and cache
    duration: Mapped[int] = mapped_column(Integer, default=10)  # seconds on screen (images)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Zone(Base):
    __tablename__ = "zones"
    __table_args__ = (Index("uq_zones_client_name", "client_id", "name", unique=True),)
    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int | None] = mapped_column(ForeignKey("clients.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    polygon: Mapped[list] = mapped_column(JSON)  # [[lat, lng], ...]
    priority: Mapped[int] = mapped_column(Integer, default=0)
    color: Mapped[str] = mapped_column(String(16), default="#3b82f6")


class Route(Base):
    """An ordered path a vehicle-mounted display follows. Leg i is the stretch from waypoint i to waypoint i+1."""

    __tablename__ = "routes"
    __table_args__ = (Index("uq_routes_client_name", "client_id", "name", unique=True),)
    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int | None] = mapped_column(ForeignKey("clients.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    waypoints: Mapped[list] = mapped_column(JSON)          # [{"name": str, "lat": float, "lng": float}, ...]
    corridor_km: Mapped[float] = mapped_column(Float, default=25.0)   # farther than this from the path = off route
    color: Mapped[str] = mapped_column(String(16), default="#e0662b")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Assignment(Base):
    """Content -> (zone | group | route [leg] | everywhere), optionally time-windowed.

    zone_id NULL and group_id NULL means a global default.
    is_emergency assignments outrank everything else while active.
    """

    __tablename__ = "assignments"
    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int | None] = mapped_column(ForeignKey("clients.id"), nullable=True, index=True)
    content_id: Mapped[int] = mapped_column(ForeignKey("content.id", ondelete="CASCADE"))
    zone_id: Mapped[int | None] = mapped_column(ForeignKey("zones.id", ondelete="CASCADE"), nullable=True)
    group_id: Mapped[int | None] = mapped_column(ForeignKey("device_groups.id", ondelete="CASCADE"), nullable=True)
    route_id: Mapped[int | None] = mapped_column(ForeignKey("routes.id", ondelete="CASCADE"), nullable=True)
    route_leg: Mapped[int | None] = mapped_column(Integer, nullable=True)      # NULL = the whole route
    start_time: Mapped[str | None] = mapped_column(String(5), nullable=True)  # "HH:MM"
    end_time: Mapped[str | None] = mapped_column(String(5), nullable=True)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    is_emergency: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    content: Mapped[Content] = relationship(lazy="joined")
    zone: Mapped[Zone | None] = relationship(lazy="joined")
    group: Mapped[DeviceGroup | None] = relationship(lazy="joined")
    route: Mapped[Route | None] = relationship(lazy="joined")


class Device(Base):
    __tablename__ = "devices"
    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    client_id: Mapped[int | None] = mapped_column(ForeignKey("clients.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    group_id: Mapped[int | None] = mapped_column(ForeignKey("device_groups.id", ondelete="SET NULL"), nullable=True)
    registration_token_hash: Mapped[str] = mapped_column(String(255))
    token_version: Mapped[int] = mapped_column(Integer, default=0)  # bump to revoke issued JWTs
    registered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    connection_type: Mapped[str | None] = mapped_column(String(16), nullable=True)  # wifi|ethernet|cellular_4g|cellular_5g|other

    # route following (route_leg / progress / off-route are recomputed on every position update)
    route_id: Mapped[int | None] = mapped_column(ForeignKey("routes.id", ondelete="SET NULL"), nullable=True)
    route_leg: Mapped[int | None] = mapped_column(Integer, nullable=True)
    route_progress: Mapped[float | None] = mapped_column(Float, nullable=True)      # percent of the route covered
    route_offset_km: Mapped[float | None] = mapped_column(Float, nullable=True)     # distance from the path
    route_off: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    # location history bookkeeping and the latest screenshot
    track_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    track_lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    track_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    screenshot_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    screenshot_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    status: Mapped[str] = mapped_column(String(16), default="offline")  # online | offline
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    current_zone_id: Mapped[int | None] = mapped_column(ForeignKey("zones.id", ondelete="SET NULL"), nullable=True)
    current_content_version: Mapped[str | None] = mapped_column(String(64), nullable=True)  # what the device reports
    current_content_names: Mapped[str | None] = mapped_column(String(500), nullable=True)
    software_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    cpu: Mapped[float | None] = mapped_column(Float, nullable=True)
    memory: Mapped[float | None] = mapped_column(Float, nullable=True)
    network: Mapped[str | None] = mapped_column(String(32), nullable=True)
    gps_ok: Mapped[bool] = mapped_column(Boolean, default=False)
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    # fleet inventory, reported by the agent (software_version above is the agent version)
    os_name: Mapped[str | None] = mapped_column(String(32), nullable=True)
    os_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    os_arch: Mapped[str | None] = mapped_column(String(24), nullable=True)
    runtime_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    capabilities: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # tamper-proofing
    public_key: Mapped[str | None] = mapped_column(String(64), nullable=True)      # base64 Ed25519 key bound at registration
    key_bound_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    hw_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)  # hash of the machine's identity, bound at registration
    code_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)       # latest hash of the agent's own code
    code_baseline: Mapped[str | None] = mapped_column(String(64), nullable=True)   # first hash seen for this device
    tamper_state: Mapped[str | None] = mapped_column(String(12), nullable=True)    # None/"ok" | "flagged"
    tamper_flagged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    boot_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    restarts: Mapped[list | None] = mapped_column(JSON, nullable=True)            # recent agent start times (epoch seconds)

    group: Mapped[DeviceGroup | None] = relationship(lazy="joined")
    route: Mapped[Route | None] = relationship(lazy="joined")
    current_zone: Mapped[Zone | None] = relationship(lazy="joined")


class DeviceLog(Base):
    __tablename__ = "device_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[str] = mapped_column(String(64), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)  # online|offline|zone|content|register|config|alert
    message: Mapped[str] = mapped_column(Text, default="")


class Impression(Base):
    __tablename__ = "impressions"
    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[str] = mapped_column(String(64), index=True)
    content_id: Mapped[int] = mapped_column(Integer, index=True)
    zone_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    duration: Mapped[float] = mapped_column(Float, default=0)


class Broadcast(Base):
    """A live announcement shown as an overlay on the displays it targets (all when no target is set)."""

    __tablename__ = "broadcasts"
    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int | None] = mapped_column(ForeignKey("clients.id"), nullable=True, index=True)
    message: Mapped[str] = mapped_column(Text)
    style: Mapped[str] = mapped_column(String(12), default="ticker")  # ticker | banner | fullscreen
    severity: Mapped[str] = mapped_column(String(12), default="info")  # info | warning | critical
    zone_id: Mapped[int | None] = mapped_column(ForeignKey("zones.id", ondelete="CASCADE"), nullable=True)
    group_id: Mapped[int | None] = mapped_column(ForeignKey("device_groups.id", ondelete="CASCADE"), nullable=True)
    device_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_by: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)  # None = until ended
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    zone: Mapped[Zone | None] = relationship(lazy="joined")
    group: Mapped[DeviceGroup | None] = relationship(lazy="joined")


class LocationPoint(Base):
    """One remembered position of a display (kept only when it moved or changed zone, and pruned after TRACK_RETENTION_DAYS)."""

    __tablename__ = "location_points"
    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int | None] = mapped_column(ForeignKey("clients.id"), nullable=True, index=True)
    device_id: Mapped[str] = mapped_column(String(64), index=True)
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    zone_id: Mapped[int | None] = mapped_column(Integer, nullable=True)          # zone at that moment (no FK: history outlives zones)
    entered: Mapped[bool] = mapped_column(Boolean, default=False)                # this point is the moment the display entered zone_id
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class Alert(Base):
    """Raised when a device's health drops below the configured threshold; resolved when it recovers."""

    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int | None] = mapped_column(ForeignKey("clients.id"), nullable=True, index=True)
    device_id: Mapped[str] = mapped_column(String(64), index=True)
    kind: Mapped[str] = mapped_column(String(16))  # offline | health_low | tamper | off_route
    message: Mapped[str] = mapped_column(Text)
    health: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledged_by: Mapped[str | None] = mapped_column(String(64), nullable=True)


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")


class AgentRelease(Base):
    """A trusted build of the display agent: version + the hash of its code. Platform-managed."""

    __tablename__ = "agent_releases"
    id: Mapped[int] = mapped_column(primary_key=True)
    version: Mapped[str] = mapped_column(String(32), index=True)
    code_hash: Mapped[str] = mapped_column(String(64), unique=True)
    note: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TamperEvent(Base):
    """Append-only, hash-chained record of tampering signals. Each row's hash covers the previous row of the same client,
    so deleting or editing history is detectable (see services/tamper.verify_chain)."""

    __tablename__ = "tamper_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    device_id: Mapped[str] = mapped_column(String(64), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    severity: Mapped[str] = mapped_column(String(12), default="critical")  # warning | critical
    source: Mapped[str] = mapped_column(String(10), default="server")      # device | server | admin
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    prev_hash: Mapped[str] = mapped_column(String(64), default="")
    hash: Mapped[str] = mapped_column(String(64), default="")
