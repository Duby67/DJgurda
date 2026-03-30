#!/usr/bin/env bash
set -euo pipefail

ARCHIVE_PATH="${1:-$HOME/cookies/runtime/firProf.tar.gz}"
PROFILE_DIR="${2:-$HOME/firefox_profile}"
TMP_DIR="$(mktemp -d)"

cleanup_tmp() {
  rm -rf "$TMP_DIR"
}
trap cleanup_tmp EXIT

if [[ ! -f "$ARCHIVE_PATH" ]]; then
  echo "Archive not found: $ARCHIVE_PATH" >&2
  exit 1
fi

mkdir -p "$PROFILE_DIR"
PROFILE_DIR_ABS="$(cd "$PROFILE_DIR" && pwd)"
if [[ "$PROFILE_DIR_ABS" == "/" ]]; then
  echo "Unsafe profile path resolved to root" >&2
  exit 1
fi

tar -xzf "$ARCHIVE_PATH" -C "$TMP_DIR"

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

find "$PROFILE_DIR_ABS" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
cp -a "$SOURCE_DIR"/. "$PROFILE_DIR_ABS"/

rm -f "$PROFILE_DIR_ABS/.parentlock" "$PROFILE_DIR_ABS/.startup-incomplete" "$PROFILE_DIR_ABS/lock"
rm -rf "$PROFILE_DIR_ABS/cache2" "$PROFILE_DIR_ABS/startupCache" "$PROFILE_DIR_ABS/crashes" "$PROFILE_DIR_ABS/minidumps"
find "$PROFILE_DIR_ABS" -type l -delete
find "$PROFILE_DIR_ABS" -type f \( -name '*.sqlite-shm' -o -name '*.sqlite-wal' \) -delete

chmod 700 "$PROFILE_DIR_ABS"
chown -R "$(id -u):$(id -g)" "$PROFILE_DIR_ABS" 2>/dev/null || true

echo "Firefox profile restored and cleaned: $PROFILE_DIR_ABS"
