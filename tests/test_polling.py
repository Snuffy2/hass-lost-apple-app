"""Tests for polling Find My devices."""

from __future__ import annotations

import datetime
from datetime import UTC
from typing import TYPE_CHECKING

from lost_apple_app.findmy_client import FindMyDevice, FindMyService
from lost_apple_app.models import DeviceSnapshot
from lost_apple_app.polling import PollingScheduler, PollingService
from lost_apple_app.storage import AppStorage

if TYPE_CHECKING:
    from pathlib import Path


DEVICE_ID = "airtag-001"
DEVICE_NAME = "Keys"
LATITUDE = 40.7128
LONGITUDE = -74.0060
ACCURACY_METERS = 12.4
BATTERY_STATUS = "medium"
LAST_REPORTED_YEAR = 2026
LAST_REPORTED_MONTH = 5
LAST_REPORTED_DAY = 23
LAST_REPORTED_HOUR = 20
LAST_REPORTED_MINUTE = 30
LAST_REPORTED_SECOND = 0
LAST_POLLED_MINUTE = 35
LAST_POLLED_SECOND = 0


class FakeFindMyService(FindMyService):
    """Fake FindMy service returning deterministic devices."""

    async def fetch_devices(self) -> list[FindMyDevice]:
        """Return a deterministic fake device."""
        return [
            FindMyDevice(
                id=DEVICE_ID,
                name=DEVICE_NAME,
                latitude=LATITUDE,
                longitude=LONGITUDE,
                accuracy_m=ACCURACY_METERS,
                battery_status=BATTERY_STATUS,
                last_reported_at=datetime.datetime(
                    LAST_REPORTED_YEAR,
                    LAST_REPORTED_MONTH,
                    LAST_REPORTED_DAY,
                    LAST_REPORTED_HOUR,
                    LAST_REPORTED_MINUTE,
                    LAST_REPORTED_SECOND,
                    tzinfo=UTC,
                ),
            )
        ]


class ClosableFindMyService(FakeFindMyService):
    """Fake service that records close calls."""

    def __init__(self) -> None:
        """Initialize close counter."""
        super().__init__()
        self.close_calls = 0

    async def close(self) -> None:
        """Record scheduler cleanup."""
        self.close_calls += 1


async def test_poll_once_stores_snapshots(tmp_path: Path) -> None:
    """Polling once stores normalized snapshots."""
    storage = AppStorage(tmp_path / "lost_apple.sqlite3")
    await storage.initialize()
    service = PollingService(storage=storage, findmy=FakeFindMyService())

    poll_time = datetime.datetime(
        LAST_REPORTED_YEAR,
        LAST_REPORTED_MONTH,
        LAST_REPORTED_DAY,
        LAST_REPORTED_HOUR,
        LAST_POLLED_MINUTE,
        LAST_POLLED_SECOND,
        tzinfo=UTC,
    )
    await service.poll_once(now=poll_time)

    snapshots = await storage.list_snapshots()
    expected = [
        DeviceSnapshot(
            id=DEVICE_ID,
            name=DEVICE_NAME,
            latitude=LATITUDE,
            longitude=LONGITUDE,
            accuracy_m=ACCURACY_METERS,
            battery_status=BATTERY_STATUS,
            status="ok",
            last_reported_at=datetime.datetime(
                LAST_REPORTED_YEAR,
                LAST_REPORTED_MONTH,
                LAST_REPORTED_DAY,
                LAST_REPORTED_HOUR,
                LAST_REPORTED_MINUTE,
                LAST_REPORTED_SECOND,
                tzinfo=UTC,
            ),
            last_polled_at=poll_time,
            error=None,
        )
    ]
    assert snapshots == expected


async def test_polling_scheduler_run_once_uses_factory_result(
    tmp_path: Path,
) -> None:
    """Scheduler run_once should call service factory."""
    storage = AppStorage(tmp_path / "lost_apple.sqlite3")
    await storage.initialize()

    call_count = 0

    async def _service_factory() -> FindMyService:
        nonlocal call_count
        call_count += 1
        return FakeFindMyService()

    scheduler = PollingScheduler(storage=storage, service_factory=_service_factory)
    await scheduler.run_once()
    assert call_count == 1


async def test_polling_scheduler_closes_factory_service(
    tmp_path: Path,
) -> None:
    """Scheduler run_once should close account-backed services after polling."""
    storage = AppStorage(tmp_path / "lost_apple.sqlite3")
    await storage.initialize()
    service = ClosableFindMyService()

    async def _service_factory() -> FindMyService:
        return service

    scheduler = PollingScheduler(storage=storage, service_factory=_service_factory)
    await scheduler.run_once()

    assert service.close_calls == 1


async def test_polling_scheduler_run_once_skips_when_factory_returns_none(
    tmp_path: Path,
) -> None:
    """Scheduler run_once is a no-op when factory returns None."""
    storage = AppStorage(tmp_path / "lost_apple.sqlite3")
    await storage.initialize()
    call_count = 0

    async def _service_factory() -> FindMyService | None:
        nonlocal call_count
        call_count += 1
        return None

    scheduler = PollingScheduler(storage=storage, service_factory=_service_factory)
    await scheduler.run_once()

    assert call_count == 1
