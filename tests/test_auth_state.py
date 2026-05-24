"""Tests for Lost Apple App auth-state classification."""

from __future__ import annotations

from lost_apple_app.auth import AuthState, classify_auth_error
import pytest


def _assert_state(actual: object, expected: object, message: str) -> None:
    """Raise an assertion error when auth classification differs."""
    if actual is not expected:
        error_message = message + " (got=" + repr(actual) + ", expected=" + repr(expected) + ")"
        raise AssertionError(error_message)


@pytest.mark.parametrize(
    "message",
    [
        "invalid session token",
        "Unauthorized access",
        "2fa verification required",
        "Invalid Session",
        "  2FA error ",
    ],
)
def test_classify_auth_error_returns_reauth_required_for_auth_failures(
    message: str,
) -> None:
    """Auth failures should require reauthentication."""
    state = classify_auth_error(message)

    _assert_state(
        actual=state,
        expected=AuthState.REAUTH_REQUIRED,
        message="Authentication-related errors should request reauth",
    )


def test_classify_auth_error_returns_authenticated_for_other_errors() -> None:
    """Non-auth failures should not request reauthentication."""
    state = classify_auth_error("network timeout while polling")

    _assert_state(
        actual=state,
        expected=AuthState.AUTHENTICATED,
        message="Non-auth errors should stay in authenticated state",
    )
