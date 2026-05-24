"""API and persistence models for the Lost Apple App."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

DeviceStatus = Literal["ok", "stale", "auth_error", "rate_limited", "error"]


class DeviceSnapshot(BaseModel):
    """Normalized Find My device state stored by the App."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    latitude: float
    longitude: float
    accuracy_m: float | None
    battery_status: str | None
    status: DeviceStatus
    last_reported_at: datetime
    last_polled_at: datetime
    error: str | None


class AppHealth(BaseModel):
    """Current App health returned to the integration."""

    api_version: int
    app_version: str
    account_state: Literal["not_configured", "authenticated", "reauth_required"]
    polling_interval_minutes: int
    device_count: int
