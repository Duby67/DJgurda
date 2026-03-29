#!/usr/bin/env bash
set -euo pipefail

EXTRACTOR_ROOT="${EXTRACTOR_ROOT:-$HOME/cookies}"
RUNTIME_DIR="${RUNTIME_DIR:-$EXTRACTOR_ROOT/runtime}"
COMPOSE_FILE="${COMPOSE_FILE:-$RUNTIME_DIR/compose.cookies.yml}"

if [[ ! -f "$COMPOSE_FILE" ]]; then
  echo "Missing compose file: $COMPOSE_FILE" >&2
  exit 1
fi

/usr/bin/docker compose -f "$COMPOSE_FILE" run --rm cookies-extractor
