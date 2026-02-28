#!/bin/bash
if [ -z "$1" ]; then
    echo "Usage: $0 {prod|dev}"
    exit 1
fi
ENV="$1"

if [ "$ENV" == "prod" ]; then
    BOT_DIR="$HOME/bot_prod"
    CONTAINER_NAME="DJgurda-prod"
    IMAGE="ghcr.io/duby67/djgurda:latest"
elif [ "$ENV" == "dev" ]; then
    BOT_DIR="$HOME/bot_dev"
    CONTAINER_NAME="DJgurda-dev"
    IMAGE="ghcr.io/duby67/djgurda:dev-latest"
else
    echo "Invalid environment: $ENV."
    exit 1
fi
ENV_FILE="$BOT_DIR/.env"

echo "Deploying $ENV environment: container=$CONTAINER_NAME, image=$IMAGE"


docker stop "$CONTAINER_NAME" 2>/dev/null || true
docker rm "$CONTAINER_NAME" 2>/dev/null || true

rm -rf "$HOME"/.cache 2>/dev/null || true
rm -rf "$HOME"/.lesshst 2>/dev/null || true
rm -rf "$HOME"/.bash_history 2>/dev/null || true

rm -rf "$BOT_DIR"/.cache 2>/dev/null || true
rm -rf "$BOT_DIR"/.lesshst 2>/dev/null || true
rm -rf "$BOT_DIR"/.bash_history 2>/dev/null || true

docker run -d \
  --name "$CONTAINER_NAME" \
  --restart always \
  --env-file "$ENV_FILE" \
  "$IMAGE"