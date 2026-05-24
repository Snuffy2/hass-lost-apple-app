"""SQLite persistence for Lost Apple App state."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import aiosqlite

from lost_apple_app.auth import AuthState
from lost_apple_app.models import DeviceSnapshot

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

if TYPE_CHECKING:
    from pathlib import Path

CREATE_SNAPSHOTS_TABLE_SQL = (
    "CREATE TABLE IF NOT EXISTS snapshots (id TEXT PRIMARY KEY, payload TEXT NOT NULL)"
)
CREATE_SETTINGS_TABLE_SQL = (
    "CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
)
UPSERT_SNAPSHOT_SQL = "INSERT OR REPLACE INTO snapshots (id, payload) VALUES (?, ?)"
UPSERT_SETTINGS_SQL = "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)"
SET_POLLING_INTERVAL_SQL = (
    "INSERT OR REPLACE INTO settings (key, value) VALUES ('polling_interval_minutes', ?)"
)
SELECT_POLLING_INTERVAL_SQL = "SELECT value FROM settings WHERE key = 'polling_interval_minutes'"
SELECT_SETTINGS_SQL = "SELECT value FROM settings WHERE key = ?"
POLLING_INTERVAL_MIN_MINUTES = 5
POLLING_INTERVAL_MAX_MINUTES = 60
POLLING_INTERVAL_DEFAULT_MINUTES = 15
APPLE_SESSION_SETTING_KEY = "apple_session_json"
APPLE_SOURCES_SETTING_KEY = "apple_sources_json"
ACCOUNT_STATE_SETTING_KEY = "apple_account_state"


class AppStorage:
    """Persist App settings and normalized device snapshots."""

    def __init__(self, database_path: Path) -> None:
        """Initialize storage for the given SQLite database path."""
        self._database_path = database_path

    async def initialize(self) -> None:
        """Create required tables if they do not already exist."""
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self._database_path) as db:
            await db.execute(CREATE_SETTINGS_TABLE_SQL)
            await db.execute(CREATE_SNAPSHOTS_TABLE_SQL)
            await db.commit()

    async def upsert_snapshot(self, snapshot: DeviceSnapshot) -> None:
        """Insert or replace a device snapshot."""
        async with aiosqlite.connect(self._database_path) as db:
            await db.execute(
                UPSERT_SNAPSHOT_SQL,
                (snapshot.id, snapshot.model_dump_json()),
            )
            await db.commit()

    async def set_account_state(self, state: AuthState) -> None:
        """Persist account auth state used by the API health endpoint."""
        await self._set_setting(ACCOUNT_STATE_SETTING_KEY, state.value)

    async def get_account_state(self) -> AuthState:
        """Return persisted account auth state, defaulting to not configured."""
        value = await self._get_setting(ACCOUNT_STATE_SETTING_KEY)
        if not value:
            return AuthState.NOT_CONFIGURED
        return AuthState(value)

    async def save_apple_session(self, state: Mapping[str, object]) -> None:
        """Persist an Apple account session payload for restart recovery."""
        await self._set_setting(APPLE_SESSION_SETTING_KEY, json.dumps(state))

    async def get_apple_session(self) -> Mapping[str, object] | None:
        """Load the persisted Apple session state, if available."""
        value = await self._get_setting(APPLE_SESSION_SETTING_KEY)
        if not value:
            return None
        loaded = json.loads(value)
        if not isinstance(loaded, dict):
            return None
        return loaded

    async def clear_apple_session(self) -> None:
        """Remove a persisted Apple account session payload."""
        await self._delete_setting(APPLE_SESSION_SETTING_KEY)

    async def save_apple_sources(self, sources: Sequence[object]) -> None:
        """Persist configured Find My source payloads for polling restarts."""
        await self._set_setting(APPLE_SOURCES_SETTING_KEY, json.dumps(list(sources)))

    async def get_apple_sources(self) -> list[object] | None:
        """Load configured Find My sources from storage."""
        value = await self._get_setting(APPLE_SOURCES_SETTING_KEY)
        if not value:
            return None
        loaded = json.loads(value)
        if not isinstance(loaded, list):
            return None
        return loaded

    async def clear_apple_sources(self) -> None:
        """Clear persisted Find My source payloads."""
        await self._delete_setting(APPLE_SOURCES_SETTING_KEY)

    async def list_snapshots(self) -> list[DeviceSnapshot]:
        """Return all known device snapshots sorted by display name."""
        async with aiosqlite.connect(self._database_path) as db:
            rows = await db.execute_fetchall("SELECT payload FROM snapshots")
        snapshots = [DeviceSnapshot.model_validate_json(row[0]) for row in rows]
        return sorted(snapshots, key=lambda item: item.name.casefold())

    async def set_polling_interval_minutes(self, value: int) -> None:
        """Persist polling interval in minutes."""
        if not (POLLING_INTERVAL_MIN_MINUTES <= value <= POLLING_INTERVAL_MAX_MINUTES):
            msg = (
                "Polling interval must be between "
                f"{POLLING_INTERVAL_MIN_MINUTES} and "
                f"{POLLING_INTERVAL_MAX_MINUTES} minutes"
            )
            raise ValueError(msg)
        async with aiosqlite.connect(self._database_path) as db:
            await db.execute(
                SET_POLLING_INTERVAL_SQL,
                (json.dumps(value),),
            )
            await db.commit()

    async def get_polling_interval_minutes(self) -> int:
        """Return polling interval in minutes, defaulting to 15."""
        async with aiosqlite.connect(self._database_path) as db:
            cursor = await db.execute(SELECT_POLLING_INTERVAL_SQL)
            row = await cursor.fetchone()
        if row is None:
            return POLLING_INTERVAL_DEFAULT_MINUTES
        return int(json.loads(row[0]))

    async def _set_setting(self, key: str, value: str) -> None:
        """Persist a string setting value."""
        async with aiosqlite.connect(self._database_path) as db:
            await db.execute(UPSERT_SETTINGS_SQL, (key, value))
            await db.commit()

    async def _get_setting(self, key: str) -> str | None:
        """Load a string setting value by key."""
        async with aiosqlite.connect(self._database_path) as db:
            cursor = await db.execute(SELECT_SETTINGS_SQL, (key,))
            row = await cursor.fetchone()
        if row is None:
            return None
        return str(row[0])

    async def _delete_setting(self, key: str) -> None:
        """Delete a setting key if present."""
        async with aiosqlite.connect(self._database_path) as db:
            await db.execute("DELETE FROM settings WHERE key = ?", (key,))
            await db.commit()
