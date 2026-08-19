#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

IMAGE_NAME="pick-a-meet:local"
CONTAINER_NAME="pick-a-meet-smoke"

docker build -t "$IMAGE_NAME" .
docker rm -f "$CONTAINER_NAME" 2>/dev/null || true
docker run -d \
  --name "$CONTAINER_NAME" \
  --network host \
  --env-file .env \
  "$IMAGE_NAME" \
  uvicorn app.main:app --host 0.0.0.0 --port 8001

echo "Pick a Meet is running at http://localhost:8001"
