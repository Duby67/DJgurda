#!/usr/bin/env bash
set -euo pipefail

ARCHIVE_PATH="${1:-$HOME/cookies/runtime/firefox_profile.tar.gz}"
PROFILE_DIR="${2:-$HOME/firefox_profile}"
TMP_DIR="$(mktemp -d)"

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

cleanup_tmp() {
  rm -rf "$TMP_DIR"
}
trap cleanup_tmp EXIT

log "prepare_profile_start archive_path=$ARCHIVE_PATH profile_dir=$PROFILE_DIR tmp_dir=$TMP_DIR"

if [[ ! -f "$ARCHIVE_PATH" ]]; then
  die "Archive not found: $ARCHIVE_PATH"
fi

mkdir -p "$PROFILE_DIR"
PROFILE_DIR_ABS="$(cd "$PROFILE_DIR" && pwd)"
if [[ "$PROFILE_DIR_ABS" == "/" ]]; then
  die "Unsafe profile path resolved to root"
fi

archive_size_bytes="$(wc -c < "$ARCHIVE_PATH" | tr -d '[:space:]' || echo unknown)"
log "prepare_profile_archive_found file=$ARCHIVE_PATH size_bytes=$archive_size_bytes"

log "prepare_profile_extract_start archive_path=$ARCHIVE_PATH tmp_dir=$TMP_DIR"
tar -xzf "$ARCHIVE_PATH" -C "$TMP_DIR"
log "prepare_profile_extract_done tmp_dir=$TMP_DIR"

SOURCE_DIR=""
if [[ -d "$TMP_DIR/firefox_profile" ]]; then
  SOURCE_DIR="$TMP_DIR/firefox_profile"
elif [[ -d "$TMP_DIR/rwui9dvc.default" ]]; then
  SOURCE_DIR="$TMP_DIR/rwui9dvc.default"
else
  DIR_COUNT="$(find "$TMP_DIR" -mindepth 1 -maxdepth 1 -type d | wc -l | tr -d ' ')"
  if [[ "$DIR_COUNT" == "1" ]]; then
    SOURCE_DIR="$(find "$TMP_DIR" -mindepth 1 -maxdepth 1 -type d)"
  else
    SOURCE_DIR="$TMP_DIR"
  fi
fi
log "prepare_profile_source_resolved source_dir=$SOURCE_DIR profile_dir=$PROFILE_DIR_ABS"

log "prepare_profile_replace_start profile_dir=$PROFILE_DIR_ABS"
find "$PROFILE_DIR_ABS" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
cp -a "$SOURCE_DIR"/. "$PROFILE_DIR_ABS"/
log "prepare_profile_replace_done profile_dir=$PROFILE_DIR_ABS"

log "prepare_profile_cleanup_start profile_dir=$PROFILE_DIR_ABS"
rm -f "$PROFILE_DIR_ABS/.parentlock" "$PROFILE_DIR_ABS/.startup-incomplete" "$PROFILE_DIR_ABS/lock"
rm -f "$PROFILE_DIR_ABS/sessionstore.jsonlz4"
rm -f "$PROFILE_DIR_ABS/sessionstore-backups/recovery.jsonlz4"
rm -f "$PROFILE_DIR_ABS/sessionstore-backups/recovery.baklz4"
rm -f "$PROFILE_DIR_ABS/sessionstore-backups/previous.jsonlz4"
rm -f "$PROFILE_DIR_ABS/sessionstore-backups/upgrade.jsonlz4"*
rm -rf "$PROFILE_DIR_ABS/cache2" "$PROFILE_DIR_ABS/startupCache" "$PROFILE_DIR_ABS/crashes" "$PROFILE_DIR_ABS/minidumps"
find "$PROFILE_DIR_ABS" -type l -delete
find "$PROFILE_DIR_ABS" -type f \( -name '*.sqlite-shm' -o -name '*.sqlite-wal' \) -delete
log "prepare_profile_cleanup_done profile_dir=$PROFILE_DIR_ABS sessionstore_removed=true cache_removed=true sqlite_sidecars_removed=true symlinks_removed=true"

chmod 700 "$PROFILE_DIR_ABS"
chown -R "$(id -u):$(id -g)" "$PROFILE_DIR_ABS" 2>/dev/null || true

profile_items_count="$(find "$PROFILE_DIR_ABS" -mindepth 1 -maxdepth 1 | wc -l | tr -d '[:space:]' || echo unknown)"
log "prepare_profile_done profile_dir=$PROFILE_DIR_ABS profile_items_count=$profile_items_count"
echo "Firefox profile restored and cleaned: $PROFILE_DIR_ABS"
