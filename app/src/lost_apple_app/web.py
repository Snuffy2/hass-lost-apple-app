"""Web routes for the Lost Apple App setup UX."""

# mypy: disable_error_code=import-untyped

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from findmy import (
    AsyncAppleAccount,
    AsyncSmsSecondFactor,
    AsyncTrustedDeviceSecondFactor,
    LocalAnisetteProvider,
    LoginState,
)
from findmy.errors import InvalidCredentialsError, InvalidStateError, UnauthorizedError
from pydantic import BaseModel, Field

from lost_apple_app.auth import AuthState
from lost_apple_app.findmy_client import (
    build_sources_from_payloads,
    load_apple_account,
    serialize_accessory_payloads,
    serialize_apple_account_state,
)

if TYPE_CHECKING:
    from fastapi import FastAPI

    from lost_apple_app.storage import AppStorage


HACS_INSTALL_URL = (
    "https://my.home-assistant.io/redirect/hacs_repository/"
    "?owner=snuffy2&repository=hass-lost-apple-integration&category=integration"
)


class LoginRequest(BaseModel):
    """Payload for initiating Apple username/password login."""

    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class TwoFactorMethodRequest(BaseModel):
    """Payload for selecting a 2FA method."""

    method_index: int = Field(ge=0)


class TwoFactorSubmitRequest(TwoFactorMethodRequest):
    """Payload for submitting a 2FA challenge code."""

    code: str = Field(min_length=1)


class SourceImportRequest(BaseModel):
    """Payload for importing official Find My accessory JSON."""

    sources: list[object]


