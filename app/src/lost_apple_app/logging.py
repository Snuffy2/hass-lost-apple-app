"""Logging redaction helpers for the Lost Apple App."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
import logging
import re
from typing import Final, cast
from urllib.parse import unquote_plus

import uvicorn

REDACTED_VALUE: Final = "<redacted>"
LOG_DATE_FORMAT: Final = "%Y-%m-%d %H:%M:%S"
SENSITIVE_QUERY_KEYS: Final = frozenset(
    {
        "access_token",
        "apple_id",
        "authorization",
        "code",
        "cookie",
        "pairing_token",
        "password",
        "refresh_token",
        "session",
        "session_cookie",
        "session_token",
        "token",
    },
)
_QUERY_PARAM_PATTERN: Final = re.compile(
    r"(?P<prefix>[?&])(?P<key>[^=\s&\"']+)=(?P<value>[^&\s\"']*)"
)
type LogArgs = tuple[object, ...] | Mapping[str, object] | None


def redact_sensitive_log_output(log_output: str) -> str:
    """Return log output with credential-like query parameter values redacted.

    Args:
        log_output: Log message text before it is emitted.

    Returns:
        Log message text with sensitive query parameter values replaced.
    """

    def _redact_match(match: re.Match[str]) -> str:
        """Redact sensitive query parameter matches."""
        key = match.group("key")
        decoded_key = unquote_plus(key).lower()
        if decoded_key not in SENSITIVE_QUERY_KEYS:
            return match.group(0)
        return f"{match.group('prefix')}{key}={REDACTED_VALUE}"

    return _QUERY_PARAM_PATTERN.sub(_redact_match, log_output)


def _redact_log_argument(argument: object) -> object:
    """Return a logging argument with any sensitive text redacted.

    Args:
        argument: Positional or mapping logging argument.

    Returns:
        A redacted argument preserving common logging argument containers.
    """
    if isinstance(argument, str):
        return redact_sensitive_log_output(argument)
    if isinstance(argument, tuple):
        return tuple(_redact_log_argument(item) for item in argument)
    if isinstance(argument, list):
        return [_redact_log_argument(item) for item in argument]
    if isinstance(argument, Mapping):
        return {key: _redact_log_argument(value) for key, value in argument.items()}
    return argument


class SensitiveDataFilter(logging.Filter):
    """Logging filter that redacts credential-like values before emission."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Redact sensitive message and argument values from a log record.

        Args:
            record: Log record about to be emitted.

        Returns:
            Always true so the record remains loggable after redaction.
        """
        if isinstance(record.msg, str):
            record.msg = redact_sensitive_log_output(record.msg)
        record.args = cast("LogArgs", _redact_log_argument(record.args))
        return True


def build_redacting_uvicorn_log_config() -> dict[str, object]:
    """Build uvicorn logging config with Lost Apple redaction filters attached.

    Returns:
        A uvicorn logging configuration dictionary.
    """
    log_config = deepcopy(uvicorn.config.LOGGING_CONFIG)
    formatters = log_config.get("formatters")
    if isinstance(formatters, dict):
        for formatter in formatters.values():
            if isinstance(formatter, dict):
                formatter["datefmt"] = LOG_DATE_FORMAT
                log_format = formatter.get("fmt")
                if isinstance(log_format, str) and "%(asctime)s" not in log_format:
                    formatter["fmt"] = f"%(asctime)s {log_format}"

    filters = log_config.setdefault("filters", {})
    if isinstance(filters, dict):
        filters["lost_apple_sensitive_data"] = {
            "()": "lost_apple_app.logging.SensitiveDataFilter",
        }

    handlers = log_config.get("handlers")
    if isinstance(handlers, dict):
        for handler in handlers.values():
            if isinstance(handler, dict):
                configured_filters = handler.setdefault("filters", [])
                if isinstance(configured_filters, list):
                    configured_filters.append("lost_apple_sensitive_data")

    return log_config
