"""Typed configuration helpers for the Lost Apple App."""

from __future__ import annotations

from collections.abc import Mapping
import json
from os import getenv
from pathlib import Path
from typing import Final

DEFAULT_OPTIONS_PATH: Final = "/data/options.json"


def _load_options(options_path: Path) -> Mapping[str, object]:
    """Load HA options JSON from disk and return mapping-like data."""
    try:
        with options_path.open("r", encoding="utf-8") as options_file:
            loaded = json.load(options_file)
    except (OSError, json.JSONDecodeError) as error:
        options_error = f"Failed to read pairing options file: {options_path}"
        raise ValueError(options_error) from error
    if not isinstance(loaded, Mapping):
        mapping_error = TypeError("Options file must contain a JSON object")
        raise mapping_error
    return loaded


def _extract_pairing_token(options: Mapping[str, object]) -> str:
    """Extract a validated non-empty `pairing_token` value from options."""
    value = options.get("pairing_token")
    if not isinstance(value, str):
        missing_error = TypeError("Missing or invalid pairing_token option")
        raise missing_error
    token = value.strip()
    if not token:
        raise _missing_pairing_token_error()
    return token


def _missing_pairing_token_error() -> ValueError:
    """Build a canonical error for missing non-empty pairing token values."""
    return ValueError("pairing_token must be a non-empty value")


def resolve_pairing_token(environment: Mapping[str, str] | None = None) -> str:
    """Resolve pairing token from env override or HA options file."""
    if environment is None:
        environment = {
            key: value
            for key in (
                "LOST_APPLE_PAIRING_TOKEN",
                "LOST_APPLE_OPTIONS_PATH",
            )
            if (value := getenv(key)) is not None
        }

    explicit_token = environment.get("LOST_APPLE_PAIRING_TOKEN")
    if explicit_token is not None:
        token = explicit_token.strip()
        if not token:
            raise _missing_pairing_token_error()
        return token

    options_path = Path(
        environment.get("LOST_APPLE_OPTIONS_PATH", DEFAULT_OPTIONS_PATH),
    )
    options = _load_options(options_path)
    return _extract_pairing_token(options)
