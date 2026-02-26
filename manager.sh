#!/bin/bash
BOT_DIR="/home/DJgurda/bot"
ENV_FILE="$BOT_DIR/.env"

CONTAINER_NAME="DJgurda"
IMAGE="ghcr.io/duby67/djgurda:latest"

docker stop "$CONTAINER_NAME" 2>/dev/null || true
docker rm "$CONTAINER_NAME" 2>/dev/null || true

rm -rf "$BOT_DIR"/.cache
rm -rf "$BOT_DIR"/.lesshst
rm -rf "$BOT_DIR"/.bash_history

docker run -d \
  --name "$CONTAINER_NAME" \
  --restart always \
  --env-file "$ENV_FILE" \
  "$IMAGE"
