#!/usr/bin/env bash
# Runs on the server under the caller's shared deployment lock.
set -Eeuo pipefail
umask 077
stage=$1
environment=$2
case "$environment" in development|production) ;; *) echo 'Invalid environment' >&2; exit 1 ;; esac

export DOCKER_CONFIG="$PWD/$stage/docker-config"
mkdir -p "$DOCKER_CONFIG"
docker login ghcr.io --username "$(cat "$stage/registry-user")" \
  --password-stdin < "$stage/registry-token" > /dev/null
compose=(docker compose --env-file "$stage/runtime.env" \
  -f "$stage/compose.yaml" -f "$stage/compose.environment.yaml")
"${compose[@]}" config --quiet
"${compose[@]}" pull --quiet bot

mkdir -p "$environment/releases"
chmod 700 "$environment" "$environment/releases"
current=
if [[ -L "$environment/current" ]]; then
  current=$(readlink "$environment/current")
  if [[ ! "$current" =~ ^releases/release\.[A-Za-z0-9]+$ ]] || [[ ! -d "$environment/$current" ]]; then
    echo 'Invalid current release; repair it before deploying.' >&2
    exit 1
  fi
elif [[ -e "$environment/current" ]]; then
  echo 'current must be a managed release symlink.' >&2
  exit 1
fi
candidate=$(mktemp -d "$environment/releases/release.XXXXXXXX")
activated=0
select_compose() {
  compose=(docker compose --env-file "$1/runtime.env" \
    -f "$1/compose.yaml" -f "$1/compose.environment.yaml")
}
finish() {
  status=$?
  trap - EXIT INT TERM
  if ((status != 0)); then
    set +e
    if ((activated)); then
      if [[ -n "$current" ]]; then
        select_compose "$environment/$current"
        if "${compose[@]}" up -d --no-build --pull never --force-recreate --wait --wait-timeout 180 bot; then
          echo 'Deployment failed; restored the last successful release.' >&2
        else
          echo 'Deployment and recovery failed; inspect server logs privately.' >&2
        fi
      else
        select_compose "$candidate"
        "${compose[@]}" stop bot
        echo 'Deployment failed; no successful release exists, candidate stopped.' >&2
      fi
    fi
    rm -rf -- "$candidate"
  fi
  exit "$status"
}
trap finish EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
cp "$stage/runtime.env" "$stage/compose.yaml" "$stage/compose.environment.yaml" "$candidate/"
chmod 600 "$candidate/"*
select_compose "$candidate"
activated=1
"${compose[@]}" up -d --no-build --pull never --force-recreate --wait --wait-timeout 180 bot
container=$("${compose[@]}" ps -q bot)
if [[ -z "$container" ]]; then
  echo 'Deployment failed: bot container is missing.' >&2
  exit 1
fi
expected_image=$(sed -n 's/^DJGURDA_IMAGE=//p' "$candidate/runtime.env")
for ((attempt=0; attempt<6; attempt++)); do
  sleep 5
  state=$(docker inspect --format '{{.State.Running}} {{.RestartCount}} {{.State.OOMKilled}} {{if .State.Health}}{{.State.Health.Status}}{{else}}missing{{end}}' "$container")
  actual_image=$(docker inspect --format '{{.Config.Image}}' "$container")
  if [[ "$state" != 'true 0 false healthy' || "$actual_image" != "$expected_image" ]]; then
    echo 'Deployment failed: bot is not ready, restarted, or has the wrong image; inspect server logs privately.' >&2
    exit 1
  fi
done

# Promote only a proven candidate. A failed retry never overwrites these pointers.
if [[ -n "$current" ]]; then
  ln -sfn "$current" "$environment/.previous.next"
  mv -Tf "$environment/.previous.next" "$environment/previous"
fi
release="releases/$(basename "$candidate")"
ln -sfn "$release" "$environment/.current.next"
mv -Tf "$environment/.current.next" "$environment/current"
trap - EXIT INT TERM

# Bound retained configuration to the current and previous successful releases.
for directory in "$environment"/releases/release.*; do
  if [[ "$directory" != "$candidate" && "$directory" != "$environment/$current" ]]; then
    rm -rf -- "$directory"
  fi
done
printf 'Deployment to %s completed; initialized bot stayed healthy for 30 seconds.\n' "$environment"
