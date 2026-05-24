"""Polling service for FindMy devices."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import logging
from typing import TYPE_CHECKING

from lost_apple_app.models import DeviceSnapshot

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from lost_apple_app.findmy_client import FindMyService
    from lost_apple_app.storage import AppStorage

_LOGGER = logging.getLogger(__name__)

_MIN_SLEEP_SECONDS = 5


class PollingService:
    """Poll FindMy.py and persist latest normalized device snapshots."""

    def __init__(
        self,
        storage: AppStorage,
        findmy: FindMyService,
    ) -> None:
        """Initialize the polling service."""
        self._storage = storage
        self._findmy = findmy

    async def poll_once(self, now: datetime | None = None) -> None:
        """Poll FindMy.py once and persist normalized snapshots."""
        polled_at = now or datetime.now(tz=UTC)
        devices = await self._findmy.fetch_devices()
        for device in devices:
            await self._storage.upsert_snapshot(
                DeviceSnapshot(
                    id=device.id,
                    name=device.name,
                    latitude=device.latitude,
                    longitude=device.longitude,
                    accuracy_m=device.accuracy_m,
                    battery_status=device.battery_status,
                    status="ok",
                    last_reported_at=device.last_reported_at,
                    last_polled_at=polled_at,
                    error=None,
                ),
            )


class PollingScheduler:
    """Background polling runner with App data-driven readiness checks."""

    def __init__(
        self,
        storage: AppStorage,
        service_factory: Callable[[], Awaitable[FindMyService | None]],
    ) -> None:
        """Initialize the scheduler."""
        self._storage = storage
        self._service_factory = service_factory
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Start a background polling task if not already active."""
        if self._task is not None and not self._task.done():
            return
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        """Stop background polling and await cancellation."""
        task = self._task
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            _LOGGER.debug("Polling scheduler task cancelled")
        self._task = None

    async def run_once(self) -> None:
        """Run one scheduled polling attempt if enough inputs are ready."""
        service = await self._service_factory()
        if service is None:
            return

        try:
            await PollingService(storage=self._storage, findmy=service).poll_once()
        finally:
            await service.close()

    async def _run(self) -> None:
        """Poll at a steady configured interval until cancelled."""
        while True:
            try:
                await self.run_once()
            except OSError, RuntimeError, TypeError, ValueError:
                _LOGGER.exception("Polling run failed")

            interval_minutes = await self._storage.get_polling_interval_minutes()
            delay_seconds = max(_MIN_SLEEP_SECONDS, interval_minutes * 60)
            await asyncio.sleep(delay_seconds)
