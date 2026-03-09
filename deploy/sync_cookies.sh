#!/usr/bin/env bash

set -Eeuo pipefail

# Пути deploy-контура и локального конфига ручной синхронизации.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="${SCRIPT_DIR}/cookies"
CONFIG_FILE="${SCRIPT_DIR}/sync_cookies.env"

if [ ! -f "$CONFIG_FILE" ]; then
    echo "[ERROR] Local sync config not found: ${CONFIG_FILE}"
    echo "[INFO] Create it from ${SCRIPT_DIR}/sync_cookies.env.example"
    exit 1
fi

# Подключаем локальный конфиг с параметрами подключения.
# shellcheck disable=SC1090
source "$CONFIG_FILE"

: "${REMOTE_USER:?REMOTE_USER is not defined in ${CONFIG_FILE}}"
: "${REMOTE_HOST:?REMOTE_HOST is not defined in ${CONFIG_FILE}}"
: "${REMOTE_PORT:?REMOTE_PORT is not defined in ${CONFIG_FILE}}"

if [ ! -d "$SOURCE_DIR" ]; then
    echo "[ERROR] Deploy cookies directory not found: ${SOURCE_DIR}"
    exit 1
fi

TARGET_ENV="${1:-}"
if [ -z "$TARGET_ENV" ]; then
    read -r -p "Type target environment (dev/prod): " TARGET_ENV
fi

case "$TARGET_ENV" in
    dev|prod) ;;
    *)
        echo "[ERROR] Invalid environment: ${TARGET_ENV}. Expected dev or prod."
        exit 1
        ;;
esac

# Целевая server-side директория cookies для выбранного окружения.
REMOTE_DIR="/home/${REMOTE_USER}/bot_${TARGET_ENV}/data/cookies"

command -v ssh >/dev/null 2>&1 || {
    echo "[ERROR] ssh is not found in PATH."
    exit 1
}

command -v scp >/dev/null 2>&1 || {
    echo "[ERROR] scp is not found in PATH."
    exit 1
}

echo "[INFO] Ensuring remote directory exists: ${REMOTE_DIR}"
ssh -p "$REMOTE_PORT" "${REMOTE_USER}@${REMOTE_HOST}" "mkdir -p '${REMOTE_DIR}'"

shopt -s nullglob
cookie_files=("${SOURCE_DIR}"/*_cookies.txt)
shopt -u nullglob

if [ "${#cookie_files[@]}" -eq 0 ]; then
    echo "[WARN] No cookie files found to upload in ${SOURCE_DIR}."
    exit 0
fi

# Синхронизация идет только по локально существующим файлам без удаления server-side остатков.
uploaded_count=0
for cookie_file in "${cookie_files[@]}"; do
    cookie_name="$(basename "$cookie_file")"
    echo "[INFO] Uploading ${cookie_name}"
    scp -P "$REMOTE_PORT" "$cookie_file" "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DIR}/"
    uploaded_count=$((uploaded_count + 1))
done

echo "[OK] Uploaded ${uploaded_count} file(s) to ${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DIR}"
