#!/usr/bin/env bash
set -euo pipefail

PROFILE_DIR="${REFRESH_FIREFOX_PROFILE:-/session_refresher/firefox_profile}"
FIREFOX_BIN="${REFRESH_FIREFOX_BIN:-/usr/bin/firefox}"
DBUS_RUN_SESSION_BIN="${REFRESH_DBUS_RUN_SESSION_BIN:-/usr/bin/dbus-run-session}"
DISPLAY_NUM="${REFRESH_DISPLAY:-:99}"
XVFB_SCREEN="${REFRESH_XVFB_SCREEN:-1024x768x16}"
WARMUP_SECONDS="${REFRESH_WARMUP_SECONDS:-3}"
HEARTBEAT_SECONDS="${REFRESH_HEARTBEAT_SECONDS:-15}"
TARGETS_RAW="${REFRESH_TARGETS:-https://www.youtube.com}"

# Backward compatibility: fixed duration if REFRESH_DURATION_SECONDS is set.
FIXED_DURATION_SECONDS="${REFRESH_DURATION_SECONDS:-}"
URL_DURATION_MIN_RAW="${REFRESH_URL_DURATION_MIN:-}"
URL_DURATION_MAX_RAW="${REFRESH_URL_DURATION_MAX:-}"
URL_DURATION_MIN=""
URL_DURATION_MAX=""

COOKIES_DB=""
COOKIE_DOMAINS=()
declare -A COOKIES_BEFORE=()
declare -A COOKIES_AFTER=()

timestamp() {
  date '+%Y-%m-%d %H:%M:%S'
}

log() {
  printf '[%s] [container] %s\n' "$(timestamp)" "$*"
}

warn() {
  log "WARN: $*"
}

die() {
  log "ERROR: $*"
  dump_debug_logs
  exit 1
}

trim() {
  local value="$1"
  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"
  printf '%s' "$value"
}

is_positive_int() {
  [[ "$1" =~ ^[1-9][0-9]*$ ]]
}

resolve_duration_bounds() {
  local min_candidate="${URL_DURATION_MIN_RAW:-}"
  local max_candidate="${URL_DURATION_MAX_RAW:-}"

  if [[ -n "$FIXED_DURATION_SECONDS" ]]; then
    if ! is_positive_int "$FIXED_DURATION_SECONDS"; then
      die "REFRESH_DURATION_SECONDS must be a positive integer"
    fi

    if [[ -z "$min_candidate" ]]; then
      min_candidate="$FIXED_DURATION_SECONDS"
    fi

    if [[ -z "$max_candidate" ]]; then
      max_candidate="$FIXED_DURATION_SECONDS"
    fi
  fi

  if [[ -z "$min_candidate" && -z "$max_candidate" ]]; then
    min_candidate="60"
    max_candidate="90"
  elif [[ -z "$min_candidate" ]]; then
    min_candidate="$max_candidate"
  elif [[ -z "$max_candidate" ]]; then
    max_candidate="$min_candidate"
  fi

  if ! is_positive_int "$min_candidate"; then
    die "REFRESH_URL_DURATION_MIN must be a positive integer"
  fi

  if ! is_positive_int "$max_candidate"; then
    die "REFRESH_URL_DURATION_MAX must be a positive integer"
  fi

  if (( min_candidate > max_candidate )); then
    die "REFRESH_URL_DURATION_MIN cannot be greater than REFRESH_URL_DURATION_MAX"
  fi

  URL_DURATION_MIN="$min_candidate"
  URL_DURATION_MAX="$max_candidate"
}

pick_random_duration() {
  if (( URL_DURATION_MIN == URL_DURATION_MAX )); then
    echo "$URL_DURATION_MIN"
    return
  fi

  local span=$((URL_DURATION_MAX - URL_DURATION_MIN + 1))
  echo $((URL_DURATION_MIN + RANDOM % span))
}

extract_host_from_url() {
  local url="$1"
  local host="${url#*://}"
  host="${host%%/*}"
  host="${host%%:*}"
  printf '%s' "$(trim "$host")"
}

build_cookie_domains() {
  declare -A seen=()
  COOKIE_DOMAINS=()

  for target in "${TARGETS[@]}"; do
    local host
    host="$(extract_host_from_url "$target")"
    [[ -z "$host" ]] && continue

    if [[ -z "${seen[$host]:-}" ]]; then
      COOKIE_DOMAINS+=("$host")
      seen["$host"]=1
    fi

    if [[ "$host" == *"youtube.com" ]] && [[ -z "${seen[google.com]:-}" ]]; then
      COOKIE_DOMAINS+=("google.com")
      seen["google.com"]=1
    fi
  done

  for domain in "${COOKIE_DOMAINS[@]}"; do
    log "cookie_domain_watch=$domain"
  done
}