def register_web_routes(app: FastAPI, storage: AppStorage) -> None:  # noqa: C901
    """Register setup routes for Apple login, 2FA, and source import."""
    pending_account: AsyncAppleAccount | None = None

    async def _persist_account_state(account: AsyncAppleAccount) -> None:
        """Persist account session and derived auth state for health reporting."""
        login_state = account.login_state
        if login_state in (LoginState.AUTHENTICATED, LoginState.LOGGED_IN):
            await storage.save_apple_session(serialize_apple_account_state(account))
            await storage.set_account_state(AuthState.AUTHENTICATED)
        elif login_state == LoginState.REQUIRE_2FA:
            await storage.clear_apple_session()
            await storage.set_account_state(AuthState.NOT_CONFIGURED)
        else:
            await storage.clear_apple_session()
            await storage.set_account_state(AuthState.REAUTH_REQUIRED)

    async def _replace_pending_account(account: AsyncAppleAccount | None) -> None:
        """Replace the in-memory 2FA account and close any previous account."""
        nonlocal pending_account
        old_account = pending_account
        pending_account = account
        if old_account is not None and old_account is not account:
            await old_account.close()

    async def _clear_pending_account() -> None:
        """Close and clear the in-memory 2FA account if one exists."""
        await _replace_pending_account(None)

    def _serialize_state(state: LoginState) -> str:
        """Convert a ``LoginState`` into a user-facing string."""
        return str(state)

    def _serialize_2fa_method(method: object, index: int) -> dict[str, object]:
        """Serialize one 2FA method in a frontend-safe form."""
        if isinstance(method, AsyncSmsSecondFactor):
            return {
                "index": index,
                "type": "sms",
                "label": method.phone_number,
            }
        if isinstance(method, AsyncTrustedDeviceSecondFactor):
            return {
                "index": index,
                "type": "trusted_device",
                "label": "trusted_device",
            }
        return {
            "index": index,
            "type": type(method).__name__,
            "label": "method",
        }

    async def _get_saved_account() -> AsyncAppleAccount | None:
        """Load current account state from storage and hydrate an account object."""
        session = await storage.get_apple_session()
        if not session:
            return None
        try:
            return load_apple_account(session)
        except (TypeError, ValueError, InvalidStateError, KeyError) as error:
            await storage.clear_apple_session()
            raise HTTPException(
                status_code=409,
                detail="Stored Apple session is invalid",
            ) from error

    async def _get_pending_account() -> AsyncAppleAccount:
        """Return the in-memory account currently waiting for 2FA."""
        if pending_account is None:
            raise HTTPException(
                status_code=409,
                detail="Apple 2FA session is missing. Start with /setup/login first.",
            )
        return pending_account

    def _build_setup_page() -> str:
        """Build setup page HTML for guided Apple login and source import."""
        return """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Lost Apple Setup</title>
  <style>
    body {
      margin: 0;
      padding: 16px;
      max-width: 980px;
      font-family: Arial, sans-serif;
      line-height: 1.45;
      color: #111827;
    }

    h1, h2, h3 {
      margin: 0.4rem 0;
    }

    section {
      margin: 1rem 0;
      border: 1px solid #e5e7eb;
      border-radius: 6px;
      padding: 12px;
      background: #f8fafc;
    }

    label {
      display: block;
      margin-top: 8px;
      font-weight: bold;
    }

    input, textarea, button {
      margin-top: 4px;
      margin-bottom: 8px;
      max-width: 100%;
      box-sizing: border-box;
    }

    .status {
      white-space: pre-wrap;
      word-break: break-word;
      background: #0f172a;
      color: #e2e8f0;
      padding: 12px;
      border-radius: 6px;
      min-height: 96px;
    }

    button {
      padding: 6px 10px;
    }
  </style>
</head>
<body>
  <h1>Lost Apple App Setup</h1>
  <p>
    Use this page to link an Apple account, complete two-factor verification,
    and import official Apple Find My accessory JSON payloads.
  </p>
  <p>
    <a href="{hacs_url}" target="_blank" rel="noopener">Install through HACS</a>
  </p>

  <section>
    <h2>Setup access</h2>
    <label for="pairing-token">Pairing token</label>
    <input id="pairing-token" type="password" autocomplete="current-password" />
  </section>

  <section>
    <h2>Apple account login</h2>
    <form id="login-form">
      <label for="username">Apple username</label>
      <input id="username" name="username" type="email" required />
      <label for="password">Apple password</label>
      <input id="password" name="password" type="password" required />
      <button id="login-submit" type="submit">Login</button>
    </form>
    <h3>Current auth state</h3>
    <div id="auth-status" class="status">No auth state loaded.</div>
  </section>

  <section>
    <h2>Two-factor authentication</h2>
    <button id="refresh-2fa" type="button">Refresh available methods</button>
    <form id="request-2fa">
      <label for="request-method-index">Method index</label>
      <input
        id="request-method-index"
        name="method_index"
        type="number"
        value="0"
        min="0"
      />
      <button type="submit">Request code</button>
    </form>
    <form id="submit-2fa">
      <label for="submit-method-index">Method index</label>
      <input
        id="submit-method-index"
        name="method_index"
        type="number"
        value="0"
        min="0"
      />
      <label for="code">Code</label>
      <input id="code" name="code" type="text" autocomplete="one-time-code" />
      <button type="submit">Submit code</button>
    </form>
    <h3>Available methods</h3>
    <div id="methods" class="status">No methods loaded.</div>
  </section>

  <section>
    <h2>Find My source import</h2>
    <p>
      Official FindMy source discovery is not implemented yet.
      Upload JSON payloads copied from Find My for Home Assistant integrations.
    </p>
    <form id="source-import">
      <label for="sources">Sources JSON array</label>
      <textarea id="sources" rows="12" cols="80"></textarea>
      <button type="submit">Save sources</button>
    </form>
    <h3>Saved sources</h3>
    <div id="sources-status" class="status">No sources saved.</div>
  </section>

  <script>
    const authStatus = document.getElementById("auth-status");
    const methods = document.getElementById("methods");
    const pairingToken = document.getElementById("pairing-token");
    const sourcesStatus = document.getElementById("sources-status");

    function setupUrl(path) {{
      const basePath = window.location.pathname.endsWith("/")
        ? window.location.pathname
        : `${{window.location.pathname}}/`;
      return `${{basePath}}${{path}}`;
    }}

    function authHeaders() {{
      const token = pairingToken.value;
      if (!token) {{
        return {{"Content-Type": "application/json"}};
      }}
      return {{
        "Authorization": `Bearer ${{token}}`,
        "Content-Type": "application/json",
      }};
    }}

    async function setStatus(target, payload) {{
      target.textContent = JSON.stringify(payload, null, 2);
    }}

    async function postJson(path, body) {{
      const response = await fetch(setupUrl(path), {{
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify(body),
      }});
      if (!response.ok) {{
        const data = await response.json().catch(
          () => ({{"detail": "Request failed"}})
        );
        throw new Error(data.detail || "Request failed");
      }}
      return response.json();
    }}

    async function refreshMethods() {{
      const response = await fetch(setupUrl("2fa/methods"), {{
        headers: authHeaders(),
      }});
      const payload = await response
        .json()
        .catch(() => ({{"detail": "Request failed"}}));
      if (!response.ok) {{
        methods.textContent = JSON.stringify(payload, null, 2);
        return;
      }}
      methods.textContent = JSON.stringify(payload, null, 2);
    }}

    document.getElementById("login-form").addEventListener("submit", async (event) => {{
      event.preventDefault();
      try {{
        const username = document.getElementById("username").value;
        const password = document.getElementById("password").value;
        const payload = await postJson("login", {{username, password}});
        await setStatus(authStatus, payload);
        await refreshMethods();
      }} catch (error) {{
        await setStatus(authStatus, {{ error: error.message }});
      }}
    }});

    document.getElementById("request-2fa").addEventListener(
      "submit", async (event) => {{
      event.preventDefault();
      try {{
        const method_index = Number(
          document.getElementById("request-method-index").value
        );
        const payload = await postJson("2fa/request", {{method_index}});
        await setStatus(authStatus, payload);
      }} catch (error) {{
        await setStatus(authStatus, {{ error: error.message }});
      }}
    }});

    document.getElementById("submit-2fa").addEventListener(
      "submit", async (event) => {{
      event.preventDefault();
      try {{
        const method_index = Number(
          document.getElementById("submit-method-index").value
        );
        const code = document.getElementById("code").value;
        const payload = await postJson("2fa/submit", {{method_index, code}});
        await setStatus(authStatus, payload);
      }} catch (error) {{
        await setStatus(authStatus, {{ error: error.message }});
      }}
    }});

    document.getElementById("source-import").addEventListener(
      "submit", async (event) => {{
      event.preventDefault();
      try {{
        const sources = JSON.parse(
          document.getElementById("sources").value || "[]"
        );
        const payload = await postJson("sources", {{sources}});
        await setStatus(sourcesStatus, payload);
      }} catch (error) {{
        await setStatus(sourcesStatus, {{ error: error.message }});
      }}
    }});

    document.getElementById("refresh-2fa").addEventListener("click", refreshMethods);
  </script>
</body>
</html>
""".replace(
            "{hacs_url}",
            HACS_INSTALL_URL,
        )

    @app.get("/", include_in_schema=False)
    async def root() -> RedirectResponse:
        """Redirect the app panel root to the setup page."""
        return RedirectResponse(url="setup")

    @app.get("/setup", response_class=HTMLResponse)
    async def setup() -> str:
        """Return setup page used for account and source configuration."""
        return _build_setup_page()

    @app.post("/setup/login")
    async def login(payload: LoginRequest) -> dict[str, object]:
        """Start Apple login and persist partial auth state."""
        account = AsyncAppleAccount(LocalAnisetteProvider())
        try:
            login_state = await account.login(payload.username, payload.password)
        except (InvalidCredentialsError, UnauthorizedError) as error:
            await account.close()
            raise HTTPException(status_code=401, detail="Apple login failed") from error

        await _persist_account_state(account)
        methods: list[dict[str, object]] = []
        if login_state == LoginState.REQUIRE_2FA:
            await _replace_pending_account(account)
            methods = [
                _serialize_2fa_method(method, index)
                for index, method in enumerate(await account.get_2fa_methods())
            ]
        else:
            await _clear_pending_account()
            await account.close()

        return {
            "state": _serialize_state(login_state),
            "account_state": str(await storage.get_account_state()),
            "methods": methods,
        }

    @app.get("/setup/2fa/methods")
    async def get_methods() -> dict[str, object]:
        """List available 2FA methods using the active in-memory account state."""
        account = await _get_pending_account()

        methods = [
            _serialize_2fa_method(method, index)
            for index, method in enumerate(await account.get_2fa_methods())
        ]
        await _persist_account_state(account)

        return {
            "state": _serialize_state(account.login_state),
            "account_state": str(await storage.get_account_state()),
            "methods": methods,
        }

    @app.post("/setup/2fa/request")
    async def request_two_factor(payload: TwoFactorMethodRequest) -> dict[str, object]:
        """Request a 2FA challenge for the selected method."""
        account = await _get_pending_account()

        methods = await account.get_2fa_methods()
        if payload.method_index >= len(methods):
            raise HTTPException(status_code=400, detail="Invalid method index")

        method = methods[payload.method_index]
        await method.request()
        await _persist_account_state(account)
        return {
            "state": _serialize_state(account.login_state),
            "account_state": str(await storage.get_account_state()),
        }

    @app.post("/setup/2fa/submit")
    async def submit_two_factor(payload: TwoFactorSubmitRequest) -> dict[str, object]:
        """Submit the 2FA code and move session forward."""
        account = await _get_pending_account()

        methods = await account.get_2fa_methods()
        if payload.method_index >= len(methods):
            raise HTTPException(status_code=400, detail="Invalid method index")

        method = methods[payload.method_index]
        try:
            login_state = await method.submit(payload.code)
        except InvalidStateError as error:
            await storage.set_account_state(AuthState.REAUTH_REQUIRED)
            await _clear_pending_account()
            raise HTTPException(status_code=409, detail="2FA submit failed") from error

        if login_state in (LoginState.AUTHENTICATED, LoginState.LOGGED_IN):
            await storage.save_apple_session(serialize_apple_account_state(account))
            await storage.set_account_state(AuthState.AUTHENTICATED)
            await _clear_pending_account()
        else:
            await storage.clear_apple_session()
            await storage.set_account_state(AuthState.REAUTH_REQUIRED)
            await _clear_pending_account()

        return {
            "state": _serialize_state(login_state),
            "account_state": str(await storage.get_account_state()),
        }

    @app.on_event("shutdown")
    async def _close_pending_account() -> None:
        """Close any in-memory 2FA account during app shutdown."""
        await _clear_pending_account()

    @app.post("/setup/sources")
    async def import_sources(payload: SourceImportRequest) -> dict[str, object]:
        """Store official Find My source payloads used for polling."""
        if not payload.sources:
            raise HTTPException(
                status_code=400,
                detail="sources payload must be non-empty",
            )

        try:
            sources = build_sources_from_payloads(payload.sources)
            serialized = serialize_accessory_payloads(payload.sources)
        except (TypeError, ValueError) as error:
            raise HTTPException(
                status_code=400,
                detail="Invalid source payload",
            ) from error

        await storage.save_apple_sources(serialized)
        return {
            "source_count": len(sources),
            "sources": [{"id": source.id, "name": source.name} for source in sources],
        }
