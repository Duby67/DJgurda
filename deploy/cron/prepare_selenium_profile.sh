#!/usr/bin/env bash
set -euo pipefail

SOURCE_PROFILE_DIR="${1:-$HOME/firefox_profile}"
SELENIUM_PROFILE_DIR="${2:-$HOME/firefox_selenium_profile}"

PROFILE_FILES=(
  cookies.sqlite
  permissions.sqlite
  content-prefs.sqlite
  key4.db
  cert9.db
  pkcs11.txt
  logins.json
  formhistory.sqlite
  storage.sqlite
  webappsstore.sqlite
  handlers.json
  places.sqlite
)

PROFILE_DIRS=(
  storage
)

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

copy_profile_item() {
  local item_name="$1"
  local source_path="$SOURCE_PROFILE_DIR_ABS/$item_name"
  local target_path="$SELENIUM_PROFILE_DIR_ABS/$item_name"

  if [[ ! -e "$source_path" ]]; then
    log "selenium_profile_skip_missing item=$item_name"
    return 0
  fi

  mkdir -p "$(dirname "$target_path")"
  cp -a "$source_path" "$target_path"
  log "selenium_profile_item_copied item=$item_name"
}

if [[ ! -d "$SOURCE_PROFILE_DIR" ]]; then
  die "Source Firefox profile directory does not exist: $SOURCE_PROFILE_DIR"
fi

mkdir -p "$SELENIUM_PROFILE_DIR"
SOURCE_PROFILE_DIR_ABS="$(cd "$SOURCE_PROFILE_DIR" && pwd)"
SELENIUM_PROFILE_DIR_ABS="$(cd "$SELENIUM_PROFILE_DIR" && pwd)"

if [[ "$SOURCE_PROFILE_DIR_ABS" == "/" || "$SELENIUM_PROFILE_DIR_ABS" == "/" ]]; then
  die "Unsafe profile path resolved to root"
fi

if [[ "$SOURCE_PROFILE_DIR_ABS" == "$SELENIUM_PROFILE_DIR_ABS" ]]; then
  die "Source and Selenium profile directories must be different: $SOURCE_PROFILE_DIR_ABS"
fi

log "selenium_profile_prepare_start source_profile_dir=$SOURCE_PROFILE_DIR_ABS selenium_profile_dir=$SELENIUM_PROFILE_DIR_ABS"

find "$SELENIUM_PROFILE_DIR_ABS" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
log "selenium_profile_target_cleaned selenium_profile_dir=$SELENIUM_PROFILE_DIR_ABS"

copied_items=0
for item_name in "${PROFILE_FILES[@]}"; do
  if [[ -e "$SOURCE_PROFILE_DIR_ABS/$item_name" ]]; then
    copied_items=$((copied_items + 1))
  fi
  copy_profile_item "$item_name"
done

for item_name in "${PROFILE_DIRS[@]}"; do
  if [[ -e "$SOURCE_PROFILE_DIR_ABS/$item_name" ]]; then
    copied_items=$((copied_items + 1))
  fi
  copy_profile_item "$item_name"
done

find "$SELENIUM_PROFILE_DIR_ABS" -type f \( -name '*.sqlite-shm' -o -name '*.sqlite-wal' \) -delete
rm -f "$SELENIUM_PROFILE_DIR_ABS/.parentlock" "$SELENIUM_PROFILE_DIR_ABS/.startup-incomplete" "$SELENIUM_PROFILE_DIR_ABS/lock"
rm -f "$SELENIUM_PROFILE_DIR_ABS/sessionstore.jsonlz4"
rm -f "$SELENIUM_PROFILE_DIR_ABS/sessionstore-backups/recovery.jsonlz4"
rm -f "$SELENIUM_PROFILE_DIR_ABS/sessionstore-backups/recovery.baklz4"
rm -f "$SELENIUM_PROFILE_DIR_ABS/sessionstore-backups/previous.jsonlz4"
rm -f "$SELENIUM_PROFILE_DIR_ABS/sessionstore-backups/upgrade.jsonlz4"*

chmod 700 "$SELENIUM_PROFILE_DIR_ABS"
chown -R "$(id -u):$(id -g)" "$SELENIUM_PROFILE_DIR_ABS" 2>/dev/null || true

profile_items_count="$(find "$SELENIUM_PROFILE_DIR_ABS" -mindepth 1 -maxdepth 1 | wc -l | tr -d '[:space:]' || echo unknown)"
log "selenium_profile_prepare_done selenium_profile_dir=$SELENIUM_PROFILE_DIR_ABS copied_items=$copied_items profile_items_count=$profile_items_count"
echo "Selenium Firefox profile prepared: $SELENIUM_PROFILE_DIR_ABS"