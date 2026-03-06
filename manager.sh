#!/bin/bash

# Выход при ошибках
set -e  

if [ -z "$1" ]; then
    echo "Usage: $0 {prod|dev}"
    exit 1
fi

ENV="$1"
LOG_FILE="/tmp/djgurda_deploy_${ENV}.log"

{
    echo "=== DJgurda Deploy Started: $(date) ==="
    echo "Environment: $ENV"
    
    if [ "$ENV" == "prod" ]; then
        BOT_DIR="$HOME/bot_prod"
        CONTAINER_NAME="DJgurda-prod"
        IMAGE="ghcr.io/duby67/djgurda:latest"
        RESTART="always"
        DB="$HOME/bot_prod/data"
    elif [ "$ENV" == "dev" ]; then
        BOT_DIR="$HOME/bot_dev" 
        CONTAINER_NAME="DJgurda-dev"
        IMAGE="ghcr.io/duby67/djgurda:dev-latest"
        RESTART="unless-stopped"
        DB="$HOME/bot_dev/data"
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

    echo "Stopping existing container..."
    docker stop "$CONTAINER_NAME" 2>/dev/null || true
    docker rm "$CONTAINER_NAME" 2>/dev/null || true

    echo "Cleaning cache..."
    rm -rf "$BOT_DIR"/.cache 2>/dev/null || true
    docker system prune -f 2>/dev/null || true

    echo "Creating data directory..."
    mkdir -p "$DB"

    echo "Starting new container..."
    docker run -d \
        --name "$CONTAINER_NAME" \
        --restart "$RESTART" \
        --env-file "$ENV_FILE" \
        -v "$DB":/app/src/data/db \
        -v "$BOT_DIR/logs":/app/logs \
        "$IMAGE"

    echo "=== Deploy Completed: $(date) ==="
    echo "Container: $CONTAINER_NAME"
    echo "Image: $IMAGE"
    
} | tee "$LOG_FILE"

echo "Deploy log: $LOG_FILE"
