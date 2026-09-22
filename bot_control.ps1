# =============================================================================
# bot_control.ps1 - Command center for UmaCore Bot management
# =============================================================================

param (
    [Parameter(Mandatory=$true)]
    [ValidateSet("sync-all", "check-schedule", "set-schedule-all")]
    [string]$Action,

    [Parameter(Mandatory=$false)]
    [string]$Identifier
)

$SSH_KEY = ".ssh\umacore_key"
$IP = "20.212.105.13"
$User = "umacore"
$Container = "umacore-bot"
$DB_Container = "umacore-postgres"

switch ($Action) {
    "check-schedule" {
        Write-Host "📅 Fetching schedule update times for all clubs..." -ForegroundColor Cyan
        ssh -i $SSH_KEY "$User@$IP" "docker exec $DB_Container psql -U umacore -c 'SELECT club_name, scrape_time FROM clubs ORDER BY club_name;'"
    }
    "sync-all" {
        Write-Host "🔄 Triggering full club sync with raw data on Azure VM..." -ForegroundColor Cyan
        ssh -i $SSH_KEY "$User@$IP" "docker exec -t $Container python utils/scrape_all_clubs.py"
        Write-Host "✅ Sync process finished." -ForegroundColor Green
    }
    "set-schedule-all" {
        if (-not $Identifier) {
            Write-Host "❌ Error: set-schedule-all requires a time (HH:MM)." -ForegroundColor Red
            Write-Host "Usage: .\bot_control.ps1 set-schedule-all '10:02'" -ForegroundColor Gray
            return
        }
        Write-Host "🕒 Updating schedule for ALL clubs to $Identifier UTC on Azure VM..." -ForegroundColor Yellow
        $Query = "UPDATE clubs SET scrape_time = '$Identifier', timezone = 'UTC', updated_at = NOW();"
        echo $Query | ssh -i $SSH_KEY "$User@$IP" "docker exec -i $DB_Container psql -U umacore"
        Write-Host "✅ Global schedule update finished." -ForegroundColor Green
    }
}
