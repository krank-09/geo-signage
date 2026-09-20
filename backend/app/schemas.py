import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


ConnectionType = Literal["wifi", "ethernet", "cellular_4g", "cellular_5g", "other"]


class LoginIn(BaseModel):
    username: str
    password: str


class FirebaseLoginIn(BaseModel):
    id_token: str = Field(min_length=20, max_length=4096)


class RoleIn(BaseModel):
    role: Literal["admin", "viewer", "pending"]
    client_id: int | None = None      # platform admins only: move the person into a client (omit to leave it unchanged)


class ClientIn(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    device_limit: int | None = Field(None, ge=1, le=100000)


class ClientUpdate(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=100)
    active: bool | None = None
    device_limit: int | None = Field(None, ge=1, le=100000)
    clear_device_limit: bool = False


class UserIn(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=8, max_length=128)
    role: Literal["admin", "viewer"] = "admin"
    client_id: int | None = None      # platform admins only; a client admin's new users always join their own client


class PasswordChangeIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


class AnnounceIn(BaseModel):
    secret: str = Field(min_length=16, max_length=64)   # random, generated and kept by the agent; only its hash is ever shown
    name: str = Field(min_length=1, max_length=80)
    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)
    connection_type: ConnectionType | None = None
    software_version: str | None = Field(None, max_length=32)
    enrollment_key: str | None = Field(None, max_length=64)   # ties the display to one client; without it it is unassigned


class HealthSettingIn(BaseModel):
    threshold: int = Field(ge=0, le=100)


class BroadcastIn(BaseModel):
    message: str = Field(min_length=1, max_length=280)
    style: Literal["ticker", "banner", "fullscreen"] = "ticker"
    severity: Literal["info", "warning", "critical"] = "info"
    zone_id: int | None = None
    group_id: int | None = None
    device_id: str | None = Field(None, max_length=64)
    duration_seconds: int | None = Field(None, ge=5, le=86400)  # None = until an admin ends it


class DeviceIn(BaseModel):
    device_id: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    name: str = Field(min_length=1, max_length=100)
    group_id: int | None = None
    connection_type: ConnectionType | None = None
    discovery_id: str | None = Field(None, max_length=32)  # claim an unclaimed agent found on the network (see discovery)
    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)


class DeviceConfig(BaseModel):
    heartbeat_interval: int = Field(10, ge=2, le=300)
    location_interval: int = Field(3, ge=1, le=300)
    mute: bool = True
    fit: Literal["contain", "cover"] = "contain"


class DeviceUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    group_id: int | None = None
    clear_group: bool = False
    connection_type: ConnectionType | None = None
    config: DeviceConfig | None = None


class Inventory(BaseModel):
    """What a display tells us about itself. All optional: displays running an older agent send none of it."""
    software_version: str | None = Field(None, max_length=32)
    os_name: str | None = Field(None, max_length=32)
    os_version: str | None = Field(None, max_length=64)
    os_arch: str | None = Field(None, max_length=24)
    runtime_version: str | None = Field(None, max_length=32)
    capabilities: list[str] | None = Field(None, max_length=32)
    code_hash: str | None = Field(None, max_length=64)
    boot_id: str | None = Field(None, max_length=64)


class RegisterIn(Inventory):
    device_id: str
    registration_token: str
    public_key: str | None = Field(None, max_length=64)      # base64 Ed25519, bound to this device on first registration
    hw_fingerprint: str | None = Field(None, max_length=64)


class TamperIn(BaseModel):
    kind: str = Field(max_length=40)
    detail: str = Field("", max_length=500)
    at: str | None = None


class TamperBatchIn(BaseModel):
    events: list[TamperIn] = Field(max_length=50)


class LocationIn(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    device_id: str | None = None


class HeartbeatIn(Inventory):
    cpu: float | None = Field(None, ge=0, le=100)
    memory: float | None = Field(None, ge=0, le=100)
    network: str | None = None
    gps: bool | None = None
    content_version: str | None = None
    content_names: str | None = None
    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)


class ImpressionIn(BaseModel):
    content_id: int
    zone_id: int | None = None
    started_at: str | None = None
    duration: float = Field(ge=0, le=86400)


class ImpressionsIn(BaseModel):
    items: list[ImpressionIn] = Field(max_length=500)


class GroupIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class ZoneIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    polygon: list[list[float]] = Field(min_length=3, max_length=500)
    priority: int = 0
    color: str = Field("#3b82f6", pattern=r"^#[0-9a-fA-F]{6}$")

    @field_validator("polygon")
    @classmethod
    def _check(cls, v):
        for p in v:
            if len(p) != 2 or not (-90 <= p[0] <= 90) or not (-180 <= p[1] <= 180):
                raise ValueError("polygon points must be [lat, lng]")
        return v


class CityZoneIn(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)   # default: "<City> Zone"
    priority: int = 10
    color: str = Field("#3b82f6", pattern=r"^#[0-9a-fA-F]{6}$")


class AssignmentIn(BaseModel):
    content_id: int
    zone_id: int | None = None
    group_id: int | None = None
    start_time: str | None = None
    end_time: str | None = None
    priority: int = Field(0, ge=0, le=1000)
    is_emergency: bool = False
    active: bool = True

    @field_validator("start_time", "end_time")
    @classmethod
    def _hhmm(cls, v):
        if v in (None, ""):
            return None
        if not HHMM.match(v):
            raise ValueError("time must be HH:MM (24h)")
        return v


class ContentUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    duration: int | None = Field(None, ge=1, le=3600)


class PolicyIn(BaseModel):
    recommended_version: str | None = Field(None, max_length=32)
    supported_version: str | None = Field(None, max_length=32)


class ReleaseIn(BaseModel):
    version: str = Field(max_length=32)
    code_hash: str = Field(min_length=16, max_length=64)
    note: str = Field("", max_length=200)
