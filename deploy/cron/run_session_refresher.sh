#!/usr/bin/env bash
set -euo pipefail

EXTRACTOR_ROOT="${EXTRACTOR_ROOT:-$HOME/cookies}"
RUNTIME_DIR="${RUNTIME_DIR:-$EXTRACTOR_ROOT/runtime}"
COMPOSE_FILE="${COMPOSE_FILE:-$RUNTIME_DIR/compose.cookies-refresh.yml}"
HOST_UID="${HOST_UID:-$(id -u)}"
HOST_GID="${HOST_GID:-$(id -g)}"

if [[ ! -f "$COMPOSE_FILE" ]]; then
  echo "Missing compose file: $COMPOSE_FILE" >&2
  exit 1
fi

export HOST_UID HOST_GID
/usr/bin/docker compose -f "$COMPOSE_FILE" run --rm cookies-session-refresher
