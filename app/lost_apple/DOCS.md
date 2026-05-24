# Lost Apple App Documentation

## Environment Variables

- `LOST_APPLE_DB` (default `/data/lost_apple.sqlite3`)
- `LOST_APPLE_PAIRING_TOKEN` (required by `build_app()`)
- `LOST_APPLE_OPTIONS_PATH` (default `/data/options.json` when the env override is not set)
- `LOST_APPLE_APP_VERSION` (default `0.1.0`)

The Lost Apple App resolves `pairing_token` from `LOST_APPLE_PAIRING_TOKEN` first and then falls back to the Home Assistant App options file. In a normal Home Assistant App install, that options file lives at `/data/options.json`.

## Setup

1. Install the Lost Apple App package in Home Assistant OS.
2. Open the Lost Apple App options and set a non-empty `pairing_token`.
3. Start the Lost Apple App and open `GET /setup` for guided Apple setup and source import.
4. Install the companion Lost Apple Integration from HACS.
5. Add the Lost Apple Integration in Home Assistant, then enter the Lost Apple App URL and the same pairing token.
6. Configure Find My sources that the Lost Apple App should poll.
   The current implementation expects source payload JSON exported from official Find My tooling to be uploaded to `/setup/sources`.
   Automatic source discovery from the Apple account session is not implemented in this scope.

## Routes

- `GET /setup`
  - Shows an installation/setup page and a link to install the companion Lost Apple Integration in HACS.

- `GET /api/v1/health`
  - Returns runtime health and snapshot metadata.

- `GET /api/v1/devices`
  - Returns discovered snapshots.

## Startup

The Lost Apple App uses a factory-based uvicorn entrypoint that loads storage, initializes schema, and starts on `0.0.0.0:8099`.
