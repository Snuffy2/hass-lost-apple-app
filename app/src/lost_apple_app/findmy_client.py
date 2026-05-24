"""Boundary around FindMy.py so the App can run without live Apple access."""

# mypy: disable_error_code=import-untyped

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from findmy import AsyncAppleAccount, FindMyAccessory
from findmy.reports import LoginState

if TYPE_CHECKING:
    from collections.abc import Awaitable
    from datetime import datetime
    from pathlib import Path


class _HashedPublicKey(Protocol):
    """Protocol matching the FindMy.py public-key shape."""

    @property
    def hashed_adv_key_bytes(self) -> bytes: ...


class _RollingKeySource(Protocol):
    """Protocol matching the FindMy.py key-source shape used by fetch_location."""

    def get_min_index(self, dt: datetime) -> int: ...

    def get_max_index(self, dt: datetime) -> int: ...

    def update_alignment(self, dt: datetime, index: int) -> None: ...

    def keys_at(self, ind: int) -> set[object]: ...


type _FindMySourceKey = _HashedPublicKey | _RollingKeySource


class _FindMyAccount(Protocol):
    """FindMy account protocol used by this adapter."""

    def fetch_location(
        self,
        key: _FindMySourceKey,
    ) -> Awaitable[_FindMyLocationReport | None]: ...


class _AppleAccountStateSource(Protocol):
    """Protocol for serializing FindMy account session state."""

    def to_json(self) -> dict[str, object]: ...


class _FindMyLocationReport(Protocol):
    """Protocol for a FindMy.py location report."""

    @property
    def latitude(self) -> float: ...

    @property
    def longitude(self) -> float: ...

    @property
    def horizontal_accuracy(self) -> float | None: ...

    @property
    def timestamp(self) -> datetime: ...


class _FindMyRawDevice(Protocol):
    """Protocol for a raw FindMy.py device object."""

    @property
    def identifier(self) -> object: ...

    @property
    def name(self) -> object: ...

    @property
    def battery_status(self) -> str | None: ...

    @property
    def location(self) -> _FindMyLocationReport: ...


@dataclass(frozen=True, slots=True)
class FindMyDevice:
    """Normalized device shape for adapter consumers."""

    id: str
    name: str
    latitude: float
    longitude: float
    accuracy_m: float | None
    battery_status: str | None
    last_reported_at: datetime


@dataclass(frozen=True, slots=True)
class FindMySource:
    """Project-owned configured source for FindMy lookups."""

    id: str
    name: str
    findmy_key_or_accessory: _FindMySourceKey
    battery_status: str | None = None


def normalize_findmy_device(raw_device: _FindMyRawDevice) -> FindMyDevice:
    """Normalize a raw FindMy.py device into app shape."""
    location = raw_device.location
    raw_accuracy = getattr(location, "horizontal_accuracy", None)
    raw_battery_status = getattr(raw_device, "battery_status", None)

    return FindMyDevice(
        id=str(raw_device.identifier),
        name=str(raw_device.name),
        latitude=float(location.latitude),
        longitude=float(location.longitude),
        accuracy_m=None if raw_accuracy is None else float(raw_accuracy),
        battery_status=None if raw_battery_status is None else str(raw_battery_status),
        last_reported_at=location.timestamp,
    )


def normalize_findmy_report(
    source: FindMySource,
    report: _FindMyLocationReport,
) -> FindMyDevice:
    """Normalize a FindMy.py location report using a configured source."""
    raw_accuracy = getattr(report, "horizontal_accuracy", None)
    return FindMyDevice(
        id=source.id,
        name=source.name,
        latitude=float(report.latitude),
        longitude=float(report.longitude),
        accuracy_m=None if raw_accuracy is None else float(raw_accuracy),
        battery_status=source.battery_status,
        last_reported_at=report.timestamp,
    )


