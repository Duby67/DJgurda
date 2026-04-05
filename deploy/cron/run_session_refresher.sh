#!/usr/bin/env bash
set -euo pipefail

PROFILE_ARCHIVE_PATH="${1:-${PROFILE_ARCHIVE_PATH:-}}"
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
FIREFOX_PROFILE_DIR="${FIREFOX_PROFILE_DIR:-${SELENIUM_PROFILE_DIR:-$HOME/firefox_profile}}"
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


trim() {
  local value="$1"
  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"
  printf '%s' "$value"
}


backup_profile() {
  if [[ ! -d "$FIREFOX_PROFILE_DIR" ]]; then
    log "profile_backup_skip reason=profile_dir_missing profile_dir=$FIREFOX_PROFILE_DIR"
    return 0
  fi

  if ! mkdir -p "$(dirname "$PROFILE_BACKUP_FILE")"; then
    die "Failed to create backup directory for: $PROFILE_BACKUP_FILE"
  fi

  log "profile_backup_start profile_dir=$FIREFOX_PROFILE_DIR backup_file=$PROFILE_BACKUP_FILE"
  rm -f "$PROFILE_BACKUP_TMP"

  if ! tar -C "$FIREFOX_PROFILE_DIR" \
    --exclude='.parentlock' \
    --exclude='.startup-incomplete' \
    --exclude='lock' \
    --exclude='*.sqlite-shm' \
    --exclude='*.sqlite-wal' \
    -czf "$PROFILE_BACKUP_TMP" .; then
    rm -f "$PROFILE_BACKUP_TMP"
    die "Failed to create firefox profile backup"
  fi

  if ! mv -f "$PROFILE_BACKUP_TMP" "$PROFILE_BACKUP_FILE"; then
    rm -f "$PROFILE_BACKUP_TMP"
    die "Failed to rotate firefox profile backup"
  fi

  chmod 600 "$PROFILE_BACKUP_FILE" 2>/dev/null || true
  local backup_size_bytes
  backup_size_bytes="$(wc -c < "$PROFILE_BACKUP_FILE" | tr -d '[:space:]' || echo unknown)"
  log "profile_backup_done file=$PROFILE_BACKUP_FILE size_bytes=$backup_size_bytes"
}


extract_archive() {
  local archive_path="$1"
  local target_dir="$2"

  case "$archive_path" in
    *.tar.gz|*.tgz)
      tar -xzf "$archive_path" -C "$target_dir"
      ;;
    *.tar)
      tar -xf "$archive_path" -C "$target_dir"
      ;;
    *.7z)
      if command -v 7z >/dev/null 2>&1; then
        7z x -y "$archive_path" "-o$target_dir" >/dev/null
      elif command -v 7za >/dev/null 2>&1; then
        7za x -y "$archive_path" "-o$target_dir" >/dev/null
      else
        die "7z archive provided but neither 7z nor 7za is installed: $archive_path"
      fi
      ;;
    *)
      die "Unsupported profile archive format: $archive_path"
      ;;
  esac
}


resolve_source_dir() {
  local tmp_dir="$1"

  if [[ -d "$tmp_dir/firefox_profile" ]]; then
    printf '%s' "$tmp_dir/firefox_profile"
    return 0
  fi

  local dir_count
  dir_count="$(find "$tmp_dir" -mindepth 1 -maxdepth 1 -type d | wc -l | tr -d '[:space:]')"
  if [[ "$dir_count" == "1" ]]; then
    find "$tmp_dir" -mindepth 1 -maxdepth 1 -type d
    return 0
  fi

  printf '%s' "$tmp_dir"
}


restore_profile_from_archive() {
  local archive_path="$1"

  if [[ -z "$archive_path" ]]; then
    return 0
  fi

  if [[ ! -f "$archive_path" ]]; then
    die "Profile archive not found: $archive_path"
  fi

  mkdir -p "$FIREFOX_PROFILE_DIR"
  local profile_dir_abs
  profile_dir_abs="$(cd "$FIREFOX_PROFILE_DIR" && pwd)"
  if [[ "$profile_dir_abs" == "/" ]]; then
    die "Unsafe firefox profile path resolved to root"
  fi

  local tmp_dir
  tmp_dir="$(mktemp -d)"
  trap 'rm -rf "$tmp_dir"' RETURN

  local archive_size_bytes
  archive_size_bytes="$(wc -c < "$archive_path" | tr -d '[:space:]' || echo unknown)"
  log "profile_restore_start archive_file=$archive_path profile_dir=$profile_dir_abs archive_size_bytes=$archive_size_bytes"
  log "profile_extract_start archive_file=$archive_path tmp_dir=$tmp_dir"
  extract_archive "$archive_path" "$tmp_dir"
  log "profile_extract_done tmp_dir=$tmp_dir"

  local source_dir
  source_dir="$(resolve_source_dir "$tmp_dir")"
  log "profile_source_resolved source_dir=$source_dir profile_dir=$profile_dir_abs"

  find "$profile_dir_abs" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
  cp -a "$source_dir"/. "$profile_dir_abs"/
  chmod 700 "$profile_dir_abs"
  chown -R "$(id -u):$(id -g)" "$profile_dir_abs" 2>/dev/null || true

  local profile_items_count
  profile_items_count="$(find "$profile_dir_abs" -mindepth 1 -maxdepth 1 | wc -l | tr -d '[:space:]' || echo unknown)"
  log "profile_restore_done profile_dir=$profile_dir_abs profile_items_count=$profile_items_count"
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
log "firefox_profile_dir=$FIREFOX_PROFILE_DIR"
log "profile_backup_file=$PROFILE_BACKUP_FILE"
log "profile_archive_path=${PROFILE_ARCHIVE_PATH:-n/a}"

if [[ ! -f "$COMPOSE_FILE" ]]; then
  die "Missing compose file: $COMPOSE_FILE"
fi

if [[ "$HOST_UID" -eq 0 || "$HOST_GID" -eq 0 ]]; then
  die "Do not run as root. Use DJgurda user context."
fi

log "host_preflight_ok host_uid=$HOST_UID host_gid=$HOST_GID"
backup_profile
restore_profile_from_archive "$PROFILE_ARCHIVE_PATH"

if [[ ! -d "$FIREFOX_PROFILE_DIR" ]]; then
  die "Firefox profile directory does not exist: $FIREFOX_PROFILE_DIR"
fi

log "profile_ready firefox_profile_dir=$FIREFOX_PROFILE_DIR backup_file=$PROFILE_BACKUP_FILE archive_file=${PROFILE_ARCHIVE_PATH:-n/a}"

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

export HOST_UID HOST_GID REFRESH_TARGETS FIREFOX_PROFILE_DIR
set +e
/usr/bin/docker compose -f "$COMPOSE_FILE" run --rm --name DJgurda-cookies cookies-session-refresher
compose_status=$?
set -e

if [[ $compose_status -ne 0 ]]; then
  die "docker compose run failed with exit code $compose_status"
fi

log "compose_run_done container_name=DJgurda-cookies exit_code=0"
log "session refresher run finished successfully"
