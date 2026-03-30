#!/usr/bin/env bash
set -euo pipefail

PROFILE_DIR="${REFRESH_FIREFOX_PROFILE:-/session_refresher/firefox_profile}"
FIREFOX_BIN="${REFRESH_FIREFOX_BIN:-/usr/bin/firefox}"
DISPLAY_NUM="${REFRESH_DISPLAY:-:99}"
XVFB_SCREEN="${REFRESH_XVFB_SCREEN:-1024x768x16}"
WARMUP_SECONDS="${REFRESH_WARMUP_SECONDS:-3}"
RUN_SECONDS="${REFRESH_DURATION_SECONDS:-90}"
TARGETS_RAW="${REFRESH_TARGETS:-https://www.youtube.com}"

if [[ ! -d "$PROFILE_DIR" ]]; then
  echo "Firefox profile directory does not exist: $PROFILE_DIR" >&2
  exit 1
fi

if [[ ! -x "$FIREFOX_BIN" ]]; then
  echo "Firefox binary not found or not executable: $FIREFOX_BIN" >&2
  exit 1
fi

# Keep cache/temp writable for non-root container user.
export HOME="${HOME:-/tmp}"
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-$HOME/.cache}"
mkdir -p "$XDG_CACHE_HOME" /tmp/.X11-unix
chmod 1777 /tmp/.X11-unix || true

LOCK_FILE="$PROFILE_DIR/.refresh.lock"
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "Refresh lock is busy, another refresh process is running" >&2
  exit 1
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

Xvfb "$DISPLAY_NUM" -screen 0 "$XVFB_SCREEN" -nolisten tcp >/tmp/xvfb.log 2>&1 &
XVFB_PID=$!

export DISPLAY="$DISPLAY_NUM"
sleep "$WARMUP_SECONDS"

IFS=',' read -r -a TARGETS <<< "$TARGETS_RAW"
if [[ ${#TARGETS[@]} -eq 0 ]]; then
  echo "No refresh targets provided" >&2
  exit 1
fi

echo "Starting Firefox session refresh"
echo "Profile: $PROFILE_DIR"
echo "Targets: ${TARGETS[*]}"

"$FIREFOX_BIN" \
  --no-remote \
  --new-instance \
  --profile "$PROFILE_DIR" \
  "${TARGETS[@]}" >/tmp/firefox-refresh.log 2>&1 &
FIREFOX_PID=$!

sleep "$RUN_SECONDS"

echo "Stopping Firefox and flushing profile changes"
kill -TERM "$FIREFOX_PID" || true
wait "$FIREFOX_PID" || true
unset FIREFOX_PID

echo "Session refresh completed"
