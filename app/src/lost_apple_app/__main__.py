"""Application entrypoint for the Lost Apple App."""

# mypy: disable_error_code=import-untyped

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Final

from findmy.errors import InvalidStateError
import uvicorn

from lost_apple_app.api import create_app
from lost_apple_app.auth import AuthState
from lost_apple_app.config import resolve_pairing_token
from lost_apple_app.const import VERSION
from lost_apple_app.findmy_client import (
    FindMyService,
    build_sources_from_payloads,
    load_apple_account,
)
from lost_apple_app.polling import PollingScheduler
from lost_apple_app.storage import AppStorage
from lost_apple_app.web import register_web_routes

if TYPE_CHECKING:
    from fastapi import FastAPI

DEFAULT_DATABASE_PATH: Final = "/data/lost_apple.sqlite3"


def _resolve_database_path() -> Path:
    """Return the configured database path from the environment."""
    configured = os.getenv("LOST_APPLE_DB", DEFAULT_DATABASE_PATH)
    return Path(configured)


def _resolve_app_version() -> str:
    """Return the app version from env or default."""
    return os.getenv("LOST_APPLE_APP_VERSION", VERSION)


async def _build_service_for_polling(storage: AppStorage) -> FindMyService | None:
    """Build a polling service if account/session and sources are both present."""
    account = None
    account_state = await storage.get_account_state()
    if account_state != AuthState.AUTHENTICATED:
        return None

    account_payload = await storage.get_apple_session()
    if not account_payload:
        return None

    source_payloads = await storage.get_apple_sources()
    if not source_payloads:
        return None

    try:
        account = load_apple_account(account_payload)
        sources = build_sources_from_payloads(source_payloads)
    except InvalidStateError, TypeError, ValueError:
        if account is not None:
            await account.close()
        await storage.set_account_state(AuthState.REAUTH_REQUIRED)
        await storage.clear_apple_session()
        await storage.clear_apple_sources()
        return None

    return FindMyService(account=account, sources=sources)


def build_app() -> FastAPI:
    """Create and return the ASGI app for FastAPI startup."""
    storage = AppStorage(_resolve_database_path())
    app = create_app(
        storage=storage,
        pairing_token=resolve_pairing_token(dict(os.environ)),
        app_version=_resolve_app_version(),
    )
    scheduler = PollingScheduler(
        storage=storage,
        service_factory=lambda: _build_service_for_polling(storage),
    )
    register_web_routes(app, storage)

    @app.on_event("startup")
    async def _start_polling() -> None:
        """Start background polling when auth and sources are configured."""
        await storage.initialize()
        await scheduler.start()

    @app.on_event("shutdown")
    async def _stop_polling() -> None:
        """Stop background polling and cleanly cancel async polling task."""
        await scheduler.stop()

    return app


def main() -> None:
    """Run the ASGI app with uvicorn in factory mode."""
    uvicorn.run(
        "lost_apple_app.__main__:build_app",
        host="0.0.0.0",  # noqa: S104
        port=8099,
        factory=True,
    )


if __name__ == "__main__":
    main()
