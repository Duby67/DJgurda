#!/bin/bash

# Выход при ошибках
set -e  

if [ -z "$1" ]; then
    echo "Usage: $0 {prod|dev}"
    exit 1
fi

ENV="$1"
LOG_FILE="/tmp/djgurda_deploy_${ENV}.log"
REQUIRED_ENV_KEYS=(
  "ADMIN_ID"
  "BOT_VERSION"
  "BOT_DB_PATH"
  "BOT_TOKEN"
  "YANDEX_MUSIC_TOKEN"
  "YOUTUBE_COOKIES_PATH"
)

{
    echo "=== DJgurda Deploy Started: $(date) ==="
    echo "Environment: $ENV"
    
    if [ "$ENV" == "prod" ]; then
        BOT_DIR="$HOME/bot_prod"
        CONTAINER_NAME="DJgurda-prod"
        IMAGE="ghcr.io/duby67/djgurda:latest"
        RESTART="always"
        DB_DIR="$HOME/bot_prod/data/db"
        COOKIES_DIR="$HOME/bot_prod/data/cookies"
        LOGS_DIR="$HOME/bot_prod/logs"

    elif [ "$ENV" == "dev" ]; then
        BOT_DIR="$HOME/bot_dev" 
        CONTAINER_NAME="DJgurda-dev"
        IMAGE="ghcr.io/duby67/djgurda:dev-latest"
        RESTART="unless-stopped"
        DB_DIR="$HOME/bot_dev/data/db"
        COOKIES_DIR="$HOME/bot_dev/data/cookies"
        LOGS_DIR="$HOME/bot_dev/logs"
        
    else
        echo "Invalid environment: $ENV"
        exit 1
    fi

    ENV_FILE="$BOT_DIR/.env"
    
    # Проверка существования .env файла
    if [ ! -f "$ENV_FILE" ]; then
        echo "ERROR: .env file not found: $ENV_FILE"
        exit 1
    fi
    
    echo "Validating required environment keys..."
    for key in "${REQUIRED_ENV_KEYS[@]}"; do
        if ! grep -q "^${key}=" "$ENV_FILE"; then
            echo "ERROR: Missing required key in $ENV_FILE: ${key}"
            exit 1
        fi
    done

    echo "Stopping existing container..."
    docker stop "$CONTAINER_NAME" 2>/dev/null || true
    docker rm "$CONTAINER_NAME" 2>/dev/null || true

    echo "Cleaning cache..."
    rm -rf "$BOT_DIR"/.cache 2>/dev/null || true
    docker system prune -f 2>/dev/null || true

    echo "Creating runtime directories..."
    mkdir -p "$DB_DIR" "$COOKIES_DIR" "$LOGS_DIR"

    if [ ! -f "$COOKIES_DIR/youtube_cookies.txt" ]; then
        touch "$COOKIES_DIR/youtube_cookies.txt"
        echo "Created empty cookies file: $COOKIES_DIR/youtube_cookies.txt"
    fi

    if [ ! -s "$COOKIES_DIR/youtube_cookies.txt" ]; then
        echo "WARNING: youtube_cookies.txt is empty. YouTube extraction may fail."
    fi

    echo "Starting new container..."
    docker run -d \
        --name "$CONTAINER_NAME" \
        --restart "$RESTART" \
        --env-file "$ENV_FILE" \
        -v "$DB_DIR":/app/src/data/db \
        -v "$COOKIES_DIR":/app/src/data/cookies:ro \
        -v "$LOGS_DIR":/app/logs \
        "$IMAGE"

    echo "=== Deploy Completed: $(date) ==="
    echo "Container: $CONTAINER_NAME"
    echo "Image: $IMAGE"
    
} | tee "$LOG_FILE"

echo "Deploy log: $LOG_FILE"
