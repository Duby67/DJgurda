#!/usr/bin/env bash
set -euo pipefail

COOKIES_ROOT="${COOKIES_ROOT:-$HOME/cookies}"
RUNTIME_DIR="${RUNTIME_DIR:-$COOKIES_ROOT/runtime}"
COMPOSE_FILE="${COMPOSE_FILE:-$RUNTIME_DIR/compose.cookies-refresh.yml}"
SOURCES_FILE="${REFRESH_SOURCES_FILE:-$RUNTIME_DIR/refresh_sources.list}"
HOST_UID="${HOST_UID:-$(id -u)}"
HOST_GID="${HOST_GID:-$(id -g)}"

if [[ ! -f "$COMPOSE_FILE" ]]; then
  echo "Missing compose file: $COMPOSE_FILE" >&2
  exit 1
fi

if [[ "$HOST_UID" -eq 0 || "$HOST_GID" -eq 0 ]]; then
  echo "Do not run as root. Use DJgurda user context." >&2
  exit 1
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
      echo "Invalid source line in $SOURCES_FILE: $line" >&2
      exit 1
    fi

    if [[ "$source_folder" == *"/"* || "$source_folder" == "." || "$source_folder" == ".." ]]; then
      echo "Invalid folder name in $SOURCES_FILE: $source_folder" >&2
      exit 1
    fi

    mkdir -p "$COOKIES_ROOT/$source_folder"
    targets+=("$source_url")
  done < "$SOURCES_FILE"
fi

if [[ -z "${REFRESH_TARGETS:-}" ]]; then
  if [[ ${#targets[@]} -eq 0 ]]; then
    echo "No refresh targets found. Provide REFRESH_TARGETS or create $SOURCES_FILE" >&2
    exit 1
  fi
  REFRESH_TARGETS="$(IFS=,; echo "${targets[*]}")"
fi

export HOST_UID HOST_GID REFRESH_TARGETS
/usr/bin/docker compose -f "$COMPOSE_FILE" run --rm cookies-session-refresher