class FindMyService:
    """Boundary to Fetch My Apple devices."""

    def __init__(
        self,
        account: _FindMyAccount | None = None,
        sources: list[FindMySource] | None = None,
    ) -> None:
        """Initialize with optional authenticated account and configured sources."""
        self._account = account
        self._sources = tuple(sources or ())

    async def fetch_devices(self) -> list[FindMyDevice]:
        """Fetch official Apple account-discovered Find My devices."""
        if self._account is None or not self._sources:
            return []

        fetcher = getattr(self._account, "fetch_location", None)
        if not callable(fetcher):
            message = (
                "Authenticated FindMy account must implement fetch_location(); "
                "installed FindMy.py exposes: fetch_location, "
                "fetch_location_history, fetch_raw_reports."
            )
            raise TypeError(message)

        devices: list[FindMyDevice] = []
        for source in self._sources:
            location = await fetcher(source.findmy_key_or_accessory)
            if location is None:
                # Explicitly skip missing reports for a configured source.
                continue
            devices.append(normalize_findmy_report(source, location))

        return devices

    @property
    def account(self) -> _FindMyAccount | None:
        """Return the configured account implementation for tests and setup checks."""
        return self._account

    async def close(self) -> None:
        """Close the underlying account when the adapter owns a closable account."""
        close = getattr(self._account, "close", None)
        if callable(close):
            await close()


def serialize_apple_account_state(
    account: _AppleAccountStateSource,
) -> dict[str, object]:
    """Serialize account session state without persisting the Apple password."""
    state = account.to_json()
    account_state = state.get("account")
    if isinstance(account_state, dict):
        account_state["password"] = None
    return state


def load_apple_account(
    state: Mapping[str, object],
    anisette_libs_path: str | Path | None = None,
) -> AsyncAppleAccount:
    """Restore an ``AsyncAppleAccount`` from persisted session JSON."""
    if state == {}:
        missing_state_message = "Missing Apple account state"
        raise ValueError(missing_state_message)
    return AsyncAppleAccount.from_json(state, anisette_libs_path=anisette_libs_path)


def build_sources_from_payloads(sources: Sequence[object]) -> list[FindMySource]:
    """Build polling sources from official FindMy accessory payload objects."""
    findmy_sources: list[FindMySource] = []
    for index, payload in enumerate(sources):
        accessory = _load_accessory(payload)
        source_identifier = accessory.identifier
        if source_identifier is None:
            source_identifier = accessory.serial_number
        if source_identifier is None:
            source_identifier = accessory.model
        if source_identifier is None:
            source_identifier = f"source-{index}"

        source_name = accessory.name
        if source_name is None:
            source_name = str(source_identifier)

        findmy_sources.append(
            FindMySource(
                id=str(source_identifier),
                name=source_name,
                findmy_key_or_accessory=accessory,
                battery_status=None,
            )
        )

    return findmy_sources


def serialize_accessory_payloads(sources: Sequence[object]) -> list[dict[str, object]]:
    """Serialize configured accessory payload objects for storage."""
    serialized_sources: list[dict[str, object]] = []
    for source in sources:
        accessory = _load_accessory(source)
        serialized = accessory.to_json()
        if not isinstance(serialized, dict):
            serialization_error = "Accessory payload must serialize to a mapping"
            raise TypeError(serialization_error)
        serialized_sources.append(serialized)
    return serialized_sources


def map_login_state(state: LoginState) -> str:
    """Map FindMy login state to a lightweight status string for logs/UI."""
    if state in (LoginState.AUTHENTICATED, LoginState.LOGGED_IN):
        return "authenticated"
    if state == LoginState.REQUIRE_2FA:
        return "requires_2fa"
    return "not_ready"


def _load_accessory(payload: object) -> FindMyAccessory:
    """Load a FindMyAccessory from a payload accepted by ``from_json``."""
    if isinstance(payload, FindMyAccessory):
        return payload
    if isinstance(payload, Mapping):
        return FindMyAccessory.from_json(payload)
    if isinstance(payload, (str, bytes, bytearray)):
        source_payload = payload.decode() if isinstance(payload, (bytes, bytearray)) else payload
        return FindMyAccessory.from_json(source_payload)

    error = "Invalid accessory payload type"
    raise TypeError(error)
