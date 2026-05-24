"""FastAPI application factory for the Lost Apple app."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
import secrets
from typing import TYPE_CHECKING, Literal

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from lost_apple_app.auth import AuthState
from lost_apple_app.models import AppHealth, DeviceSnapshot

if TYPE_CHECKING:
    from lost_apple_app.storage import AppStorage


INVALID_TOKEN_MESSAGE = "Invalid pairing token"  # noqa: S105


def _requires_pairing_token(path: str) -> bool:
    """Return whether the request path requires pairing-token authentication."""
    if path.startswith("/api/v1/"):
        return True
    return path.startswith("/setup/") and path != "/setup/"


def create_app(storage: AppStorage, pairing_token: str, app_version: str) -> FastAPI:
    """Build the Lost Apple FastAPI app with pairing-token authentication."""
    if not pairing_token.strip():
        message = "pairing_token must be a non-empty value"
        raise ValueError(message)
    app = FastAPI()

    @app.middleware("http")
    async def _require_pairing_token(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Reject unauthenticated requests to app API routes."""
        if _requires_pairing_token(request.url.path):
            authorization = request.headers.get("Authorization")
            if authorization is None or not authorization.startswith("Bearer "):
                return JSONResponse(
                    status_code=401,
                    content={"detail": INVALID_TOKEN_MESSAGE},
                )
            token = authorization.removeprefix("Bearer ")
            if not token or not secrets.compare_digest(token, pairing_token):
                return JSONResponse(
                    status_code=401,
                    content={"detail": INVALID_TOKEN_MESSAGE},
                )
        return await call_next(request)

    @app.get("/api/v1/health", response_model=AppHealth)
    async def health() -> AppHealth:
        """Return app health including polling interval and known device count."""
        snapshots = await storage.list_snapshots()
        polling_interval_minutes = await storage.get_polling_interval_minutes()
        account_state = await storage.get_account_state()
        account_state_literal: Literal[
            "not_configured",
            "authenticated",
            "reauth_required",
        ]
        if account_state == AuthState.NOT_CONFIGURED:
            account_state_literal = "not_configured"
        elif account_state == AuthState.AUTHENTICATED:
            account_state_literal = "authenticated"
        else:
            account_state_literal = "reauth_required"
        return AppHealth(
            api_version=1,
            app_version=app_version,
            account_state=account_state_literal,
            polling_interval_minutes=polling_interval_minutes,
            device_count=len(snapshots),
        )

    @app.get("/api/v1/devices", response_model=list[DeviceSnapshot])
    async def devices() -> list[DeviceSnapshot]:
        """Return normalized device snapshots from storage."""
        return await storage.list_snapshots()

    return app
