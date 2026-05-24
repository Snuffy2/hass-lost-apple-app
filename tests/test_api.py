"""Tests for Lost Apple HTTP API."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from fastapi.testclient import TestClient
from lost_apple_app.api import create_app
from lost_apple_app.models import DeviceSnapshot
from lost_apple_app.storage import POLLING_INTERVAL_DEFAULT_MINUTES, AppStorage
import pytest

if TYPE_CHECKING:
    from pathlib import Path

AUTHORIZATION_HEADER = "Authorization"
VALID_CREDENTIAL = "test-pairing-token"
INVALID_CREDENTIAL = "invalid"
HEADER_PREFIX = "Bearer "
APP_VERSION = "1.0.0"
API_VERSION = 1
HTTP_STATUS_OK = 200
HTTP_STATUS_UNAUTHORIZED = 401
INVALID_TOKEN_ERROR = "Invalid pairing token"
EMPTY_STRING = ""
WHITESPACE_TOKEN = "   "
DEVICE_ID = "airtag-001"
DEVICE_NAME = "Keys"
LATITUDE = 40.7128
LONGITUDE = -74.0060
ACCURACY_METERS = 12.4
BATTERY_STATUS = "medium"
REPORT_YEAR = 2026
REPORT_MONTH = 5
REPORT_DAY = 23
REPORT_HOUR = 20
REPORT_MINUTE = 30
REPORT_SECOND = 0


def _make_snapshot() -> DeviceSnapshot:
    """Create a stable snapshot fixture used by API tests."""
    return DeviceSnapshot(
        id=DEVICE_ID,
        name=DEVICE_NAME,
        latitude=LATITUDE,
        longitude=LONGITUDE,
        accuracy_m=ACCURACY_METERS,
        battery_status=BATTERY_STATUS,
        status="ok",
        last_reported_at=datetime(
            REPORT_YEAR,
            REPORT_MONTH,
            REPORT_DAY,
            REPORT_HOUR,
            REPORT_MINUTE,
            REPORT_SECOND,
            tzinfo=UTC,
        ),
        last_polled_at=datetime(
            REPORT_YEAR,
            REPORT_MONTH,
            REPORT_DAY,
            REPORT_HOUR,
            REPORT_MINUTE,
            REPORT_SECOND,
            tzinfo=UTC,
        ),
        error=None,
    )


def _make_auth_headers(token: str) -> dict[str, str]:
    """Create an Authorization header value for API requests."""
    return {AUTHORIZATION_HEADER: f"{HEADER_PREFIX}{token}"}


def _assert_response_payload(
    response_status: int,
    expected_status: int,
    response_payload: object,
    expected_payload: object,
    error_message: str,
) -> None:
    """Raise an AssertionError when response status or payload does not match."""
    if response_status != expected_status:
        status_mismatch = f"{error_message} (unexpected status: {response_status})"
        raise AssertionError(status_mismatch)

    if response_payload != expected_payload:
        payload_mismatch = f"{error_message} (unexpected payload: {response_payload})"
        raise AssertionError(payload_mismatch)


async def test_health_endpoint_requires_valid_pairing_token(tmp_path: Path) -> None:
    """Health endpoint rejects missing or invalid pairing tokens."""
    storage = AppStorage(tmp_path / "lost_apple.sqlite3")
    await storage.initialize()
    app = create_app(
        storage=storage,
        pairing_token=VALID_CREDENTIAL,
        app_version=APP_VERSION,
    )
    client = TestClient(app)

    missing_auth_response = client.get("/api/v1/health")
    _assert_response_payload(
        response_status=missing_auth_response.status_code,
        expected_status=HTTP_STATUS_UNAUTHORIZED,
        response_payload=missing_auth_response.json(),
        expected_payload={"detail": INVALID_TOKEN_ERROR},
        error_message="Missing Authorization header should be rejected",
    )

    bad_token_response = client.get(
        "/api/v1/health",
        headers=_make_auth_headers(token=INVALID_CREDENTIAL),
    )
    _assert_response_payload(
        response_status=bad_token_response.status_code,
        expected_status=HTTP_STATUS_UNAUTHORIZED,
        response_payload=bad_token_response.json(),
        expected_payload={"detail": INVALID_TOKEN_ERROR},
        error_message="Invalid pairing token should be rejected",
    )


async def test_health_endpoint_returns_expected_payload(tmp_path: Path) -> None:
    """Health endpoint returns version and polling/device metadata from storage."""
    storage = AppStorage(tmp_path / "lost_apple.sqlite3")
    await storage.initialize()
    await storage.upsert_snapshot(_make_snapshot())
    await storage.set_polling_interval_minutes(POLLING_INTERVAL_DEFAULT_MINUTES)

    app = create_app(
        storage=storage,
        pairing_token=VALID_CREDENTIAL,
        app_version=APP_VERSION,
    )
    client = TestClient(app)

    response = client.get(
        "/api/v1/health",
        headers=_make_auth_headers(token=VALID_CREDENTIAL),
    )

    _assert_response_payload(
        response_status=response.status_code,
        expected_status=HTTP_STATUS_OK,
        response_payload=response.json(),
        expected_payload={
            "api_version": API_VERSION,
            "app_version": APP_VERSION,
            "account_state": "not_configured",
            "polling_interval_minutes": POLLING_INTERVAL_DEFAULT_MINUTES,
            "device_count": 1,
        },
        error_message="Health payload should include app status metadata",
    )


@pytest.mark.parametrize(
    "pairing_token",
    [
        EMPTY_STRING,
        WHITESPACE_TOKEN,
    ],
)
def test_create_app_rejects_blank_pairing_tokens(
    tmp_path: Path,
    pairing_token: str,
) -> None:
    """App factory rejects empty or whitespace-only pairing tokens."""
    storage = AppStorage(tmp_path / "lost_apple.sqlite3")
    with pytest.raises(ValueError, match="pairing_token must be a non-empty value"):
        create_app(
            storage=storage,
            pairing_token=pairing_token,
            app_version=APP_VERSION,
        )


async def test_empty_bearer_token_is_rejected(tmp_path: Path) -> None:
    """Empty bearer token does not authenticate even when configured token is valid."""
    storage = AppStorage(tmp_path / "lost_apple.sqlite3")
    await storage.initialize()
    app = create_app(
        storage=storage,
        pairing_token=VALID_CREDENTIAL,
        app_version=APP_VERSION,
    )
    client = TestClient(app)

    empty_token_response = client.get(
        "/api/v1/health",
        headers=_make_auth_headers(token=EMPTY_STRING),
    )
    _assert_response_payload(
        response_status=empty_token_response.status_code,
        expected_status=HTTP_STATUS_UNAUTHORIZED,
        response_payload=empty_token_response.json(),
        expected_payload={"detail": INVALID_TOKEN_ERROR},
        error_message="Empty bearer token should be rejected",
    )


async def test_devices_endpoint_returns_snapshots(tmp_path: Path) -> None:
    """Devices endpoint returns all snapshots from storage."""
    storage = AppStorage(tmp_path / "lost_apple.sqlite3")
    await storage.initialize()
    await storage.upsert_snapshot(_make_snapshot())

    app = create_app(
        storage=storage,
        pairing_token=VALID_CREDENTIAL,
        app_version=APP_VERSION,
    )
    client = TestClient(app)

    response = client.get(
        "/api/v1/devices",
        headers=_make_auth_headers(token=VALID_CREDENTIAL),
    )

    _assert_response_payload(
        response_status=response.status_code,
        expected_status=HTTP_STATUS_OK,
        response_payload=response.json(),
        expected_payload=[_make_snapshot().model_dump(mode="json")],
        error_message="Devices endpoint should return normalized snapshots",
    )
