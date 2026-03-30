#!/usr/bin/env bash
set -euo pipefail

COOKIES_ROOT="${COOKIES_ROOT:-$HOME/cookies}"
RUNTIME_DIR="${RUNTIME_DIR:-$COOKIES_ROOT/runtime}"
COMPOSE_FILE="${COMPOSE_FILE:-$RUNTIME_DIR/compose.cookies-refresh.yml}"
SOURCES_FILE="${REFRESH_SOURCES_FILE:-$RUNTIME_DIR/refresh_sources.list}"
LOG_ROOT="${LOG_ROOT:-$HOME/logs/cookies}"
RUN_ID="${RUN_ID:-$(date '+%Y%m%d_%H%M%S')}"
RUN_LOG_FILE="${RUN_LOG_FILE:-$LOG_ROOT/session_refresher_${RUN_ID}.log}"
LATEST_LOG_FILE="${LATEST_LOG_FILE:-$LOG_ROOT/session_refresher.latest.log}"
HOST_UID="${HOST_UID:-$(id -u)}"
HOST_GID="${HOST_GID:-$(id -g)}"

timestamp() {
  date '+%Y-%m-%d %H:%M:%S'
}

log() {
  printf '[%s] [host] %s\n' "$(timestamp)" "$*"
}

die() {
  log "ERROR: $*"
  exit 1
}

if ! mkdir -p "$LOG_ROOT"; then
  echo "Failed to create log directory: $LOG_ROOT" >&2
  exit 1
fi

if ! touch "$RUN_LOG_FILE"; then
  echo "Failed to create log file: $RUN_LOG_FILE" >&2
  exit 1
fi

ln -sfn "$(basename "$RUN_LOG_FILE")" "$LATEST_LOG_FILE" 2>/dev/null || true
exec > >(tee -a "$RUN_LOG_FILE") 2>&1

log "Starting run_session_refresher"
log "run_log_file=$RUN_LOG_FILE"
log "compose_file=$COMPOSE_FILE"
log "sources_file=$SOURCES_FILE"

if [[ ! -f "$COMPOSE_FILE" ]]; then
  die "Missing compose file: $COMPOSE_FILE"
fi

if [[ "$HOST_UID" -eq 0 || "$HOST_GID" -eq 0 ]]; then
  die "Do not run as root. Use DJgurda user context."
fi

trim() {
  local value="$1"
  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"
  printf '%s' "$value"
}

targets=()
if [[ -f "$SOURCES_FILE" ]]; then
  while IFS= read -r raw || [[ -n "$raw" ]]; do
    line="${raw%$'\r'}"
    [[ -z "$line" || "${line:0:1}" == "#" ]] && continue

    IFS='|' read -r source_key source_url source_folder <<< "$line"
    source_key="$(trim "${source_key:-}")"
    source_url="$(trim "${source_url:-}")"
    source_folder="$(trim "${source_folder:-}")"

    if [[ -z "$source_key" || -z "$source_url" || -z "$source_folder" ]]; then
      die "Invalid source line in $SOURCES_FILE: $line"
    fi

    if [[ "$source_folder" == *"/"* || "$source_folder" == "." || "$source_folder" == ".." ]]; then
      die "Invalid folder name in $SOURCES_FILE: $source_folder"
    fi

    target_dir="$COOKIES_ROOT/$source_folder"
    if ! mkdir -p "$target_dir"; then
      die "Failed to create target directory: $target_dir"
    fi

    log "source=$source_key url=$source_url folder=$target_dir"
    targets+=("$source_url")
  done < "$SOURCES_FILE"
else
  log "sources file not found, using REFRESH_TARGETS from environment"
fi

if [[ -z "${REFRESH_TARGETS:-}" ]]; then
  if [[ ${#targets[@]} -eq 0 ]]; then
    die "No refresh targets found. Provide REFRESH_TARGETS or create $SOURCES_FILE"
  fi
  REFRESH_TARGETS="$(IFS=,; echo "${targets[*]}")"
fi

log "resolved_targets=$REFRESH_TARGETS"
log "running docker compose refresher"

export HOST_UID HOST_GID REFRESH_TARGETS
set +e
/usr/bin/docker compose -f "$COMPOSE_FILE" run --rm cookies-session-refresher
compose_status=$?
set -e

if [[ $compose_status -ne 0 ]]; then
  die "docker compose run failed with exit code $compose_status"
fi

log "session refresher run finished successfully"
