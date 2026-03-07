#!/bin/bash

# Скрипт должен завершаться при любой нештатной ситуации.
# Важно: manager.sh является ЕДИНЫМ скриптом для двух окружений (dev и prod).
# Любые изменения обязаны сохранять корректный перезапуск обоих контейнеров,
# так как prod может временно отставать от dev по версии/конфигурации.
set -Eeuo pipefail

if [ -z "${1:-}" ]; then
    echo "Использование: $0 {prod|dev}"
    exit 1
fi

ENVIRONMENT="$1"
SCRIPT_START_TS="$(date +%s)"
CURRENT_STEP="init"
LOCK_HELD=0

# Ранний валидатор окружения до инициализации логирования.
case "$ENVIRONMENT" in
    prod|dev) ;;
    *)
        echo "Некорректное окружение: ${ENVIRONMENT}. Используй prod или dev."
        exit 1
        ;;
esac

BOT_DIR="$HOME/bot_${ENVIRONMENT}"
LOGS_DIR="${BOT_DIR}/logs"
LOG_FILE="${LOGS_DIR}/manager.log"
if ! mkdir -p "$LOGS_DIR"; then
    echo "Не удалось создать каталог логов: ${LOGS_DIR}"
    echo "Проверь права на ${BOT_DIR} и владельца директории."
    exit 1
fi
RUN_UID="$(id -u)"
RUN_GID="$(id -g)"

# Настраиваем единый вывод в консоль и в лог-файл.
exec > >(tee -a "$LOG_FILE") 2>&1

REQUIRED_ENV_KEYS=(
    "ADMIN_ID"
    "BOT_VERSION"
    "BOT_DB_PATH"
    "BOT_TOKEN"
    "YANDEX_MUSIC_TOKEN"
    "YOUTUBE_COOKIES_PATH"
)

# Ожидаемые пути внутри контейнера (должны совпадать с .env на сервере).
EXPECTED_BOT_DB_PATH="/app/src/data/db/bot.db"
EXPECTED_YT_COOKIES_PATH="/app/src/data/cookies/youtube_cookies.txt"

timestamp() {
    date "+%Y-%m-%d %H:%M:%S"
}

log() {
    local level="$1"
    shift
    printf "[%s] [%s] [%s] %s\n" "$(timestamp)" "$level" "$CURRENT_STEP" "$*"
}

fail() {
    log "ERROR" "$1"
    exit 1
}

on_error() {
    local exit_code="$1"
    local line_no="$2"
    log "ERROR" "Step failed at line ${line_no} (exit code: ${exit_code})"
    exit "$exit_code"
}

trap 'on_error $? $LINENO' ERR
trap 'release_deploy_lock' EXIT

run_step() {
    local step="$1"
    shift
    CURRENT_STEP="$step"
    log "INFO" "Step started"
    "$@"
    log "INFO" "Step finished successfully"
}

configure_environment() {
    case "$ENVIRONMENT" in
        prod)
            CONTAINER_NAME="DJgurda-prod"
            IMAGE="ghcr.io/duby67/djgurda:latest"
            RESTART_POLICY="always"
            ;;
        dev)
            CONTAINER_NAME="DJgurda-dev"
            IMAGE="ghcr.io/duby67/djgurda:dev-latest"
            # Для dev контейнер не должен автоперезапускаться.
            RESTART_POLICY="no"
            ;;
        *)
            fail "Invalid environment: ${ENVIRONMENT}"
            ;;
    esac

    DB_DIR="${BOT_DIR}/data/db"
    COOKIES_DIR="${BOT_DIR}/data/cookies"
    TEMP_DIR="${BOT_DIR}/data/temp_files"
    COOKIES_FILE="${COOKIES_DIR}/youtube_cookies.txt"
    ENV_FILE="${BOT_DIR}/.env"

    # Защиты от конкурентных запусков и технических окон.
    LOCK_WAIT_SECONDS="${LOCK_WAIT_SECONDS:-1800}"
    GLOBAL_LOCK_FILE="${HOME}/.cache/djgurda/deploy.lock"
    GLOBAL_FREEZE_FILE="${HOME}/.bot_deploy.freeze"
    ENV_FREEZE_FILE="${BOT_DIR}/.deploy.freeze"
}

acquire_deploy_lock() {
    mkdir -p "$(dirname "$GLOBAL_LOCK_FILE")"
    exec 9>"$GLOBAL_LOCK_FILE"

    log "INFO" "Waiting for deploy lock (timeout: ${LOCK_WAIT_SECONDS}s)"
    if ! flock -w "$LOCK_WAIT_SECONDS" 9; then
        fail "Failed to acquire deploy lock in ${LOCK_WAIT_SECONDS}s: ${GLOBAL_LOCK_FILE}"
    fi

    LOCK_HELD=1
    log "INFO" "Deploy lock acquired: ${GLOBAL_LOCK_FILE}"
}

release_deploy_lock() {
    if [ "$LOCK_HELD" -eq 1 ]; then
        flock -u 9 || true
        LOCK_HELD=0
        log "INFO" "Deploy lock released: ${GLOBAL_LOCK_FILE}"
    fi
}

get_env_value() {
    local key="$1"
    grep -E "^${key}=" "$ENV_FILE" | tail -n 1 | cut -d '=' -f 2-
}

check_required_env_keys() {
    local missing=0
    for key in "${REQUIRED_ENV_KEYS[@]}"; do
        if ! grep -Eq "^${key}=.+" "$ENV_FILE"; then
            log "ERROR" "Missing or empty key in ${ENV_FILE}: ${key}"
            missing=1
        fi
    done

    if [ "$missing" -ne 0 ]; then
        fail "Preflight failed: required env keys are invalid"
    fi
}

