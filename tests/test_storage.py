"""Tests for Lost Apple App storage."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from lost_apple_app.auth import AuthState
from lost_apple_app.models import DeviceSnapshot
from lost_apple_app.storage import AppStorage
import pytest

if TYPE_CHECKING:
    from pathlib import Path


async def test_storage_round_trips_device_snapshot(tmp_path: Path) -> None:
    """Store and retrieve a normalized device snapshot."""
    storage = AppStorage(tmp_path / "lost_apple.sqlite3")
    await storage.initialize()
    snapshot = DeviceSnapshot(
        id="airtag-001",
        name="Keys",
        latitude=40.7128,
        longitude=-74.0060,
        accuracy_m=12.4,
        battery_status="medium",
        status="ok",
        last_reported_at=datetime(2026, 5, 23, 20, 30, tzinfo=UTC),
        last_polled_at=datetime(2026, 5, 23, 20, 35, tzinfo=UTC),
        error=None,
    )

    await storage.upsert_snapshot(snapshot)

    assert await storage.list_snapshots() == [snapshot]


async def test_storage_returns_default_polling_interval(tmp_path: Path) -> None:
    """Default polling interval is 15 minutes."""
    storage = AppStorage(tmp_path / "lost_apple.sqlite3")
    await storage.initialize()

    assert await storage.get_polling_interval_minutes() == 15


@pytest.mark.parametrize(
    ("value", "expected_error"),
    [
        (4, "Polling interval must be between 5 and 60 minutes"),
        (61, "Polling interval must be between 5 and 60 minutes"),
    ],
)
async def test_storage_rejects_invalid_polling_intervals(
    tmp_path: Path, value: int, expected_error: str
) -> None:
    """Invalid polling interval values are rejected with a clear error message."""
    storage = AppStorage(tmp_path / "lost_apple.sqlite3")
    await storage.initialize()

    with pytest.raises(ValueError, match=expected_error):
        await storage.set_polling_interval_minutes(value)


async def test_storage_saves_polling_interval(tmp_path: Path) -> None:
    """Persist the user-selected polling interval."""
    storage = AppStorage(tmp_path / "lost_apple.sqlite3")
    await storage.initialize()

    await storage.set_polling_interval_minutes(10)

    assert await storage.get_polling_interval_minutes() == 10


async def test_storage_persists_account_session_and_state(tmp_path: Path) -> None:
    """Store and restore Apple session payloads and auth state."""
    storage = AppStorage(tmp_path / "lost_apple.sqlite3")
    await storage.initialize()

    payload = {"type": "account", "login": {"state": 1}}
    await storage.save_apple_session(payload)
    await storage.set_account_state(AuthState.NOT_CONFIGURED)

    assert await storage.get_apple_session() == payload
    assert await storage.get_account_state() == AuthState.NOT_CONFIGURED

    await storage.clear_apple_session()
    assert await storage.get_apple_session() is None


async def test_storage_persists_source_payloads(tmp_path: Path) -> None:
    """Store and restore accessory payloads used for polling sources."""
    storage = AppStorage(tmp_path / "lost_apple.sqlite3")
    await storage.initialize()

    sources = [{"id": "airtag-001"}, {"id": "airtag-002"}]
    await storage.save_apple_sources(sources)

    assert await storage.get_apple_sources() == sources

    await storage.clear_apple_sources()
    assert await storage.get_apple_sources() is None
