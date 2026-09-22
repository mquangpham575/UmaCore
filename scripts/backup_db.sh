#!/usr/bin/env bash
set -euo pipefail

# Automated off-VM backup for UmaCore's production Postgres database.
#
# Why this exists: on 2026-09-22 the production VM's disk was replaced during an
# unrelated terraform apply (for a co-located project), wiping the database with
# zero backups anywhere. Recovery took hours of manual reconstruction from Discord
# message history. This script keeps a rolling set of real backups OFF the VM
# entirely (on this machine), so a repeat of that incident is a five-minute
# `gunzip | psql` restore instead of hours of manual work.
#
# Run manually any time, or on a schedule. Safe to run repeatedly - each run is a
# fresh timestamped dump.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
BACKUP_DIR="$REPO_DIR/backups"
SSH_KEY="$REPO_DIR/.ssh/umacore_key"
VM_HOST="20.212.105.13"
VM_USER="umacore"
KEEP=14   # how many daily backups to retain locally

mkdir -p "$BACKUP_DIR"

TIMESTAMP="$(date -u +%Y%m%d_%H%M%S)"
REMOTE_TMP="/tmp/umacore_backup_${TIMESTAMP}.sql.gz"
LOCAL_FILE="$BACKUP_DIR/umacore_${TIMESTAMP}.sql.gz"

echo "[1/3] Dumping production database on the VM..."
ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=15 "${VM_USER}@${VM_HOST}" \
  "sudo docker exec umacore-postgres pg_dump -U umacore -d umacore | gzip > ${REMOTE_TMP} && sudo chown ${VM_USER}:${VM_USER} ${REMOTE_TMP}"

echo "[2/3] Copying backup off the VM to $LOCAL_FILE ..."
scp -i "$SSH_KEY" -o StrictHostKeyChecking=no "${VM_USER}@${VM_HOST}:${REMOTE_TMP}" "$LOCAL_FILE"

echo "[3/3] Cleaning up remote temp file..."
ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "${VM_USER}@${VM_HOST}" "rm -f ${REMOTE_TMP}"

SIZE="$(du -h "$LOCAL_FILE" | cut -f1)"
echo "Backup saved: $LOCAL_FILE ($SIZE)"

# Rotate: keep only the most recent $KEEP backups
cd "$BACKUP_DIR"
ls -1t umacore_*.sql.gz 2>/dev/null | tail -n +$((KEEP + 1)) | xargs -r rm -f
COUNT="$(ls -1 umacore_*.sql.gz 2>/dev/null | wc -l)"
echo "Backups retained: $COUNT (keeping last $KEEP)"