run_sqlite_query() {
  local sql="$1"
  local output=""
  local status=0
  local sqlite_error=""

  set +e
  output="$(sqlite3 -readonly "$COOKIES_DB" "$sql" 2>/tmp/sqlite-refresh.log)"
  status=$?
  set -e

  if [[ $status -ne 0 ]]; then
    sqlite_error="$(tr '\n' ' ' </tmp/sqlite-refresh.log 2>/dev/null || true)"
    sqlite_error="$(trim "$sqlite_error")"
    warn "sqlite query failed: ${sqlite_error:-unknown error}"
    return 1
  fi

  printf '%s' "$output"
}

capture_cookie_snapshot() {
  local label="$1"
  local map_name="$2"
  declare -n out_map="$map_name"

  out_map=()

  if [[ ! -f "$COOKIES_DB" ]]; then
    warn "cookies sqlite database not found: $COOKIES_DB"
    return
  fi

  if ! command -v sqlite3 >/dev/null 2>&1; then
    warn "sqlite3 is not available in container"
    return
  fi

  for domain in "${COOKIE_DOMAINS[@]}"; do
    local domain_safe
    local stats
    domain_safe="$(printf '%s' "$domain" | tr -cd 'A-Za-z0-9.-')"
    [[ -z "$domain_safe" ]] && continue

    stats="$(run_sqlite_query "SELECT count(*), COALESCE(datetime(max(lastAccessed)/1000000,'unixepoch'),'n/a'), COALESCE(datetime(max(expiry),'unixepoch'),'n/a') FROM moz_cookies WHERE host LIKE '%${domain_safe}';")" || stats="query_error"
    out_map["$domain"]="$stats"
    log "cookies_${label} domain=$domain stats=$stats"
  done

  local all_stats
  all_stats="$(run_sqlite_query "SELECT count(*), COALESCE(datetime(max(lastAccessed)/1000000,'unixepoch'),'n/a'), COALESCE(datetime(max(expiry),'unixepoch'),'n/a') FROM moz_cookies;")" || all_stats="query_error"
  out_map["__all__"]="$all_stats"
  log "cookies_${label} domain=__all__ stats=$all_stats"
}

compare_cookie_snapshots() {
  for domain in "${COOKIE_DOMAINS[@]}" "__all__"; do
    local before
    local after
    before="${COOKIES_BEFORE[$domain]:-n/a}"
    after="${COOKIES_AFTER[$domain]:-n/a}"

    if [[ "$before" == "$after" ]]; then
      log "cookies_compare domain=$domain status=unchanged before=$before after=$after"
    else
      log "cookies_compare domain=$domain status=changed before=$before after=$after"
    fi
  done
}

dump_debug_logs() {
  if [[ -f /tmp/firefox-refresh.log ]]; then
    log "tail firefox-refresh.log"
    tail -n 120 /tmp/firefox-refresh.log | sed 's/^/[firefox] /'
  fi

  if [[ -f /tmp/xvfb.log ]]; then
    log "tail xvfb.log"
    tail -n 120 /tmp/xvfb.log | sed 's/^/[xvfb] /'
  fi
}

run_single_target() {
  local target="$1"
  local step_index="$2"
  local total_steps="$3"
  local duration="$4"
  local remaining="$duration"
  local firefox_status=0

  log "step_start index=$step_index/$total_steps target=$target duration_seconds=$duration"

  "$DBUS_RUN_SESSION_BIN" -- "$FIREFOX_BIN" \
    --no-remote \
    --new-instance \
    --profile "$PROFILE_DIR" \
    "$target" >>/tmp/firefox-refresh.log 2>&1 &
  FIREFOX_PID=$!

  sleep 5
  if ! kill -0 "$FIREFOX_PID" 2>/dev/null; then
    die "Firefox exited too early for target=$target"
  fi

  while [[ "$remaining" -gt 0 ]]; do
    local step="$HEARTBEAT_SECONDS"
    if [[ "$step" -gt "$remaining" ]]; then
      step="$remaining"
    fi

    sleep "$step"
    remaining=$((remaining - step))

    if ! kill -0 "$FIREFOX_PID" 2>/dev/null; then
      die "Firefox exited before target window finished: target=$target remaining=${remaining}s"
    fi

    log "step_progress index=$step_index/$total_steps target=$target remaining=${remaining}s"
  done

  kill -TERM "$FIREFOX_PID" 2>/dev/null || true
  set +e
  wait "$FIREFOX_PID"
  firefox_status=$?
  set -e
  unset FIREFOX_PID

  if [[ "$firefox_status" -ne 0 && "$firefox_status" -ne 143 ]]; then
    warn "Firefox exited with status $firefox_status for target=$target"
  fi

  log "step_done index=$step_index/$total_steps target=$target duration_seconds=$duration"
}

