#!/usr/bin/env bash
set -euo pipefail

PROFILE_DIR="${REFRESH_FIREFOX_PROFILE:-/session_refresher/firefox_profile}"
DISPLAY_NUM="${REFRESH_DISPLAY:-:99}"
XVFB_SCREEN="${REFRESH_XVFB_SCREEN:-800x600x16}"
WARMUP_SECONDS="${REFRESH_WARMUP_SECONDS:-3}"
HEARTBEAT_SECONDS="${REFRESH_HEARTBEAT_SECONDS:-15}"
DBUS_RUN_SESSION_BIN="${REFRESH_DBUS_RUN_SESSION_BIN:-/usr/bin/dbus-run-session}"
PYTHON_BIN="${REFRESH_PYTHON_BIN:-/opt/venv/bin/python}"
REFRESH_SCRIPT="${REFRESH_SCRIPT:-/session_refresher/refresh_session.py}"

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

is_positive_int() {
  [[ "$1" =~ ^[1-9][0-9]*$ ]]
}

dump_debug_logs() {
  if [[ -f /tmp/firefox-refresh.log ]]; then
    log "tail firefox-refresh.log"
    tail -n 120 /tmp/firefox-refresh.log | sed 's/^/[firefox] /'
  fi

  if [[ -f /tmp/geckodriver.log ]]; then
    log "tail geckodriver.log"
    tail -n 120 /tmp/geckodriver.log | sed 's/^/[geckodriver] /'
  fi

  if [[ -f /tmp/xvfb.log ]]; then
    log "tail xvfb.log"
    tail -n 120 /tmp/xvfb.log | sed 's/^/[xvfb] /'
  fi
}

if [[ ! -d "$PROFILE_DIR" ]]; then
  die "Firefox profile directory does not exist: $PROFILE_DIR"
fi

if [[ ! -x "$DBUS_RUN_SESSION_BIN" ]]; then
  die "dbus-run-session binary not found or not executable: $DBUS_RUN_SESSION_BIN"
fi

if [[ ! -x "$PYTHON_BIN" ]]; then
  die "Python binary not found or not executable: $PYTHON_BIN"
fi

if [[ ! -f "$REFRESH_SCRIPT" ]]; then
  die "Refresh script not found: $REFRESH_SCRIPT"
fi

if ! is_positive_int "$WARMUP_SECONDS"; then
  die "REFRESH_WARMUP_SECONDS must be a positive integer"
fi

if ! is_positive_int "$HEARTBEAT_SECONDS"; then
  die "REFRESH_HEARTBEAT_SECONDS must be a positive integer"
fi

# Keep cache/temp writable for non-root container user.
export HOME="${HOME:-/home/DJgurda}"
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
  if [[ -n "${RUNNER_PID:-}" ]] && kill -0 "$RUNNER_PID" 2>/dev/null; then
    kill -TERM "$RUNNER_PID" || true
    wait "$RUNNER_PID" || true
  fi

  if [[ -n "${XVFB_PID:-}" ]] && kill -0 "$XVFB_PID" 2>/dev/null; then
    kill -TERM "$XVFB_PID" || true
    wait "$XVFB_PID" || true
  fi

  rm -f "$PROFILE_DIR/.parentlock" "$PROFILE_DIR/.startup-incomplete" "$PROFILE_DIR/lock"
}
trap cleanup EXIT

log "Starting Selenium runtime wrapper"
log "profile=$PROFILE_DIR"
log "display=$DISPLAY_NUM xvfb_screen=$XVFB_SCREEN"
log "python_bin=$PYTHON_BIN refresh_script=$REFRESH_SCRIPT"

Xvfb "$DISPLAY_NUM" -screen 0 "$XVFB_SCREEN" -nolisten tcp >/tmp/xvfb.log 2>&1 &
XVFB_PID=$!

export DISPLAY="$DISPLAY_NUM"
sleep "$WARMUP_SECONDS"

if ! kill -0 "$XVFB_PID" 2>/dev/null; then
  die "Xvfb failed to start"
fi

set +e
"$DBUS_RUN_SESSION_BIN" -- "$PYTHON_BIN" "$REFRESH_SCRIPT" &
RUNNER_PID=$!
wait "$RUNNER_PID"
runner_status=$?
set -e
unset RUNNER_PID

if [[ $runner_status -ne 0 ]]; then
  die "Selenium refresher runner failed with exit code $runner_status"
fi

log "Selenium refresher runner finished successfully"
dump_debug_logs
