"""Tests for Lost Apple App configuration loading."""

from __future__ import annotations

import json
import os
from pathlib import Path
import tomllib

from fastapi.testclient import TestClient
from lost_apple_app.__main__ import build_app
from lost_apple_app.config import resolve_pairing_token
from lost_apple_app.const import VERSION
import pytest

AUTHORIZATION_HEADER = "Authorization"
HTTP_STATUS_OK = 200
HTTP_STATUS_UNAUTHORIZED = 401
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _write_options_file(path: Path, token: str) -> None:
    """Persist the options payload to disk for the tested path."""
    with path.open("w", encoding="utf-8") as stream:
        json.dump({"pairing_token": token}, stream)


def _make_auth_headers(token: str) -> dict[str, str]:
    """Create an Authorization header for Bearer-token requests."""
    return {AUTHORIZATION_HEADER: f"Bearer {token}"}


def _assert_equal(actual: object, expected: object, message: str) -> None:
    """Raise assertion failures with a message format consistent with project style."""
    if actual != expected:
        equality_error = message + " (got=" + repr(actual) + ", expected=" + repr(expected) + ")"
        raise AssertionError(equality_error)


def _assert_status(response_status: int, expected_status: int) -> None:
    """Validate response status with explicit assertion style."""
    if response_status != expected_status:
        status_error = (
            "Unexpected status code: " + str(response_status) + ", expected " + str(expected_status)
        )
        raise AssertionError(status_error)


