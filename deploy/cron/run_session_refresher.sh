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
SELENIUM_PROFILE_DIR="${SELENIUM_PROFILE_DIR:-$HOME/firefox_selenium_profile}"
PREPARE_PROFILE_SCRIPT="${PREPARE_PROFILE_SCRIPT:-$RUNTIME_DIR/prepare_firefox_profile.sh}"
PROFILE_BACKUP_FILE="${PROFILE_BACKUP_FILE:-$RUNTIME_DIR/firefox_profile.backup.tar.gz}"
PROFILE_BACKUP_TMP="${PROFILE_BACKUP_TMP:-${PROFILE_BACKUP_FILE}.tmp}"

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

backup_profile() {
  if [[ ! -d "$SELENIUM_PROFILE_DIR" ]]; then
    die "Firefox Selenium profile directory does not exist: $SELENIUM_PROFILE_DIR"
  fi

  if ! mkdir -p "$(dirname "$PROFILE_BACKUP_FILE")"; then
    die "Failed to create backup directory for: $PROFILE_BACKUP_FILE"
  fi

  log "profile_backup_start profile_dir=$SELENIUM_PROFILE_DIR backup_file=$PROFILE_BACKUP_FILE"
  rm -f "$PROFILE_BACKUP_TMP"

  if ! tar -C "$SELENIUM_PROFILE_DIR" \
    --exclude='.parentlock' \
    --exclude='.startup-incomplete' \
    --exclude='lock' \
    --exclude='*.sqlite-shm' \
    --exclude='*.sqlite-wal' \
    -czf "$PROFILE_BACKUP_TMP" .; then
    rm -f "$PROFILE_BACKUP_TMP"
    die "Failed to create firefox selenium profile backup"
  fi

  if ! mv -f "$PROFILE_BACKUP_TMP" "$PROFILE_BACKUP_FILE"; then
    rm -f "$PROFILE_BACKUP_TMP"
    die "Failed to rotate firefox profile backup"
  fi

  chmod 600 "$PROFILE_BACKUP_FILE" 2>/dev/null || true
  backup_size_bytes="$(wc -c < "$PROFILE_BACKUP_FILE" | tr -d '[:space:]' || echo unknown)"
  log "profile_backup_done file=$PROFILE_BACKUP_FILE size_bytes=$backup_size_bytes"
}

prepare_profile() {
  if [[ ! -x "$PREPARE_PROFILE_SCRIPT" ]]; then
    die "Prepare profile script not found or not executable: $PREPARE_PROFILE_SCRIPT"
  fi

  log "profile_prepare_start script=$PREPARE_PROFILE_SCRIPT archive_file=$PROFILE_BACKUP_FILE profile_dir=$SELENIUM_PROFILE_DIR"
  if ! "$PREPARE_PROFILE_SCRIPT" "$PROFILE_BACKUP_FILE" "$SELENIUM_PROFILE_DIR"; then
    die "Failed to prepare firefox selenium profile from archive: $PROFILE_BACKUP_FILE"
  fi
  log "profile_prepare_done profile_dir=$SELENIUM_PROFILE_DIR"
}

trim() {
  local value="$1"
  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"
  printf '%s' "$value"
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
log "selenium_profile_dir=$SELENIUM_PROFILE_DIR"
log "profile_backup_file=$PROFILE_BACKUP_FILE"
log "prepare_profile_script=$PREPARE_PROFILE_SCRIPT"

if [[ ! -f "$COMPOSE_FILE" ]]; then
  die "Missing compose file: $COMPOSE_FILE"
fi

if [[ "$HOST_UID" -eq 0 || "$HOST_GID" -eq 0 ]]; then
  die "Do not run as root. Use DJgurda user context."
fi

log "host_preflight_ok host_uid=$HOST_UID host_gid=$HOST_GID"
backup_profile
prepare_profile
log "profile_ready selenium_profile_dir=$SELENIUM_PROFILE_DIR archive_file=$PROFILE_BACKUP_FILE"

targets=()
if [[ -f "$SOURCES_FILE" ]]; then
  log "sources_parse_start file=$SOURCES_FILE"
  while IFS= read -r raw || [[ -n "$raw" ]]; do
    line="${raw%$'\r'}"
    [[ -z "$line" || "${line:0:1}" == "#" ]] && continue

    IFS='|' read -r source_key source_folder source_urls extra <<< "$line"
    source_key="$(trim "${source_key:-}")"
    source_folder="$(trim "${source_folder:-}")"
    source_urls="$(trim "${source_urls:-}")"
    extra="$(trim "${extra:-}")"

    if [[ -n "$extra" ]]; then
      die "Invalid source format in $SOURCES_FILE (too many fields): $line"
    fi

    if [[ -z "$source_key" || -z "$source_folder" || -z "$source_urls" ]]; then
      die "Invalid source line in $SOURCES_FILE: $line"
    fi

    if [[ "$source_folder" == *"/"* || "$source_folder" == "." || "$source_folder" == ".." ]]; then
      die "Invalid folder name in $SOURCES_FILE: $source_folder"
    fi

    target_dir="$COOKIES_ROOT/$source_folder"
    if ! mkdir -p "$target_dir"; then
      die "Failed to create target directory: $target_dir"
    fi

    IFS=';' read -r -a source_url_items <<< "$source_urls"
    source_target_count=0
    for raw_url in "${source_url_items[@]}"; do
      source_url="$(trim "$raw_url")"
      [[ -z "$source_url" ]] && continue

      if [[ "$source_url" != http://* && "$source_url" != https://* ]]; then
        die "Invalid url in $SOURCES_FILE: $source_url"
      fi

      targets+=("$source_url")
      source_target_count=$((source_target_count + 1))
      log "source=$source_key folder=$target_dir url=$source_url"
    done

    if [[ "$source_target_count" -eq 0 ]]; then
      die "No urls found for source '$source_key' in $SOURCES_FILE"
    fi

    log "source=$source_key urls_count=$source_target_count"
  done < "$SOURCES_FILE"
  log "sources_parse_done file=$SOURCES_FILE total_targets=${#targets[@]}"
else
  log "sources_parse_mode=env reason=sources_file_not_found"
fi

if [[ -z "${REFRESH_TARGETS:-}" ]]; then
  if [[ ${#targets[@]} -eq 0 ]]; then
    die "No refresh targets found. Provide REFRESH_TARGETS or create $SOURCES_FILE"
  fi
  REFRESH_TARGETS="$(IFS=,; echo "${targets[*]}")"
fi

resolved_count="$(awk -F',' '{print NF}' <<< "$REFRESH_TARGETS")"
log "resolved_targets_count=$resolved_count"
log "resolved_targets=$REFRESH_TARGETS"
log "compose_run_start container_name=DJgurda-cookies service=cookies-session-refresher compose_file=$COMPOSE_FILE"

export HOST_UID HOST_GID REFRESH_TARGETS SELENIUM_PROFILE_DIR
set +e
/usr/bin/docker compose -f "$COMPOSE_FILE" run --rm --name DJgurda-cookies cookies-session-refresher
compose_status=$?
set -e

if [[ $compose_status -ne 0 ]]; then
  die "docker compose run failed with exit code $compose_status"
fi

log "compose_run_done container_name=DJgurda-cookies exit_code=0"
log "session refresher run finished successfully"
