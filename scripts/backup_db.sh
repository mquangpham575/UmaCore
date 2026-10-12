#!/usr/bin/env bash
set -euo pipefail

# Automated / manual local backup for UmaCore's PostgreSQL database in Docker.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
BACKUP_DIR="$REPO_DIR/backups"
KEEP=4   # how many backups to retain locally

mkdir -p "$BACKUP_DIR"

TIMESTAMP="$(date -u +%Y%m%d_%H%M%S)"
LOCAL_FILE="$BACKUP_DIR/umacore_${TIMESTAMP}.sql.gz"

echo "[1/2] Dumping database from local Docker container (umacore-postgres)..."
docker exec umacore-postgres pg_dump -U umacore -d umacore | gzip > "$LOCAL_FILE"

SIZE="$(du -h "$LOCAL_FILE" | cut -f1)"
echo "[2/2] Backup saved: $LOCAL_FILE ($SIZE)"

# Rotate: keep only the most recent $KEEP backups
cd "$BACKUP_DIR"
ls -1t umacore_*.sql.gz 2>/dev/null | tail -n +$((KEEP + 1)) | xargs -r rm -f
COUNT="$(ls -1 umacore_*.sql.gz 2>/dev/null | wc -l)"
echo "Backups retained: $COUNT (keeping last $KEEP)"