def test_resolve_pairing_token_prefers_env_override(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Explicit env token should override options-file content."""
    options_path = tmp_path / "options.json"
    _write_options_file(options_path, "ignored-token")
    monkeypatch.setenv("LOST_APPLE_OPTIONS_PATH", str(options_path))
    monkeypatch.setenv("LOST_APPLE_PAIRING_TOKEN", "env-token")

    resolved = resolve_pairing_token()
    _assert_equal(
        actual=resolved,
        expected="env-token",
        message="Env override should win over options file",
    )


def test_resolve_pairing_token_reads_options_file(tmp_path: Path) -> None:
    """Options JSON should supply the pairing token when env override is absent."""
    options_path = tmp_path / "options.json"
    _write_options_file(options_path, "options-token")
    environment = {"LOST_APPLE_OPTIONS_PATH": str(options_path)}

    resolved = resolve_pairing_token(environment)
    _assert_equal(
        actual=resolved,
        expected="options-token",
        message="Options file token should be used without env override",
    )


def test_resolve_pairing_token_rejects_blank_option(tmp_path: Path) -> None:
    """Blank pairing token values should be rejected from options."""
    options_path = tmp_path / "options.json"
    _write_options_file(options_path, "   ")
    environment = {"LOST_APPLE_OPTIONS_PATH": str(options_path)}

    with pytest.raises(ValueError, match="pairing_token must be a non-empty value"):
        resolve_pairing_token(environment)


def test_dockerfile_starts_packaged_run_script() -> None:
    """Docker image command should target the copied app run script."""
    dockerfile = REPOSITORY_ROOT / "app" / "lost_apple" / "Dockerfile"
    run_script = REPOSITORY_ROOT / "app" / "lost_apple" / "run.sh"

    dockerfile_content = dockerfile.read_text(encoding="utf-8")

    assert 'CMD ["./app/lost_apple/run.sh"]' in dockerfile_content
    assert run_script.exists()
    assert os.access(run_script, os.X_OK)


def test_app_config_uses_multi_arch_image_tag() -> None:
    """App config should point at the multi-platform GHCR image tag."""
    config_path = REPOSITORY_ROOT / "app" / "lost_apple" / "config.yaml"

    config_content = config_path.read_text(encoding="utf-8")

    assert "image: ghcr.io/snuffy2/hass-lost-apple-app\n" in config_content
    assert "hass-lost-apple-{arch}" not in config_content


def test_app_config_version_matches_runtime_version() -> None:
    """Home Assistant App config should publish the same version as the runtime."""
    config_path = REPOSITORY_ROOT / "app" / "lost_apple" / "config.yaml"

    config_content = config_path.read_text(encoding="utf-8")

    assert f"version: {VERSION}\n" in config_content


def test_release_workflow_publishes_single_multi_platform_image() -> None:
    """Release workflow should publish one image name with a multi-platform manifest."""
    workflow_path = REPOSITORY_ROOT / ".github" / "workflows" / "release.yml"

    workflow_content = workflow_path.read_text(encoding="utf-8")

    assert "${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}-${{ matrix.arch }}" not in workflow_content
    assert "platforms: linux/amd64,linux/arm64" in workflow_content


def test_release_workflow_uses_event_specific_image_tags() -> None:
    """Release workflow should tag images by the triggering event type."""
    workflow_path = REPOSITORY_ROOT / ".github" / "workflows" / "release.yml"

    workflow_content = workflow_path.read_text(encoding="utf-8")

    assert "type=edge,branch=main,enable=${{ github.event_name == 'push' }}" in workflow_content
    assert (
        "type=semver,pattern={{version}},value=${{ github.event.release.tag_name }},"
        "enable=${{ github.event_name == 'release' }}"
    ) in workflow_content
    assert (
        "type=raw,value=latest,"
        "enable=${{ github.event_name == 'release' && !github.event.release.prerelease }}"
    ) in workflow_content
    assert (
        "type=raw,value=${{ inputs.tag_name }},"
        "enable=${{ github.event_name == 'workflow_dispatch' }}"
    ) in workflow_content
    assert "type=semver,pattern={{version}},value=${{ env.RELEASE_TAG }}" not in workflow_content
    assert (
        "type=raw,value=latest,"
        "enable=${{ github.event_name == 'workflow_dispatch'" not in workflow_content
    )
    assert "description: Image tag only; does not update app version" in workflow_content


def test_config_tests_do_not_pin_current_release_version() -> None:
    """Config tests should keep working after release automation bumps VERSION."""
    test_path = REPOSITORY_ROOT / "tests" / "test_config.py"

    test_content = test_path.read_text(encoding="utf-8")
    pinned_version_assertion = "assert " + "VERSION == " + '"'

    assert pinned_version_assertion not in test_content


def test_project_version_uses_lost_apple_app_constant() -> None:
    """Package metadata should resolve from the runtime version constant."""
    pyproject_path = REPOSITORY_ROOT / "pyproject.toml"

    pyproject = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))

    assert pyproject["project"]["dynamic"] == ["version"]
    assert "version" not in pyproject["project"]
    assert pyproject["tool"]["setuptools"]["dynamic"]["version"] == {
        "attr": "lost_apple_app.const.VERSION"
    }


def test_release_workflow_updates_runtime_and_app_config_versions() -> None:
    """Release workflow should rewrite both runtime and Home Assistant App versions."""
    workflow_path = REPOSITORY_ROOT / ".github" / "workflows" / "release.yml"

    workflow_content = workflow_path.read_text(encoding="utf-8")

    assert "types: [published]" in workflow_content
    assert "if: ${{ github.event_name == 'release' }}" in workflow_content
    assert 'APP_VERSION="${RELEASE_TAG#v}"' in workflow_content
    assert "grep -Eq" in workflow_content
    assert 'printf "%s\\n" "${APP_VERSION}"' in workflow_content
    assert "Invalid release version" in workflow_content
    assert 's/^VERSION: Final = \\".*\\"/VERSION: Final = \\"${APP_VERSION}\\"/' in workflow_content
    assert "app/src/lost_apple_app/const.py" in workflow_content
    assert "s/^version: .*/version: ${APP_VERSION}/" in workflow_content
    assert "app/lost_apple/config.yaml" in workflow_content
    assert "git push origin HEAD:${{ github.event.repository.default_branch }}" in workflow_content
    assert "DEFAULT_APP_VERSION" not in workflow_content


def test_build_app_uses_options_json_for_authentication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """build_app() should use options-configured token for API auth."""
    options_path = tmp_path / "options.json"
    _write_options_file(options_path, "auth-token")
    monkeypatch.setenv("LOST_APPLE_OPTIONS_PATH", str(options_path))
    monkeypatch.setenv("LOST_APPLE_DB", str(tmp_path / "lost_apple.sqlite3"))

    app = build_app()
    with TestClient(app) as client:
        unauthorized = client.get("/api/v1/health")
        _assert_status(unauthorized.status_code, HTTP_STATUS_UNAUTHORIZED)

        wrong_token = client.get(
            "/api/v1/health",
            headers=_make_auth_headers("invalid"),
        )
        _assert_status(wrong_token.status_code, HTTP_STATUS_UNAUTHORIZED)

        valid = client.get(
            "/api/v1/health",
            headers=_make_auth_headers("auth-token"),
        )
        _assert_status(valid.status_code, HTTP_STATUS_OK)
