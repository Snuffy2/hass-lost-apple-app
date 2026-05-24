"""Tests for FindMy.py adapter normalization."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import plistlib

from lost_apple_app.findmy_client import (
    FindMyDevice,
    FindMyService,
    FindMySource,
    build_sources_from_plist_payloads,
    normalize_findmy_device,
    normalize_findmy_report,
    serialize_accessory_payloads,
    serialize_apple_account_state,
)
import pytest


@dataclass(frozen=True, slots=True)
class RawLocation:
    """Fake FindMy.py location object."""

    latitude: float = 40.7128
    longitude: float = -74.006
    horizontal_accuracy: float | None = 12.4
    timestamp: datetime = datetime(2026, 5, 23, 20, 30, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class RawDevice:
    """Fake FindMy.py official device object."""

    identifier: object = "airtag-001"
    name: object = "Keys"
    battery_status: str | None = "medium"
    location: RawLocation = field(default_factory=RawLocation)


@dataclass(frozen=True, slots=True)
class LocationReport:
    """Fake FindMy.py location report."""

    latitude: float = 40.7128
    longitude: float = -74.006
    horizontal_accuracy: float | None = 12.4
    timestamp: datetime = datetime(2026, 5, 23, 20, 30, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class FindMyKey:
    """Fake key/accessory source identifier used by account.fetch_location()."""

    hashed_adv_key_bytes: bytes


@dataclass(frozen=True, slots=True)
class FakeFindMyAccount:
    """Fake account implementing find_location() with deterministic responses."""

    mapping: dict[object, LocationReport | None]

    async def fetch_location(self, key: object) -> LocationReport | None:
        """Return report for key or ``None`` when unavailable."""
        return self.mapping.get(key)


class FakeSerializableAccount:
    """Fake account state source including a password that must not persist."""

    def to_json(self) -> dict[str, object]:
        """Return account state in the same sensitive shape as FindMy.py."""
        return {
            "type": "account",
            "account": {"username": "user@example.com", "password": "secret"},
        }


def _make_accessory_plist(
    *,
    identifier: str = "airtag-001",
    name: str = "Keys",
    pairing_date: datetime = datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
) -> bytes:
    """Build a minimal FindMy.py-compatible accessory plist payload."""
    payload = {
        "privateKey": {"key": {"data": b"\x01" * 32}},
        "sharedSecret": {"key": {"data": b"\x02" * 32}},
        "secondarySharedSecret": {"key": {"data": b"\x03" * 32}},
        "publicKey": b"\x04" * 65,
        "identifier": identifier,
        "model": "AirTag",
        "pairingDate": pairing_date,
        "name": name,
        "emoji": "",
    }
    return plistlib.dumps(payload)


def _make_alignment_plist(
    *,
    index: int = 42,
    observed_at: datetime = datetime(2026, 5, 2, 12, 0, tzinfo=UTC),
) -> bytes:
    """Build a minimal FindMy.py-compatible key-alignment plist payload."""
    return plistlib.dumps(
        {
            "lastIndexObservationDate": observed_at,
            "lastIndexObserved": index,
        }
    )


def test_normalize_findmy_device() -> None:
    """Raw FindMy.py device is normalized for polling."""
    normalized = normalize_findmy_device(RawDevice())
    expected = FindMyDevice(
        id="airtag-001",
        name="Keys",
        latitude=40.7128,
        longitude=-74.006,
        accuracy_m=12.4,
        battery_status="medium",
        last_reported_at=RawLocation().timestamp,
    )
    if normalized != expected:
        message = "Normalized device did not match expected output"
        raise AssertionError(message)


def test_normalize_findmy_report() -> None:
    """Location report is normalized into configured source metadata."""
    source = FindMySource(
        id="airtag-001",
        name="Keys",
        findmy_key_or_accessory=FindMyKey(b"airtag"),
        battery_status="medium",
    )
    normalized = normalize_findmy_report(source=source, report=LocationReport())
    expected = FindMyDevice(
        id="airtag-001",
        name="Keys",
        latitude=40.7128,
        longitude=-74.006,
        accuracy_m=12.4,
        battery_status="medium",
        last_reported_at=LocationReport().timestamp,
    )
    if normalized != expected:
        message = "Normalized report did not match configured source metadata"
        raise AssertionError(message)


async def test_fetch_devices_returns_empty_when_account_is_missing() -> None:
    """FindMyService returns empty list when account is missing."""
    service = FindMyService(
        sources=[
            FindMySource(
                id="airtag-001",
                name="Keys",
                findmy_key_or_accessory=FindMyKey(b"airtag"),
            )
        ]
    )
    devices = await service.fetch_devices()
    if devices != []:
        message = "Service without account should return an empty list"
        raise AssertionError(message)


async def test_fetch_devices_returns_empty_when_sources_are_missing() -> None:
    """FindMyService returns empty list when sources are missing."""
    service = FindMyService(account=FakeFindMyAccount({}))
    devices = await service.fetch_devices()
    if devices != []:
        message = "Service without sources should return an empty list"
        raise AssertionError(message)


async def test_fetch_devices_normalizes_account_locations() -> None:
    """FindMyService normalizes reports from account.fetch_location()."""
    key = FindMyKey(b"airtag")
    source = FindMySource(
        id="airtag-001",
        name="Keys",
        findmy_key_or_accessory=key,
        battery_status="medium",
    )
    account = FakeFindMyAccount({key: LocationReport()})
    service = FindMyService(account=account, sources=[source])
    devices = await service.fetch_devices()
    if devices != [normalize_findmy_report(source=source, report=LocationReport())]:
        message = "Service should normalize each location report by configured source"
        raise AssertionError(message)


async def test_fetch_devices_skips_missing_location_reports() -> None:
    """FindMyService skips configured sources that return no location report."""
    key = FindMyKey(b"airtag")
    source = FindMySource(
        id="airtag-001",
        name="Keys",
        findmy_key_or_accessory=key,
        battery_status="medium",
    )
    account = FakeFindMyAccount({key: None})
    service = FindMyService(account=account, sources=[source])
    if await service.fetch_devices() != []:
        message = "Service should skip missing location reports instead of failing"
        raise AssertionError(message)


def test_serialize_apple_account_state_drops_password() -> None:
    """Persisted Apple account state must not include the Apple password."""
    state = serialize_apple_account_state(FakeSerializableAccount())
    if state["account"] != {"username": "user@example.com", "password": None}:
        message = "Serialized account state should redact the Apple password"
        raise AssertionError(message)


def test_build_sources_from_plist_payloads_pairs_alignment_by_filename() -> None:
    """Accessory plist imports should pair matching alignment plists by file stem."""
    sources = build_sources_from_plist_payloads(
        accessory_payloads=[("Keys.plist", _make_accessory_plist())],
        alignment_payloads=[("Keys.alignment.plist", _make_alignment_plist())],
    )
    serialized = serialize_accessory_payloads(
        [source.findmy_key_or_accessory for source in sources]
    )

    assert len(sources) == 1
    assert sources[0].id == "airtag-001"
    assert sources[0].name == "Keys"
    assert serialized[0]["alignment_index"] == 42
    assert serialized[0]["alignment_date"] == "2026-05-02T12:00:00+00:00"


def test_build_sources_from_plist_payloads_rejects_unmatched_alignment() -> None:
    """Alignment plists should not be accepted when no accessory match is possible."""
    with pytest.raises(
        ValueError,
        match="Alignment plist does not match an uploaded accessory: Wallet",
    ):
        build_sources_from_plist_payloads(
            accessory_payloads=[("Keys.plist", _make_accessory_plist())],
            alignment_payloads=[("Wallet.alignment.plist", _make_alignment_plist())],
        )
