# =============================================================================
# PodPilot - Infrastructure Teardown
# Ticket: 01 - Provision Core Azure Infrastructure
#
# Deletes ALL resources created by infra/provision.ps1.
# Intended for dev/CI environments only.
#
# Usage:
#   .\infra\teardown.ps1
#
# Set $env:PODPILOT_FORCE_TEARDOWN = "1" to skip the confirmation prompt (CI).
# =============================================================================

#Requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ── Load outputs ──────────────────────────────────────────────────────────────
$OutputsFile = Join-Path $PSScriptRoot ".infra-outputs.ps1"
if (Test-Path $OutputsFile) {
    . $OutputsFile
}

$ResourceGroup = if ($env:RESOURCE_GROUP) { $env:RESOURCE_GROUP } else { "rg-podpilot" }

Write-Host ""
Write-Host "PodPilot Infrastructure Teardown" -ForegroundColor Red
Write-Host "=================================" -ForegroundColor Red
Write-Host ""
Write-Host "WARNING: This will permanently delete resource group '$ResourceGroup'" -ForegroundColor Yellow
Write-Host "and ALL resources inside it:" -ForegroundColor Yellow
Write-Host "  - AKS cluster"
Write-Host "  - Azure Cosmos DB for MongoDB account"
Write-Host "  - All associated networking and storage"
Write-Host ""

# ── Confirmation ──────────────────────────────────────────────────────────────
if ($env:PODPILOT_FORCE_TEARDOWN -ne "1") {
    $Confirm = Read-Host "Type the resource group name to confirm deletion"
    if ($Confirm -ne $ResourceGroup) {
        Write-Host "[ERROR] Confirmation did not match. Aborting." -ForegroundColor Red
        exit 1
    }
}

# ── Pre-flight ────────────────────────────────────────────────────────────────
az account show >$null 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Not logged in to Azure. Run: az login" -ForegroundColor Red
    exit 1
}

# ── Delete resource group ─────────────────────────────────────────────────────
Write-Host ""
Write-Host "[INFO]  Deleting resource group '$ResourceGroup' (this may take several minutes)..." -ForegroundColor Cyan

az group delete `
    --name $ResourceGroup `
    --yes `
    --no-wait `
    --output none

# ── Remove local outputs file ─────────────────────────────────────────────────
if (Test-Path $OutputsFile) {
    Remove-Item $OutputsFile -Force
    Write-Host "[INFO]  Removed $OutputsFile" -ForegroundColor Cyan
}

Write-Host ""
Write-Host "[OK]    Deletion initiated for resource group '$ResourceGroup'." -ForegroundColor Green
Write-Host "[INFO]  Azure is deleting resources in the background (typically 5-10 minutes)." -ForegroundColor Cyan
Write-Host "[INFO]  Check progress with:" -ForegroundColor Cyan
Write-Host "          az group show --name $ResourceGroup --query properties.provisioningState"
Write-Host ""
