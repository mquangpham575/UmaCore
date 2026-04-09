# =============================================================================
# vm_control.ps1 - Start/Stop/Status for UmaCore VM on Azure
# =============================================================================

param (
    [Parameter(Mandatory=$true)]
    [ValidateSet("start", "stop", "status", "logs", "db", "deploy", "run-local", "local-logs")]
    [string]$Action
)

$RG = "rg-umacore"
$VM = "umacore-vm"

switch ($Action) {
    "start" {
        Write-Host "🚀 Starting VM: $VM in $RG..." -ForegroundColor Cyan
        az vm start --resource-group $RG --name $VM --no-wait
    }
    "stop" {
        Write-Host "🛑 Stopping (Deallocating) VM: $VM in $RG..." -ForegroundColor Yellow
        az vm deallocate --resource-group $RG --name $VM --no-wait
    }
    "status" {
        Write-Host "🔍 Checking Status for $VM..." -ForegroundColor Gray
        az vm get-instance-view --resource-group $RG --name $VM --query "instanceView.statuses[1].displayStatus" -o tsv
    }
    "deploy" {
        Write-Host "📦 Packaging and Syncing code to $VM..." -ForegroundColor Magenta
        $RemotePath = "/opt/umacore"
        $SSH_KEY = ".ssh\umacore_key"
        $IP = "20.212.105.13"
        $User = "umacore"

        # Create a temporary tarball excluding unnecessary files
        tar --exclude=./venv --exclude=./.git --exclude=./__pycache__ --exclude=./.env --exclude=./debug --exclude=./.ssh --exclude=./project.tar.gz -czf project.tar.gz .

        # Upload and deploy
        scp -i $SSH_KEY project.tar.gz "$User@$($IP):$RemotePath/"
        ssh -i $SSH_KEY "$User@$IP" "cd $RemotePath && tar -xzf project.tar.gz && rm project.tar.gz && docker compose -f docker-compose.prod.yml up -d --build"
        
        Remove-Item project.tar.gz
        Write-Host "✅ Deployment complete! Containers are restarting." -ForegroundColor Green
    }
    "run-local" {
        Write-Host "🏠 Running UmaCore locally with Docker..." -ForegroundColor Blue
        # Ensure .env exists
        if (-not (Test-Path .env)) {
            Write-Host "⚠️  .env file not found! Please create it from .env.example first." -ForegroundColor Red
            return
        }
        docker compose up -d --build
        Write-Host "🚀 Local bot started! Use './vm_control.ps1 local-logs' to see logs." -ForegroundColor Green
    }
    "local-logs" {
        docker compose logs -f umacore-bot
    }
    "logs" {
        Write-Host "📜 Fetching logs for umacore-bot..." -ForegroundColor Cyan
        ssh -i .ssh\umacore_key umacore@20.212.105.13 "docker logs -f umacore-bot"
    }
    "db" {
        Write-Host "🗄️ Connecting to PostgreSQL shell..." -ForegroundColor Blue
        ssh -i .ssh\umacore_key umacore@20.212.105.13 -t "docker exec -it umacore-postgres psql -U umacore"
    }
}
