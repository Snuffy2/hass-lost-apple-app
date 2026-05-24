"""Authentication status primitives for Lost Apple App API consumers."""

from __future__ import annotations

from enum import StrEnum


class AuthState(StrEnum):
    """State of the cached Apple auth session."""

    NOT_CONFIGURED = "not_configured"
    AUTHENTICATED = "authenticated"
    REAUTH_REQUIRED = "reauth_required"


def classify_auth_error(message: str) -> AuthState:
    """Classify an authentication error message into an auth-state hint.

    Args:
        message: Error detail text from Apple or app communication.

    Returns:
        ``AuthState.REAUTH_REQUIRED`` for known auth failure signals,
        otherwise ``AuthState.AUTHENTICATED``.

    """
    lowered_message = message.casefold().strip()
    if (
        "invalid session" in lowered_message
        or "unauthorized" in lowered_message
        or "2fa" in lowered_message
    ):
        return AuthState.REAUTH_REQUIRED
    return AuthState.AUTHENTICATED
