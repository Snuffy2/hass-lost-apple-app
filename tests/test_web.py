"""Tests for web-facing setup routes in the Lost Apple App."""

# mypy: disable_error_code=import-untyped

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi.testclient import TestClient
from findmy.reports import LoginState
from lost_apple_app.__main__ import build_app
from lost_apple_app.auth import AuthState
from lost_apple_app.storage import AppStorage
from lost_apple_app.web import HACS_INSTALL_URL
import pytest

if TYPE_CHECKING:
    from pathlib import Path

    from fastapi import FastAPI

HTTP_STATUS_OK = 200
HTTP_STATUS_BAD_REQUEST = 400
PAIRING_TOKEN = "test-token"
VALID_USERNAME = "apple_user"
VALID_PASSWORD = "apple_pass"
SOURCE_PAYLOAD_COUNT = 2


class Fake2faMethod:
    """Fake 2FA method object with request/submit behavior."""

    def __init__(self, code_return_state: LoginState = LoginState.REQUIRE_2FA) -> None:
        """Initialize request/submit counters and optional final state."""
        self.request_calls = 0
        self.submit_calls = 0
        self.code_return_state = code_return_state
        self.code: str | None = None
        self.phone_number = "(555) 000-0001"

    async def request(self) -> None:
        """Simulate requesting a one-time code."""
        self.request_calls += 1

    async def submit(self, code: str) -> LoginState:
        """Simulate submitting a one-time code."""
        self.submit_calls += 1
        self.code = code
        return self.code_return_state


class FakeAppleAccount:
    """Fake FindMy async account exposing the minimal setup surface."""

    def __init__(
        self,
        login_state: LoginState = LoginState.REQUIRE_2FA,
        methods: list[Fake2faMethod] | None = None,
    ) -> None:
        """Initialize login state and any configured fake 2FA methods."""
        self.login_state = login_state
        self._methods = methods or []
        self.close_calls = 0

    async def login(self, _username: str, _password: str) -> LoginState:
        """Simulate a username/password login."""
        return self.login_state

    async def get_2fa_methods(self) -> list[Fake2faMethod]:
        """Return any fake 2FA methods configured for this account."""
        return self._methods

    def to_json(self) -> dict[str, object]:
        """Serialize a simple account payload for restart persistence."""
        return {
            "type": "account",
            "account": {"username": VALID_USERNAME, "password": VALID_PASSWORD},
            "login": {"state": self.login_state.value},
        }

    async def close(self) -> None:
        """Track that account resources were closed."""
        self.close_calls += 1


def _authorization_headers(token: str) -> dict[str, str]:
    """Build an Authorization header value used by protected API routes."""
    return {"Authorization": f"Bearer {token}"}


def _setup_authorization_headers() -> dict[str, str]:
    """Build Authorization headers for setup mutation routes."""
    return _authorization_headers(PAIRING_TOKEN)


