@echo off
echo ========================================================
echo Starting UmaCore Bot (Discord Bot + PostgreSQL Database)
echo ========================================================
echo Checking Docker status...
docker info >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Docker is not running!
    echo Please launch Docker Desktop first and wait until it is fully started.
    echo.
    pause
    exit /b 1
)

echo Starting containers with Docker Compose...
docker compose -f docker-compose.prod.yml up -d --build
if %errorlevel% neq 0 (
    echo [ERROR] Failed to start containers. Please check the error message above.
    echo.
    pause
    exit /b 1
)

echo.
echo ========================================================
echo [SUCCESS] UmaCore Bot is now running in the background!
echo You can safely minimize or close this window.
echo ========================================================
pause