check_expected_container_paths() {
    local env_db_path
    local env_cookies_path

    env_db_path="$(get_env_value "BOT_DB_PATH")"
    env_cookies_path="$(get_env_value "YOUTUBE_COOKIES_PATH")"

    if [ "$env_db_path" != "$EXPECTED_BOT_DB_PATH" ]; then
        fail "Preflight failed: BOT_DB_PATH='${env_db_path}', expected '${EXPECTED_BOT_DB_PATH}'"
    fi

    if [ "$env_cookies_path" != "$EXPECTED_YT_COOKIES_PATH" ]; then
        fail "Preflight failed: YOUTUBE_COOKIES_PATH='${env_cookies_path}', expected '${EXPECTED_YT_COOKIES_PATH}'"
    fi
}

preflight() {
    command -v docker >/dev/null 2>&1 || fail "Preflight failed: docker not found in PATH"
    command -v flock >/dev/null 2>&1 || fail "Preflight failed: flock not found in PATH"
    docker info >/dev/null 2>&1 || fail "Preflight failed: docker daemon is unavailable"

    if [ ! -d "$BOT_DIR" ]; then
        fail "Preflight failed: environment directory not found: ${BOT_DIR}"
    fi

    if [ ! -f "$ENV_FILE" ]; then
        fail "Preflight failed: env file not found: ${ENV_FILE}"
    fi

    if [ -f "$GLOBAL_FREEZE_FILE" ]; then
        fail "Preflight failed: deploy freeze is active (${GLOBAL_FREEZE_FILE})"
    fi

    if [ -f "$ENV_FREEZE_FILE" ]; then
        fail "Preflight failed: deploy freeze is active for ${ENVIRONMENT} (${ENV_FREEZE_FILE})"
    fi

    check_required_env_keys
    check_expected_container_paths

    log "INFO" "Environment: ${ENVIRONMENT}"
    log "INFO" "Container: ${CONTAINER_NAME}"
    log "INFO" "Image: ${IMAGE}"
    log "INFO" "Run user (uid:gid): ${RUN_UID}:${RUN_GID}"
    log "INFO" "Restart policy: ${RESTART_POLICY}"
}

prepare_runtime_dirs() {
    mkdir -p "$DB_DIR" "$COOKIES_DIR" "$LOGS_DIR" "$TEMP_DIR"

    if [ ! -f "$COOKIES_FILE" ]; then
        touch "$COOKIES_FILE"
        log "INFO" "Created empty cookies file: ${COOKIES_FILE}"
    fi

    if [ ! -s "$COOKIES_FILE" ]; then
        log "WARN" "youtube_cookies.txt is empty: YouTube extraction may fail"
    fi
}

stop_and_remove_container() {
    if docker ps -a --format '{{.Names}}' | grep -Fxq "$CONTAINER_NAME"; then
        local is_running
        is_running="$(docker inspect -f '{{.State.Running}}' "$CONTAINER_NAME" 2>/dev/null || echo false)"

        if [ "$is_running" = "true" ]; then
            log "INFO" "Stopping container gracefully: ${CONTAINER_NAME}"
            if ! docker stop --time 25 "$CONTAINER_NAME" >/dev/null; then
                log "WARN" "Graceful stop failed for ${CONTAINER_NAME}, forcing removal"
            fi
        fi

        log "INFO" "Removing container: ${CONTAINER_NAME}"
        if ! docker rm "$CONTAINER_NAME" >/dev/null 2>&1; then
            docker rm -f "$CONTAINER_NAME" >/dev/null
        fi
    else
        log "INFO" "Container ${CONTAINER_NAME} not found, skipping stop"
    fi
}

cleanup_runtime_cache() {
    rm -rf "${BOT_DIR}/.cache" 2>/dev/null || true
    docker system prune -f >/dev/null 2>&1 || true
}

start_container() {
    local container_id
    local container_status

    log "INFO" "Starting container from image: ${IMAGE}"
    container_id="$(docker run -d \
        --name "$CONTAINER_NAME" \
        --user "${RUN_UID}:${RUN_GID}" \
        --restart "$RESTART_POLICY" \
        --env-file "$ENV_FILE" \
        -v "$DB_DIR":/app/src/data/db \
        -v "$COOKIES_DIR":/app/src/data/cookies:ro \
        -v "$TEMP_DIR":/app/src/data/temp_files \
        -v "$LOGS_DIR":/app/logs \
        "$IMAGE")"

    log "INFO" "Container created: ${container_id}"

    container_status="$(docker ps --filter "name=^/${CONTAINER_NAME}$" --format '{{.Status}}')"
    if [ -z "$container_status" ]; then
        fail "Container ${CONTAINER_NAME} is not running after docker run"
    fi

    log "INFO" "Container status: ${container_status}"
}

print_summary() {
    local script_end_ts
    local duration

    script_end_ts="$(date +%s)"
    duration="$((script_end_ts - SCRIPT_START_TS))"

    CURRENT_STEP="summary"
    log "INFO" "Deploy finished successfully"
    log "INFO" "Environment: ${ENVIRONMENT}"
    log "INFO" "Container: ${CONTAINER_NAME}"
    log "INFO" "Image: ${IMAGE}"
    log "INFO" "Deploy log: ${LOG_FILE}"
    log "INFO" "Duration: ${duration} sec."
}

main() {
    configure_environment

    run_step "acquire-lock" acquire_deploy_lock
    run_step "preflight" preflight
    run_step "prepare-runtime" prepare_runtime_dirs
    run_step "stop-container" stop_and_remove_container
    run_step "cleanup-cache" cleanup_runtime_cache
    run_step "start-container" start_container

    print_summary
}

main "$@"
