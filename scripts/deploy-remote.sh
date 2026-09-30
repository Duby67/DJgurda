#!/usr/bin/env bash
# Runs on the server under a lock shared by both environments.
set -euo pipefail
umask 077
stage=$1
environment=$2
case "$environment" in development|production) ;; *) echo 'Invalid environment' >&2; exit 1 ;; esac

# Registry credentials live only in the staging directory, removed by the caller.
export DOCKER_CONFIG="$PWD/$stage/docker-config"
mkdir -p "$DOCKER_CONFIG"
docker login ghcr.io --username "$(cat "$stage/registry-user")" \
  --password-stdin < "$stage/registry-token" > /dev/null
compose=(docker compose --env-file "$stage/runtime.env" \
  -f "$stage/compose.yaml" -f "$stage/compose.environment.yaml")
"${compose[@]}" config --quiet
"${compose[@]}" pull --quiet bot

mkdir -p "$environment"
chmod 700 "$environment"
# Keep the previous deployment configuration for a manual rollback.
if [[ -f "$environment/runtime.env" ]]; then
  mkdir -p "$environment/previous"
  cp "$environment/runtime.env" "$environment/compose.yaml" \
    "$environment/compose.environment.yaml" "$environment/previous/"
fi
cp "$stage/runtime.env" "$stage/compose.yaml" "$stage/compose.environment.yaml" "$environment/"
chmod 600 "$environment/runtime.env"
compose=(docker compose --env-file "$environment/runtime.env" \
  -f "$environment/compose.yaml" -f "$environment/compose.environment.yaml")
"${compose[@]}" up -d --no-build --pull never --wait --wait-timeout 60 bot
container=$("${compose[@]}" ps -q bot)
if [[ -z "$container" ]]; then
  echo 'Deployment failed: bot container is missing' >&2
  exit 1
fi
# No healthcheck is claimed: observe the process and detect early crashes/restarts.
for ((attempt=0; attempt<6; attempt++)); do
  sleep 5
  state=$(docker inspect --format '{{.State.Running}} {{.RestartCount}} {{.State.OOMKilled}}' "$container")
  if [[ "$state" != 'true 0 false' ]]; then
    echo 'Deployment failed: bot exited, restarted or was OOM-killed; inspect server logs privately.' >&2
    exit 1
  fi
done
printf 'Deployment to %s completed; process stayed running for 30 seconds.\n' "$environment"
