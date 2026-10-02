#!/usr/bin/env bash
# Run functional checks locally; the database lives in .data/.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p .data
export DJGURDA_IMAGE=djgurda:local LOCAL_USER="$(id -u):$(id -g)"
exec docker compose --env-file .env -f deploy/bot/compose.yaml \
  -f deploy/bot/compose.development.yaml -f deploy/bot/compose.local.yaml "$@"
