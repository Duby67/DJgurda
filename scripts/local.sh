#!/usr/bin/env bash
# Run functional checks locally; the database lives in .data/.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p .data/bot-api
export DJGURDA_IMAGE=djgurda:local BOT_API_IMAGE=djgurda-bot-api:local LOCAL_USER="$(id -u):$(id -g)"
exec docker compose --env-file .env -f deploy/compose.yaml \
  -f deploy/compose.production.yaml -f deploy/compose.local.yaml "$@"
