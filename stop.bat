@echo off
echo ========================================================
echo Stopping UmaCore Bot containers...
echo ========================================================
docker compose -f docker-compose.prod.yml down
echo.
echo [SUCCESS] UmaCore Bot has been stopped successfully.
pause