# =============================================================================
# bot_control.ps1 - Command center for UmaCore Bot management
# =============================================================================

param (
    [Parameter(Mandatory=$true)]
    [ValidateSet("sync-all", "db-reset", "db-reset-all")]
    [string]$Action,

    [Parameter(Mandatory=$false)]
    [string]$Identifier
)

$SSH_KEY = ".ssh\umacore_key"
$IP = "20.212.105.13"
$User = "umacore"
$Container = "umacore-bot"

switch ($Action) {
    "sync-all" {
        Write-Host "🔄 Triggering full club sync with raw data on Azure VM..." -ForegroundColor Cyan
        ssh -i $SSH_KEY "$User@$IP" "docker exec -t $Container python utils/scrape_all_clubs.py"
        Write-Host "✅ Sync process finished." -ForegroundColor Green
    }
    "db-reset" {
        if (-not $Identifier) {
            Write-Host "❌ Error: db-reset requires a club name or UUID." -ForegroundColor Red
            Write-Host "Usage: .\bot_control.ps1 db-reset 'ClubName'" -ForegroundColor Gray
            return
        }
        Write-Host "🧹 Resetting database data for club '$Identifier' on Azure VM..." -ForegroundColor Yellow
        ssh -i $SSH_KEY "$User@$IP" "docker exec -t $Container python utils/db_cleanup.py `"$Identifier`""
        Write-Host "✅ Club data reset finished." -ForegroundColor Green
    }
    "db-reset-all" {
        Write-Host "☢️  PERFORMING GLOBAL DATABASE RESET ON AZURE VM..." -ForegroundColor Red
        Write-Host "This will wipe ALL historical data for ALL clubs." -ForegroundColor Yellow
        $Confirmation = Read-Host "Are you absolutely sure? Type 'YES' to confirm"
        if ($Confirmation -eq 'YES') {
            ssh -i $SSH_KEY "$User@$IP" "docker exec -t $Container python utils/reset_all_data.py"
            Write-Host "✅ Global database reset complete." -ForegroundColor Green
        } else {
            Write-Host "❌ Reset aborted." -ForegroundColor Gray
        }
    }
}
