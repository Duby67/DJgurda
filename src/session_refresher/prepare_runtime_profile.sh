#!/usr/bin/env bash
set -euo pipefail

PROFILE_DIR="${1:-${REFRESH_FIREFOX_PROFILE:-/session_refresher/firefox_profile}}"

timestamp() {
  date '+%Y-%m-%d %H:%M:%S'
}

log() {
  printf '[%s] [container] %s\n' "$(timestamp)" "$*"
}

die() {
  log "ERROR: $*"
  exit 1
}

if [[ ! -d "$PROFILE_DIR" ]]; then
  die "Firefox profile directory does not exist: $PROFILE_DIR"
fi

log "prepare_runtime_profile_start profile_dir=$PROFILE_DIR"

rm -f \
  "$PROFILE_DIR/.parentlock" \
  "$PROFILE_DIR/.startup-incomplete" \
  "$PROFILE_DIR/lock" \
  "$PROFILE_DIR/.refresh.lock" \
  "$PROFILE_DIR/sessionstore.jsonlz4"
rm -f \
  "$PROFILE_DIR/sessionstore-backups/recovery.jsonlz4" \
  "$PROFILE_DIR/sessionstore-backups/recovery.baklz4" \
  "$PROFILE_DIR/sessionstore-backups/previous.jsonlz4"
rm -f "$PROFILE_DIR"/sessionstore-backups/upgrade.jsonlz4*
rm -rf \
  "$PROFILE_DIR/cache2" \
  "$PROFILE_DIR/startupCache" \
  "$PROFILE_DIR/crashes" \
  "$PROFILE_DIR/minidumps"
find "$PROFILE_DIR" -type l -delete
find "$PROFILE_DIR" -type f \( -name '*.sqlite-shm' -o -name '*.sqlite-wal' \) -delete

profile_items_count="$(find "$PROFILE_DIR" -mindepth 1 -maxdepth 1 | wc -l | tr -d '[:space:]' || echo unknown)"
log "prepare_runtime_profile_done profile_dir=$PROFILE_DIR sessionstore_removed=true cache_removed=true sqlite_sidecars_removed=true symlinks_removed=true profile_items_count=$profile_items_count"
