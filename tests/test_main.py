"""Tests for app startup behavior in __main__.py."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import FastAPI
from fastapi.testclient import TestClient
import lost_apple_app.__main__ as app_main
from lost_apple_app.auth import AuthState
from lost_apple_app.storage import AppStorage
import pytest

if TYPE_CHECKING:
    from pathlib import Path

PAIRING_TOKEN = "test-token"


class FakeScheduler:
    """Minimal polling scheduler with observable lifecycle calls."""

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        """Initialize scheduler counters."""
        self.starts = 0
        self.stops = 0

    async def start(self) -> None:
        """Count startup invocations."""
        self.starts += 1

    async def stop(self) -> None:
        """Count shutdown invocations."""
        self.stops += 1


class FakeAccount:
    """Fake loaded account with observable cleanup."""

    def __init__(self) -> None:
        """Initialize cleanup counter."""
        self.close_calls = 0

    async def close(self) -> None:
        """Record account cleanup."""
        self.close_calls += 1


def test_build_app_starts_and_stops_polling_scheduler(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The app should trigger polling scheduler start/stop from lifecycle events."""
    fake_scheduler = FakeScheduler()

    monkeypatch.setattr(
        app_main,
        "PollingScheduler",
        lambda *_args, **_kwargs: fake_scheduler,
    )
    monkeypatch.setenv("LOST_APPLE_DB", str(tmp_path / "lost_apple.sqlite3"))
    monkeypatch.setenv("LOST_APPLE_PAIRING_TOKEN", PAIRING_TOKEN)

    app = app_main.build_app()
    with TestClient(app):
        pass

    assert fake_scheduler.starts == 1
    assert fake_scheduler.stops == 1


def test_build_app_returns_sync_uvicorn_factory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """build_app() should return an ASGI app directly for uvicorn factory mode."""
    monkeypatch.setenv("LOST_APPLE_DB", str(tmp_path / "lost_apple.sqlite3"))
    monkeypatch.setenv("LOST_APPLE_PAIRING_TOKEN", PAIRING_TOKEN)

    app = app_main.build_app()

    assert isinstance(app, FastAPI)


async def test_polling_service_builder_closes_account_on_source_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Invalid persisted sources should close a loaded account before returning."""
    storage = AppStorage(tmp_path / "lost_apple.sqlite3")
    await storage.initialize()
    await storage.set_account_state(AuthState.AUTHENTICATED)
    await storage.save_apple_session({"type": "account"})
    await storage.save_apple_sources([{"invalid": "source"}])
    account = FakeAccount()

    monkeypatch.setattr(app_main, "load_apple_account", lambda _payload: account)

    def _raise_source_error(_payloads: object) -> object:
        """Simulate invalid source payloads after account hydration."""
        error_message = "invalid sources"
        raise ValueError(error_message)

    monkeypatch.setattr(app_main, "build_sources_from_payloads", _raise_source_error)

    service = await app_main._build_service_for_polling(storage)

    assert service is None
    assert account.close_calls == 1
    assert await storage.get_account_state() == AuthState.REAUTH_REQUIRED
    assert await storage.get_apple_session() is None
    assert await storage.get_apple_sources() is None
