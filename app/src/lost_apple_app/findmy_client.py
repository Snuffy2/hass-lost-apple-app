"""Boundary around FindMy.py so the App can run without live Apple access."""

# mypy: disable_error_code=import-untyped

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
import plistlib
import re
from typing import TYPE_CHECKING, Protocol

from findmy import AsyncAppleAccount, FindMyAccessory
from findmy.reports import LoginState

if TYPE_CHECKING:
    from collections.abc import Awaitable
    from datetime import datetime


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
type _NamedBytesPayload = tuple[str, bytes]

_ALIGNMENT_FILENAME_SUFFIXES = (
    ".key-alignment",
    "_key_alignment",
    "-key-alignment",
    " key alignment",
    ".alignment",
    "_alignment",
    "-alignment",
    " alignment",
)
_ACCESSORY_MATCH_KEYS = (
    "identifier",
    "beaconIdentifier",
    "beacon_identifier",
    "stableIdentifier",
    "serialNumber",
    "name",
)


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


@dataclass(frozen=True, slots=True)
class _AccessoryPlistUpload:
    """Parsed accessory plist upload with keys used for alignment matching."""

    filename: str
    payload: bytes
    parsed: Mapping[str, object]
    match_keys: frozenset[str]


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
        findmy_sources.append(_source_from_accessory(accessory, index))

    return findmy_sources


def build_sources_from_plist_payloads(
    accessory_payloads: Sequence[_NamedBytesPayload],
    alignment_payloads: Sequence[_NamedBytesPayload] | None = None,
) -> list[FindMySource]:
    """Build polling sources from accessory plist uploads and optional alignments."""
    if not accessory_payloads:
        missing_payloads_error = "accessory_payloads must be non-empty"
        raise ValueError(missing_payloads_error)

    accessories = [
        _parse_accessory_plist(filename, payload) for filename, payload in accessory_payloads
    ]
    alignment_by_filename = _match_alignment_payloads(
        accessories=accessories,
        alignment_payloads=alignment_payloads or (),
    )

    findmy_sources: list[FindMySource] = []
    for index, accessory_upload in enumerate(accessories):
        alignment_payload = alignment_by_filename.get(accessory_upload.filename)
        accessory = FindMyAccessory.from_plist(
            accessory_upload.payload,
            alignment_payload,
            name=_accessory_display_name(accessory_upload),
        )
        findmy_sources.append(_source_from_accessory(accessory, index))

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


def _source_from_accessory(accessory: FindMyAccessory, index: int) -> FindMySource:
    """Create a project source from a loaded FindMy.py accessory."""
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

    return FindMySource(
        id=str(source_identifier),
        name=source_name,
        findmy_key_or_accessory=accessory,
        battery_status=None,
    )


def _parse_accessory_plist(filename: str, payload: bytes) -> _AccessoryPlistUpload:
    """Parse an accessory plist and collect stable matching keys."""
    parsed = _load_plist_mapping(payload)
    match_keys = set(_matching_keys_from_mapping(parsed))
    stem_key = _normalize_match_key(_strip_plist_suffix(filename))
    if stem_key:
        match_keys.add(stem_key)

    return _AccessoryPlistUpload(
        filename=filename,
        payload=payload,
        parsed=parsed,
        match_keys=frozenset(match_keys),
    )


def _load_plist_mapping(payload: bytes) -> Mapping[str, object]:
    """Load a plist payload and ensure the top-level value is a mapping."""
    try:
        parsed = plistlib.loads(payload)
    except plistlib.InvalidFileException as error:
        raise ValueError("Invalid plist payload") from error
    if not isinstance(parsed, Mapping):
        invalid_payload_error = "Plist payload must contain a mapping"
        raise TypeError(invalid_payload_error)
    return parsed


def _matching_keys_from_mapping(payload: Mapping[str, object]) -> set[str]:
    """Extract normalized identifiers that may connect accessory and alignment files."""
    keys: set[str] = set()
    for field in _ACCESSORY_MATCH_KEYS:
        raw_value = payload.get(field)
        if raw_value is None:
            continue
        normalized = _normalize_match_key(raw_value)
        if normalized:
            keys.add(normalized)
    return keys


def _match_alignment_payloads(
    *,
    accessories: Sequence[_AccessoryPlistUpload],
    alignment_payloads: Sequence[_NamedBytesPayload],
) -> dict[str, bytes]:
    """Match uploaded key-alignment plists to accessory plists."""
    match_index = _build_accessory_match_index(accessories)
    matched_alignments: dict[str, bytes] = {}

    for filename, payload in alignment_payloads:
        parsed = _load_plist_mapping(payload)
        display_name = _alignment_display_name(filename)
        match_keys = _matching_keys_from_mapping(parsed)
        fallback_key = _normalize_match_key(display_name)
        if fallback_key:
            match_keys.add(fallback_key)

        matches = {
            accessory.filename
            for match_key in match_keys
            for accessory in match_index.get(match_key, ())
        }
        if len(matches) != 1:
            raise ValueError(
                f"Alignment plist does not match an uploaded accessory: {display_name}"
            )

        accessory_filename = matches.pop()
        if accessory_filename in matched_alignments:
            raise ValueError(
                f"Multiple alignment plists match uploaded accessory: {accessory_filename}"
            )
        matched_alignments[accessory_filename] = payload

    return matched_alignments


def _build_accessory_match_index(
    accessories: Sequence[_AccessoryPlistUpload],
) -> dict[str, tuple[_AccessoryPlistUpload, ...]]:
    """Index uploaded accessory plists by all known alignment match keys."""
    indexed: dict[str, list[_AccessoryPlistUpload]] = {}
    for accessory in accessories:
        for match_key in accessory.match_keys:
            indexed.setdefault(match_key, []).append(accessory)
    return {key: tuple(value) for key, value in indexed.items()}


def _alignment_display_name(filename: str) -> str:
    """Return a human-readable accessory name implied by an alignment filename."""
    stem = _strip_plist_suffix(filename)
    lowered = stem.casefold()
    for suffix in _ALIGNMENT_FILENAME_SUFFIXES:
        if lowered.endswith(suffix):
            return stem[: -len(suffix)]
    return stem


def _accessory_display_name(accessory_upload: _AccessoryPlistUpload) -> str | None:
    """Return the uploaded accessory name if the plist or filename provides one."""
    raw_name = accessory_upload.parsed.get("name")
    if isinstance(raw_name, str) and raw_name:
        return raw_name

    filename_stem = _strip_plist_suffix(accessory_upload.filename)
    return filename_stem or None


def _strip_plist_suffix(filename: str) -> str:
    """Return the basename without a trailing plist extension."""
    basename = Path(filename).name
    if basename.casefold().endswith(".plist"):
        return basename[:-6]
    return basename


def _normalize_match_key(value: object) -> str:
    """Normalize user-facing plist names and identifiers for matching."""
    return re.sub(r"[^a-z0-9]+", "", str(value).casefold())
