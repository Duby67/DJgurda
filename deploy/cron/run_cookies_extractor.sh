#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-$HOME/bot_prod}"
COMPOSE_FILE="$PROJECT_DIR/deploy/compose/compose.cookies.yml"
ENV_FILE="$PROJECT_DIR/deploy/compose/.env.cookies"

if [[ ! -f "$COMPOSE_FILE" ]]; then
  echo "Missing compose file: $COMPOSE_FILE" >&2
  exit 1
fi

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing env file: $ENV_FILE" >&2
  exit 1
fi

/usr/bin/docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" run --rm cookies-extractor
