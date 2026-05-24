"""Tests for Lost Apple logging safeguards."""

from __future__ import annotations

import logging

from lost_apple_app.logging import (
    SensitiveDataFilter,
    build_redacting_uvicorn_log_config,
    redact_sensitive_log_output,
)


def test_redact_sensitive_log_output_scrubs_sensitive_query_values() -> None:
    """Credential-like query parameters should not be emitted in access logs."""
    log_line = (
        '172.30.32.2:39348 - "GET '
        "/setup?username=user@example.com&password=apple-secret"
        "&pairing_token=local-secret&token=session-secret&apple_id=icloud-user"
        '&session=raw-session HTTP/1.1" 200 OK'
    )

    redacted = redact_sensitive_log_output(log_line)

    assert "apple-secret" not in redacted
    assert "local-secret" not in redacted
    assert "session-secret" not in redacted
    assert "icloud-user" not in redacted
    assert "raw-session" not in redacted
    assert "username=user@example.com" in redacted
    assert "password=<redacted>" in redacted
    assert "pairing_token=<redacted>" in redacted
    assert "token=<redacted>" in redacted
    assert "apple_id=<redacted>" in redacted
    assert "session=<redacted>" in redacted


def test_sensitive_data_filter_redacts_uvicorn_access_log_arguments() -> None:
    """The logging filter should redact uvicorn access log request-target args."""
    record = logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname="uvicorn",
        lineno=1,
        msg='%s - "%s %s HTTP/%s" %d',
        args=(
            "172.30.32.2:39348",
            "GET",
            "/setup?username=user@example.com&password=apple-secret",
            "1.1",
            200,
        ),
        exc_info=None,
        func=None,
        sinfo=None,
    )

    assert SensitiveDataFilter().filter(record)

    assert "apple-secret" not in record.getMessage()
    assert "username=user@example.com" in record.getMessage()
    assert "password=<redacted>" in record.getMessage()


def test_build_redacting_uvicorn_log_config_adds_filter_to_handlers() -> None:
    """Uvicorn log config should attach the redaction filter to all handlers."""
    log_config = build_redacting_uvicorn_log_config()

    filters = log_config["filters"]
    handlers = log_config["handlers"]

    assert isinstance(filters, dict)
    assert filters["lost_apple_sensitive_data"] == {
        "()": "lost_apple_app.logging.SensitiveDataFilter",
    }
    assert isinstance(handlers, dict)
    for handler in handlers.values():
        assert isinstance(handler, dict)
        assert "lost_apple_sensitive_data" in handler["filters"]


def test_build_redacting_uvicorn_log_config_uses_second_precision_timestamps() -> None:
    """Uvicorn log config should emit timestamps as yyyy-mm-dd hh:mm:ss."""
    log_config = build_redacting_uvicorn_log_config()

    formatters = log_config["formatters"]

    assert isinstance(formatters, dict)
    for formatter in formatters.values():
        assert isinstance(formatter, dict)
        assert formatter["datefmt"] == "%Y-%m-%d %H:%M:%S"
        assert "%(asctime)s" in formatter["fmt"]
