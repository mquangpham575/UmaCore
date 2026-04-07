# =============================================================================
# vm_control.ps1 - Start/Stop/Status for UmaCore VM on Azure
# =============================================================================

param (
    [Parameter(Mandatory=$true)]
    [ValidateSet("start", "stop", "status")]
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
}
