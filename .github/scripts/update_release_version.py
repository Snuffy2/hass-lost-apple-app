"""Update release version references for the Lost Apple App."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path
import re

VERSION_PATTERN = re.compile(
    r"^[0-9]+([.][0-9]+)*((a|b|rc|[.]post|[.]dev)[0-9]+)?"
    r"([+][0-9A-Za-z]+([.-][0-9A-Za-z]+)*)?$"
)
CONFIG_VERSION_PATTERN = re.compile(r"^version:\s*(?P<version>[^\s#]+).*$", re.MULTILINE)
CONST_VERSION_PATTERN = re.compile(r'^VERSION: Final = "(?P<version>[^"]*)"$', re.MULTILINE)


def _validate_version(version: str) -> str:
    """Validate a release version string.

    Args:
        version: Version derived from the GitHub release tag.

    Returns:
        The validated version string.

    Raises:
        ValueError: If the version does not match the supported release format.
    """
    if VERSION_PATTERN.fullmatch(version) is None:
        raise ValueError(f"Invalid release version: {version}")
    return version


def _replace_once(path: Path, pattern: re.Pattern[str], replacement: str) -> None:
    """Replace exactly one matching line in a text file.

    Args:
        path: File to update.
        pattern: Compiled regular expression matching the full target line.
        replacement: Replacement line content.

    Raises:
        ValueError: If the target line is missing or appears more than once.
    """
    content = path.read_text(encoding="utf-8")
    updated, replacements = pattern.subn(replacement, content)
    if replacements != 1:
        raise ValueError(f"Expected exactly one version line in {path}, found {replacements}")
    path.write_text(updated, encoding="utf-8")


def _read_version_once(path: Path, pattern: re.Pattern[str]) -> str:
    """Read exactly one version value from a text file.

    Args:
        path: File to read.
        pattern: Compiled regular expression with a version group.

    Returns:
        Version read from the file.

    Raises:
        ValueError: If the version line is missing or appears more than once.
    """
    content = path.read_text(encoding="utf-8")
    matches = list(pattern.finditer(content))
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one version line in {path}, found {len(matches)}")
    return _validate_version(matches[0].group("version").strip('"'))


def update_version_files(config_path: Path, const_path: Path, version: str) -> None:
    """Update Home Assistant App config and runtime version constants.

    Args:
        config_path: Path to the Home Assistant App config YAML file.
        const_path: Path to the Python constants module.
        version: Version to write to both files.
    """
    validated_version = _validate_version(version)
    _replace_once(config_path, CONFIG_VERSION_PATTERN, f"version: {validated_version}")
    _replace_once(
        const_path,
        CONST_VERSION_PATTERN,
        f'VERSION: Final = "{validated_version}"',
    )


def assert_version_files_match(config_path: Path, const_path: Path) -> str:
    """Validate that app config and runtime constants use the same version.

    Args:
        config_path: Path to the Home Assistant App config YAML file.
        const_path: Path to the Python constants module.

    Returns:
        The shared version value.

    Raises:
        ValueError: If either version is invalid or the files do not match.
    """
    config_version = _read_version_once(config_path, CONFIG_VERSION_PATTERN)
    const_version = _read_version_once(const_path, CONST_VERSION_PATTERN)
    if config_version != const_version:
        raise ValueError(
            f"Version skew: {config_path} has {config_version}, {const_path} has {const_version}"
        )
    return config_version


def _build_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser."""
    parser = argparse.ArgumentParser(description="Update Lost Apple App release version files.")
    parser.add_argument("--version", help="Release version to write.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate that existing version files match without updating them.",
    )
    parser.add_argument(
        "--github-output",
        type=Path,
        help="Optional GITHUB_OUTPUT path for writing the checked version.",
    )
    parser.add_argument(
        "--config-path",
        type=Path,
        required=True,
        help="Path to app/lost_apple/config.yaml.",
    )
    parser.add_argument(
        "--const-path",
        type=Path,
        required=True,
        help="Path to lost_apple_app/const.py.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the version update command.

    Args:
        argv: Optional command-line arguments for tests.

    Returns:
        Process exit code.
    """
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.version is None and not args.check:
        parser.error("--version is required unless --check is used")
    try:
        if args.version is not None:
            update_version_files(
                config_path=args.config_path,
                const_path=args.const_path,
                version=args.version,
            )
        version = assert_version_files_match(
            config_path=args.config_path,
            const_path=args.const_path,
        )
    except ValueError as err:
        parser.error(str(err))
    if args.github_output is not None:
        with args.github_output.open("a", encoding="utf-8") as output_file:
            output_file.write(f"version={version}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
