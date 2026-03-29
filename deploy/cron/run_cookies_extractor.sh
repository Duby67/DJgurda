#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-$HOME/bot_prod}"
COMPOSE_FILE="$PROJECT_DIR/deploy/compose/compose.cookies.yml"

if [[ ! -f "$COMPOSE_FILE" ]]; then
  echo "Missing compose file: $COMPOSE_FILE" >&2
  exit 1
fi

/usr/bin/docker compose -f "$COMPOSE_FILE" run --rm cookies-extractor
