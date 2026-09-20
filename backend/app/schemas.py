import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class LoginIn(BaseModel):
    username: str
    password: str


class UserIn(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=8, max_length=128)
    role: Literal["admin", "viewer"] = "admin"


class PasswordChangeIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


class DeviceIn(BaseModel):
    device_id: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    name: str = Field(min_length=1, max_length=100)
    group_id: int | None = None
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
    config: DeviceConfig | None = None


class RegisterIn(BaseModel):
    device_id: str
    registration_token: str
    software_version: str | None = None


class LocationIn(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    device_id: str | None = None


class HeartbeatIn(BaseModel):
    cpu: float | None = Field(None, ge=0, le=100)
    memory: float | None = Field(None, ge=0, le=100)
    network: str | None = None
    gps: bool | None = None
    content_version: str | None = None
    content_names: str | None = None
    software_version: str | None = None
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
