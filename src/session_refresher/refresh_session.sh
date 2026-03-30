#!/usr/bin/env bash
set -euo pipefail

PROFILE_DIR="${REFRESH_FIREFOX_PROFILE:-/session_refresher/firefox_profile}"
FIREFOX_BIN="${REFRESH_FIREFOX_BIN:-/usr/bin/firefox}"
DBUS_RUN_SESSION_BIN="${REFRESH_DBUS_RUN_SESSION_BIN:-/usr/bin/dbus-run-session}"
DISPLAY_NUM="${REFRESH_DISPLAY:-:99}"
XVFB_SCREEN="${REFRESH_XVFB_SCREEN:-1024x768x16}"
WARMUP_SECONDS="${REFRESH_WARMUP_SECONDS:-3}"
RUN_SECONDS="${REFRESH_DURATION_SECONDS:-90}"
HEARTBEAT_SECONDS="${REFRESH_HEARTBEAT_SECONDS:-30}"
TARGETS_RAW="${REFRESH_TARGETS:-https://www.youtube.com}"

timestamp() {
  date '+%Y-%m-%d %H:%M:%S'
}

log() {
  printf '[%s] [container] %s\n' "$(timestamp)" "$*"
}

warn() {
  log "WARN: $*"
}

trim() {
  local value="$1"
  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"
  printf '%s' "$value"
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

die() {
  log "ERROR: $*"
  dump_debug_logs
  exit 1
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

# Keep cache/temp writable for non-root container user.
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
log "warmup_seconds=$WARMUP_SECONDS run_seconds=$RUN_SECONDS heartbeat_seconds=$HEARTBEAT_SECONDS"

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

for target in "${TARGETS[@]}"; do
  log "target=$target"
done

"$DBUS_RUN_SESSION_BIN" -- "$FIREFOX_BIN" \
  --no-remote \
  --new-instance \
  --profile "$PROFILE_DIR" \
  "${TARGETS[@]}" >/tmp/firefox-refresh.log 2>&1 &
FIREFOX_PID=$!

sleep 5
if ! kill -0 "$FIREFOX_PID" 2>/dev/null; then
  die "Firefox exited too early"
fi

remaining="$RUN_SECONDS"
while [[ "$remaining" -gt 0 ]]; do
  step="$HEARTBEAT_SECONDS"
  if [[ "$step" -gt "$remaining" ]]; then
    step="$remaining"
  fi

  sleep "$step"
  remaining=$((remaining - step))

  if ! kill -0 "$FIREFOX_PID" 2>/dev/null; then
    die "Firefox exited before refresh window finished"
  fi

  log "heartbeat: firefox alive, remaining=${remaining}s"
done

log "Stopping Firefox and flushing profile changes"
kill -TERM "$FIREFOX_PID" 2>/dev/null || true
set +e
wait "$FIREFOX_PID"
firefox_status=$?
set -e
unset FIREFOX_PID

if [[ "$firefox_status" -ne 0 && "$firefox_status" -ne 143 ]]; then
  warn "Firefox exited with status $firefox_status"
fi

log "Session refresh completed"
dump_debug_logs
