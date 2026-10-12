#!/usr/bin/env bash
set -e

echo "========================================================"
echo "Starting UmaCore Bot (Discord Bot + PostgreSQL Database)"
echo "========================================================"

if ! docker info >/dev/null 2>&1; then
    echo "[ERROR] Docker daemon is not running! Please start Docker first."
    exit 1
fi

echo "Starting containers with Docker Compose..."
docker compose -f docker-compose.prod.yml up -d --build

echo ""
echo "========================================================"
echo "[SUCCESS] UmaCore Bot is now running in the background!"
echo "========================================================"