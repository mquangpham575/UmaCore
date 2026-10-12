#!/usr/bin/env bash
echo "Streaming UmaCore Bot Live Logs (Press Ctrl+C to exit)..."
docker compose -f docker-compose.prod.yml logs -f umacore-bot