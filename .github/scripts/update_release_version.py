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
CONFIG_VERSION_PATTERN = re.compile(r"^version: .*$", re.MULTILINE)
CONST_VERSION_PATTERN = re.compile(r'^VERSION: Final = ".*"$', re.MULTILINE)


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


def _build_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser."""
    parser = argparse.ArgumentParser(description="Update Lost Apple App release version files.")
    parser.add_argument("--version", required=True, help="Release version to write.")
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
    try:
        update_version_files(
            config_path=args.config_path,
            const_path=args.const_path,
            version=args.version,
        )
    except ValueError as err:
        parser.error(str(err))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