async def _make_app(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> FastAPI:
    """Create a test app and bind it to an isolated AppStorage."""
    database_path = tmp_path / "lost_apple.sqlite3"
    storage = AppStorage(database_path)
    await storage.initialize()
    monkeypatch.setenv("LOST_APPLE_DB", str(database_path))
    monkeypatch.setenv("LOST_APPLE_PAIRING_TOKEN", PAIRING_TOKEN)
    return build_app()


@pytest.mark.anyio
async def test_setup_page_includes_configuration_sections(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Setup page should expose login, 2FA, and source import sections."""
    app = await _make_app(tmp_path, monkeypatch)
    client = TestClient(app)

    response = client.get("/setup")

    assert response.status_code == HTTP_STATUS_OK

    body = response.text
    for fragment in (
        "Lost Apple App Setup",
        "Apple account login",
        "Setup access",
        "Pairing token",
        "Two-factor authentication",
        "Find My source import",
        "Install through HACS",
        HACS_INSTALL_URL,
        'postJson("login"',
        'postJson("2fa/request"',
        'postJson("2fa/submit"',
        'postJson("sources"',
        'fetch(setupUrl("2fa/methods")',
    ):
        assert fragment in body


@pytest.mark.anyio
async def test_app_root_redirects_to_setup_page(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ingress panel root should redirect without escaping the ingress prefix."""
    app = await _make_app(tmp_path, monkeypatch)
    client = TestClient(app, follow_redirects=False)

    response = client.get("/")

    assert response.status_code == 307
    assert response.headers["location"] == "setup"


@pytest.mark.anyio
async def test_setup_mutation_routes_require_pairing_token(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Setup mutation routes should reject missing or invalid pairing tokens."""
    app = await _make_app(tmp_path, monkeypatch)
    client = TestClient(app)

    response = client.post(
        "/setup/login",
        json={"username": VALID_USERNAME, "password": VALID_PASSWORD},
    )
    invalid_response = client.post(
        "/setup/sources",
        headers=_authorization_headers("wrong-token"),
        json={"sources": [{"id": "airtag-001"}]},
    )

    assert response.status_code == 401
    assert invalid_response.status_code == 401


@pytest.mark.anyio
async def test_login_saves_session_and_updates_health_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Login stores account session/state and exposes auth state through health."""
    account = FakeAppleAccount(
        login_state=LoginState.REQUIRE_2FA,
        methods=[Fake2faMethod()],
    )
    monkeypatch.setattr(
        "lost_apple_app.web.AsyncAppleAccount",
        lambda _provider: account,
    )
    app = await _make_app(tmp_path, monkeypatch)
    client = TestClient(app)

    response = client.post(
        "/setup/login",
        headers=_setup_authorization_headers(),
        json={"username": VALID_USERNAME, "password": VALID_PASSWORD},
    )
    assert response.status_code == HTTP_STATUS_OK

    payload = response.json()
    assert payload["state"] == str(LoginState.REQUIRE_2FA)

    storage = AppStorage(tmp_path / "lost_apple.sqlite3")
    await storage.initialize()
    assert await storage.get_account_state() == AuthState.NOT_CONFIGURED
    assert await storage.get_apple_session() is None

    health_response = client.get(
        "/api/v1/health",
        headers=_authorization_headers(PAIRING_TOKEN),
    )
    assert health_response.status_code == HTTP_STATUS_OK
    assert health_response.json()["account_state"] == "not_configured"


@pytest.mark.anyio
async def test_login_handles_immediate_authenticated_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Login should not request 2FA methods after an authenticated login."""

    class AlreadyAuthenticatedAccount(FakeAppleAccount):
        """Fake account that fails if 2FA methods are requested."""

        async def get_2fa_methods(self) -> list[Fake2faMethod]:
            """Raise if the route asks for methods outside REQUIRE_2FA."""
            error_message = "2FA methods should not be requested"
            raise AssertionError(error_message)

    account = AlreadyAuthenticatedAccount(login_state=LoginState.LOGGED_IN)
    monkeypatch.setattr(
        "lost_apple_app.web.AsyncAppleAccount",
        lambda _provider: account,
    )
    app = await _make_app(tmp_path, monkeypatch)
    client = TestClient(app)

    response = client.post(
        "/setup/login",
        headers=_setup_authorization_headers(),
        json={"username": VALID_USERNAME, "password": VALID_PASSWORD},
    )

    assert response.status_code == HTTP_STATUS_OK
    payload = response.json()
    assert payload["account_state"] == "authenticated"
    assert payload["methods"] == []
    assert account.close_calls == 1

    storage = AppStorage(tmp_path / "lost_apple.sqlite3")
    await storage.initialize()
    session = await storage.get_apple_session()
    assert session is not None
    assert session["account"] == {"username": VALID_USERNAME, "password": None}


@pytest.mark.anyio
async def test_submit_two_factor_authentication_completes_login(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """2FA submit endpoint should persist authenticated state when state transitions."""
    account = FakeAppleAccount(
        login_state=LoginState.REQUIRE_2FA,
        methods=[Fake2faMethod(code_return_state=LoginState.AUTHENTICATED)],
    )
    monkeypatch.setattr(
        "lost_apple_app.web.AsyncAppleAccount",
        lambda _provider: account,
    )
    storage = AppStorage(tmp_path / "lost_apple.sqlite3")
    await storage.initialize()
    app = await _make_app(tmp_path, monkeypatch)
    client = TestClient(app)

    login_response = client.post(
        "/setup/login",
        headers=_setup_authorization_headers(),
        json={"username": VALID_USERNAME, "password": VALID_PASSWORD},
    )
    assert login_response.status_code == HTTP_STATUS_OK

    request_payload = {"method_index": 0}
    request_response = client.post(
        "/setup/2fa/request",
        headers=_setup_authorization_headers(),
        json=request_payload,
    )
    assert request_response.status_code == HTTP_STATUS_OK

    submit_payload = {"method_index": 0, "code": "123456"}
    submit_response = client.post(
        "/setup/2fa/submit",
        headers=_setup_authorization_headers(),
        json=submit_payload,
    )
    assert submit_response.status_code == HTTP_STATUS_OK

    submit_payload = submit_response.json()
    assert submit_payload["state"] == str(LoginState.AUTHENTICATED)
    assert submit_payload["account_state"] == "authenticated"

    assert await storage.get_account_state() == AuthState.AUTHENTICATED
    session = await storage.get_apple_session()
    assert session is not None
    assert session["account"] == {"username": VALID_USERNAME, "password": None}
    assert account.close_calls == 1


@pytest.mark.anyio
async def test_setup_sources_import_requires_valid_json_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Source import endpoint requires a non-empty JSON source list."""
    app = await _make_app(tmp_path, monkeypatch)
    client = TestClient(app)

    empty_response = client.post(
        "/setup/sources",
        headers=_setup_authorization_headers(),
        json={"sources": []},
    )
    assert empty_response.status_code == HTTP_STATUS_BAD_REQUEST


@pytest.mark.anyio
async def test_setup_sources_import_persists_payloads_with_patched_parsers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Source import stores normalized payloads after parser mapping."""

    class FakeSource:
        """Small source stand-in to verify parser normalization."""

        def __init__(self, source_id: str, name: str) -> None:
            """Store fixed identifier and display name."""
            self.id = source_id
            self.name = name

    monkeypatch.setattr(
        "lost_apple_app.web.build_sources_from_payloads",
        lambda _sources: [
            FakeSource(source_id="airtag-001", name="Keys"),
            FakeSource(source_id="airtag-002", name="Wallet"),
        ],
    )
    monkeypatch.setattr(
        "lost_apple_app.web.serialize_accessory_payloads",
        lambda _sources: [
            {"id": "airtag-001", "name": "Keys"},
            {"id": "airtag-002", "name": "Wallet"},
        ],
    )

    app = await _make_app(tmp_path, monkeypatch)
    client = TestClient(app)

    response = client.post(
        "/setup/sources",
        headers=_setup_authorization_headers(),
        json={
            "sources": [
                {"id": "airtag-001"},
                {"id": "airtag-002"},
            ]
        },
    )
    assert response.status_code == HTTP_STATUS_OK

    payload = response.json()
    assert payload["source_count"] == SOURCE_PAYLOAD_COUNT

    storage = AppStorage(tmp_path / "lost_apple.sqlite3")
    await storage.initialize()
    assert await storage.get_apple_sources() == [
        {"id": "airtag-001", "name": "Keys"},
        {"id": "airtag-002", "name": "Wallet"},
    ]
