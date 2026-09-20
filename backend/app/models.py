from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))  # "!firebase" for accounts that only sign in via Firebase
    role: Mapped[str] = mapped_column(String(16), default="admin")  # admin | viewer | pending (awaiting approval)
    email: Mapped[str | None] = mapped_column(String(255), unique=True, index=True, nullable=True)
    firebase_uid: Mapped[str | None] = mapped_column(String(128), unique=True, index=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DeviceGroup(Base):
    __tablename__ = "device_groups"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)


class Content(Base):
    __tablename__ = "content"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    type: Mapped[str] = mapped_column(String(16))  # image | video
    storage_key: Mapped[str] = mapped_column(String(255))
    mime: Mapped[str] = mapped_column(String(64))
    size: Mapped[int] = mapped_column(Integer, default=0)
    duration: Mapped[int] = mapped_column(Integer, default=10)  # seconds on screen (images)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Zone(Base):
    __tablename__ = "zones"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    polygon: Mapped[list] = mapped_column(JSON)  # [[lat, lng], ...]
    priority: Mapped[int] = mapped_column(Integer, default=0)
    color: Mapped[str] = mapped_column(String(16), default="#3b82f6")


class Assignment(Base):
    """Content -> (zone | group | everywhere), optionally time-windowed.

    zone_id NULL and group_id NULL means a global default.
    is_emergency assignments outrank everything else while active.
    """

    __tablename__ = "assignments"
    id: Mapped[int] = mapped_column(primary_key=True)
    content_id: Mapped[int] = mapped_column(ForeignKey("content.id", ondelete="CASCADE"))
    zone_id: Mapped[int | None] = mapped_column(ForeignKey("zones.id", ondelete="CASCADE"), nullable=True)
    group_id: Mapped[int | None] = mapped_column(ForeignKey("device_groups.id", ondelete="CASCADE"), nullable=True)
    start_time: Mapped[str | None] = mapped_column(String(5), nullable=True)  # "HH:MM"
    end_time: Mapped[str | None] = mapped_column(String(5), nullable=True)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    is_emergency: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    content: Mapped[Content] = relationship(lazy="joined")
    zone: Mapped[Zone | None] = relationship(lazy="joined")
    group: Mapped[DeviceGroup | None] = relationship(lazy="joined")


class Device(Base):
    __tablename__ = "devices"
    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    group_id: Mapped[int | None] = mapped_column(ForeignKey("device_groups.id", ondelete="SET NULL"), nullable=True)
    registration_token_hash: Mapped[str] = mapped_column(String(255))
    token_version: Mapped[int] = mapped_column(Integer, default=0)  # bump to revoke issued JWTs
    registered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    connection_type: Mapped[str | None] = mapped_column(String(16), nullable=True)  # wifi|ethernet|cellular_4g|cellular_5g|other

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

    group: Mapped[DeviceGroup | None] = relationship(lazy="joined")
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


class Alert(Base):
    """Raised when a device's health drops below the configured threshold; resolved when it recovers."""

    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[str] = mapped_column(String(64), index=True)
    kind: Mapped[str] = mapped_column(String(16))  # offline | health_low
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
