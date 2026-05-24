#!/usr/bin/env sh
set -eu

: "${LOST_APPLE_DB:=/data/lost_apple.sqlite3}"
export LOST_APPLE_DB

python3 -m lost_apple_app
