#!/usr/bin/env bash
# Run Docker Compose for the local bot with development limits; the database lives in .data/.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p .data
export DJGURDA_IMAGE=djgurda:local LOCAL_USER="$(id -u):$(id -g)"
exec docker compose --env-file .env -f deploy/compose.yaml \
  -f deploy/compose.development.yaml -f deploy/compose.local.yaml "$@"
