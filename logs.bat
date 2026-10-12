@echo off
echo ========================================================
echo Streaming UmaCore Bot Live Logs (Press Ctrl+C to exit)
echo ========================================================
docker compose -f docker-compose.prod.yml logs -f umacore-bot
pause