if [[ ! -d "$PROFILE_DIR" ]]; then
  die "Firefox profile directory does not exist: $PROFILE_DIR"
fi

if [[ ! -x "$FIREFOX_BIN" ]]; then
  die "Firefox binary not found or not executable: $FIREFOX_BIN"
fi

if [[ ! -x "$DBUS_RUN_SESSION_BIN" ]]; then
  die "dbus-run-session binary not found or not executable: $DBUS_RUN_SESSION_BIN"
fi

if ! is_positive_int "$WARMUP_SECONDS"; then
  die "REFRESH_WARMUP_SECONDS must be a positive integer"
fi

if ! is_positive_int "$HEARTBEAT_SECONDS"; then
  die "REFRESH_HEARTBEAT_SECONDS must be a positive integer"
fi

resolve_duration_bounds

export HOME="${HOME:-/tmp}"
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-$HOME/.cache}"
export NO_AT_BRIDGE="${NO_AT_BRIDGE:-1}"
mkdir -p "$XDG_CACHE_HOME"
mkdir -p /tmp/.X11-unix 2>/dev/null || true

if [[ ! -w "$XDG_CACHE_HOME" ]]; then
  warn "cache directory is not writable: $XDG_CACHE_HOME"
fi

LOCK_FILE="$PROFILE_DIR/.refresh.lock"
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  die "Refresh lock is busy, another refresh process is running"
fi

cleanup() {
  if [[ -n "${FIREFOX_PID:-}" ]] && kill -0 "$FIREFOX_PID" 2>/dev/null; then
    kill -TERM "$FIREFOX_PID" || true
    wait "$FIREFOX_PID" || true
  fi

  if [[ -n "${XVFB_PID:-}" ]] && kill -0 "$XVFB_PID" 2>/dev/null; then
    kill -TERM "$XVFB_PID" || true
    wait "$XVFB_PID" || true
  fi

  rm -f "$PROFILE_DIR/.parentlock" "$PROFILE_DIR/.startup-incomplete" "$PROFILE_DIR/lock"
}
trap cleanup EXIT

log "Starting Firefox session refresh"
log "profile=$PROFILE_DIR"
log "firefox_bin=$FIREFOX_BIN"
log "dbus_run_session_bin=$DBUS_RUN_SESSION_BIN"
log "display=$DISPLAY_NUM xvfb_screen=$XVFB_SCREEN"
log "warmup_seconds=$WARMUP_SECONDS heartbeat_seconds=$HEARTBEAT_SECONDS"
log "url_duration_min=$URL_DURATION_MIN url_duration_max=$URL_DURATION_MAX"

Xvfb "$DISPLAY_NUM" -screen 0 "$XVFB_SCREEN" -nolisten tcp >/tmp/xvfb.log 2>&1 &
XVFB_PID=$!

export DISPLAY="$DISPLAY_NUM"
sleep "$WARMUP_SECONDS"

if ! kill -0 "$XVFB_PID" 2>/dev/null; then
  die "Xvfb failed to start"
fi

IFS=',' read -r -a TARGETS_RAW_ARRAY <<< "$TARGETS_RAW"
TARGETS=()
for raw_target in "${TARGETS_RAW_ARRAY[@]}"; do
  target="$(trim "$raw_target")"
  [[ -n "$target" ]] && TARGETS+=("$target")
done

if [[ ${#TARGETS[@]} -eq 0 ]]; then
  die "No refresh targets provided"
fi

total_targets="${#TARGETS[@]}"
log "targets_total=$total_targets"
for target in "${TARGETS[@]}"; do
  log "target=$target"
done

build_cookie_domains
COOKIES_DB="$PROFILE_DIR/cookies.sqlite"
capture_cookie_snapshot "before" COOKIES_BEFORE

for idx in "${!TARGETS[@]}"; do
  step_index=$((idx + 1))
  target="${TARGETS[$idx]}"
  duration="$(pick_random_duration)"
  run_single_target "$target" "$step_index" "$total_targets" "$duration"
done

capture_cookie_snapshot "after" COOKIES_AFTER
compare_cookie_snapshots

log "Session refresh completed"
dump_debug_logs
