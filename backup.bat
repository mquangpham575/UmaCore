@echo off
setlocal enabledelayedexpansion
title UmaCore Database Backup

echo ========================================================
echo   UmaCore - PostgreSQL Local Backup
echo ========================================================
echo.

:: 1. Verify Docker Daemon
docker info >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Docker is not running.
    echo Please start Docker Desktop and wait until it is ready.
    pause
    exit /b 1
)

:: 2. Ensure backups directory exists
if not exist "backups" mkdir backups

:: 3. Generate timestamp (YYYYMMDD_HHMMSS)
for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value 2^>nul') do set dt=%%I
if defined dt (
    set TIMESTAMP=%dt:~0,8%_%dt:~8,6%
) else (
    set TIMESTAMP=%date:~-4%%date:~4,2%%date:~7,2%_%time:~0,2%%time:~3,2%%time:~6,2%
    set TIMESTAMP=%TIMESTAMP: =0%
)

set BACKUP_FILE=backups\umacore_%TIMESTAMP%.sql

echo [*] Exporting database from umacore-postgres container...
docker exec umacore-postgres pg_dump -U umacore -d umacore > "%BACKUP_FILE%"
if errorlevel 1 (
    echo [ERROR] Backup failed. Is umacore-postgres container running?
    pause
    exit /b 1
)

echo.
echo [OK] Database backup completed successfully:
echo      %BACKUP_FILE%
echo ========================================================
echo.
pause
