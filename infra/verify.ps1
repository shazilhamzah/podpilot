# =============================================================================
# PodPilot - Infrastructure Verification
# Ticket: 01 - Provision Core Azure Infrastructure
#
# Asserts every acceptance criterion in the ticket.
# Exits with code 0 only when all checks pass.
#
# Usage:
#   .\infra\verify.ps1
#
# Sources infra/.infra-outputs.ps1 for connection details if present.
# =============================================================================

#Requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = "SilentlyContinue"

$PassCount = 0
$FailCount = 0

function Write-Pass    { param($Msg) Write-Host "  [PASS]  $Msg" -ForegroundColor Green;  $script:PassCount++ }
function Write-Fail    { param($Msg) Write-Host "  [FAIL]  $Msg" -ForegroundColor Red;    $script:FailCount++ }
function Write-Section { param($Msg) Write-Host ""; Write-Host "-- $Msg" -ForegroundColor Cyan }

# ── Load outputs from provision step ─────────────────────────────────────────
$OutputsFile = Join-Path $PSScriptRoot ".infra-outputs.ps1"
if (Test-Path $OutputsFile) {
    . $OutputsFile
}

$ResourceGroup = if ($env:RESOURCE_GROUP) { $env:RESOURCE_GROUP } else { "rg-podpilot" }
$ClusterName   = if ($env:CLUSTER_NAME)   { $env:CLUSTER_NAME }   else { "aks-podpilot" }
$CosmosAccount = if ($env:COSMOS_ACCOUNT) { $env:COSMOS_ACCOUNT } else { "podpilot-cosmos" }
$CosmosDbName  = if ($env:COSMOS_DB_NAME) { $env:COSMOS_DB_NAME } else { "podpilot" }

Write-Host ""
Write-Host "PodPilot - Ticket 01 Infrastructure Verification" -ForegroundColor Cyan
Write-Host "===================================================" -ForegroundColor Cyan

# ── Pre-flight ────────────────────────────────────────────────────────────────
Write-Section "Pre-flight"

if (Get-Command az -ErrorAction SilentlyContinue) {
    Write-Pass "Azure CLI is installed"
} else {
    Write-Host "[ERROR] Azure CLI not found - cannot continue." -ForegroundColor Red
    exit 1
}

if (Get-Command kubectl -ErrorAction SilentlyContinue) {
    Write-Pass "kubectl is installed"
} else {
    Write-Host "[ERROR] kubectl not found - cannot continue." -ForegroundColor Red
    exit 1
}

$null = az account show 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Pass "Azure CLI is authenticated"
} else {
    Write-Host "[ERROR] Not logged in - run: az login" -ForegroundColor Red
    exit 1
}

# ── Criterion 1: Resource group ───────────────────────────────────────────────
Write-Section "Criterion 1 - Resource group exists"

$rgState = az group show --name $ResourceGroup --query "properties.provisioningState" -o tsv 2>&1
if ($LASTEXITCODE -eq 0 -and $rgState -eq "Succeeded") {
    Write-Pass "Resource group '$ResourceGroup' exists and is Succeeded"
} else {
    Write-Fail "Resource group '$ResourceGroup' not found or not ready (state: $rgState)"
}

# ── Criterion 2: AKS cluster flags ───────────────────────────────────────────
Write-Section "Criterion 2 - AKS cluster flags"

$aksRaw = az aks show --name $ClusterName --resource-group $ResourceGroup 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Fail "AKS cluster '$ClusterName' not found - run provision.ps1 first"
    Write-Fail "OIDC issuer flag not verifiable - cluster missing"
    Write-Fail "Workload Identity flag not verifiable - cluster missing"
    Write-Fail "Cost Analysis flag not verifiable - cluster missing"
} else {
    $aks = $aksRaw | ConvertFrom-Json

    if ($aks.oidcIssuerProfile.enabled -eq $true) {
        Write-Pass "OIDC issuer enabled"
    } else {
        Write-Fail "OIDC issuer NOT enabled (needs --enable-oidc-issuer)"
    }

    if ($aks.securityProfile.workloadIdentity.enabled -eq $true) {
        Write-Pass "Workload Identity enabled"
    } else {
        Write-Fail "Workload Identity NOT enabled (needs --enable-workload-identity)"
    }

    $caAddon = $aks.addonProfiles.PSObject.Properties["costAnalysis"]
    if ($caAddon -and $caAddon.Value.enabled -eq $true) {
        Write-Pass "Cost Analysis add-on enabled"
    } else {
        Write-Fail "Cost Analysis add-on NOT enabled (needs --enable-cost-analysis)"
    }
}

# ── Criterion 3: kubectl get nodes ───────────────────────────────────────────
Write-Section "Criterion 3 - kubectl get nodes (at least 2 Ready)"

$nodesRaw   = kubectl get nodes --no-headers 2>&1
$readyCount = ($nodesRaw | Where-Object { $_ -match "\sReady\s" }).Count

if ($readyCount -ge 2) {
    Write-Pass "$readyCount node(s) in Ready state"
} else {
    Write-Fail "Only $readyCount node(s) Ready - expected at least 2"
}

# ── Criterion 4a: OpenCost pods ───────────────────────────────────────────────
Write-Section "Criterion 4a - OpenCost pods running"

$opencostPods = kubectl get pods -n kube-system -l app=opencost --no-headers 2>&1
$runningCount = ($opencostPods | Where-Object { $_ -match "Running" }).Count

if ($runningCount -ge 1) {
    Write-Pass "$runningCount OpenCost pod(s) running in kube-system"
} else {
    Write-Fail "No OpenCost pods found running in kube-system"
}

# ── Criterion 4b: OpenCost HTTP probe ─────────────────────────────────────────
Write-Section "Criterion 4b - OpenCost allocation endpoint responds"

$pfJob = Start-Job -ScriptBlock {
    kubectl port-forward -n kube-system svc/opencost 19090:9090 2>&1 | Out-Null
}
Start-Sleep -Seconds 4

try {
    $response = Invoke-WebRequest `
        -Uri "http://localhost:19090/allocation/compute?window=1d&aggregate=pod&accumulate=false" `
        -TimeoutSec 5 `
        -UseBasicParsing `
        -ErrorAction Stop
    if ($response.StatusCode -eq 200) {
        Write-Pass "OpenCost allocation endpoint returned HTTP 200"
    } else {
        Write-Fail "OpenCost allocation endpoint returned HTTP $($response.StatusCode)"
    }
} catch {
    Write-Fail "OpenCost allocation endpoint unreachable: $($_.Exception.Message)"
} finally {
    Stop-Job   $pfJob -ErrorAction SilentlyContinue
    Remove-Job $pfJob -ErrorAction SilentlyContinue
}

# ── Criterion 5: Cosmos DB account ───────────────────────────────────────────
Write-Section "Criterion 5 - Cosmos DB for MongoDB account"

$cosmosRaw = az cosmosdb show --name $CosmosAccount --resource-group $ResourceGroup 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Fail "Cosmos DB account '$CosmosAccount' not found"
    Write-Fail "Cosmos DB version not verifiable - account missing"
} else {
    $cosmos = $cosmosRaw | ConvertFrom-Json

    if ($cosmos.kind -eq "MongoDB") {
        Write-Pass "Cosmos DB kind is MongoDB"
    } else {
        Write-Fail "Cosmos DB kind is '$($cosmos.kind)' (expected MongoDB)"
    }

    if ($cosmos.apiProperties.serverVersion -eq "7.0") {
        Write-Pass "Cosmos DB server version is 7.0"
    } else {
        Write-Fail "Cosmos DB server version is '$($cosmos.apiProperties.serverVersion)' (expected 7.0)"
    }
}

# ── Criterion 6: podpilot database ───────────────────────────────────────────
Write-Section "Criterion 6 - Cosmos DB 'podpilot' database exists"

$dbName = az cosmosdb mongodb database show `
    --account-name $CosmosAccount `
    --resource-group $ResourceGroup `
    --name $CosmosDbName `
    --query "name" -o tsv 2>&1

if ($LASTEXITCODE -eq 0 -and $dbName.Trim() -eq $CosmosDbName) {
    Write-Pass "Database '$CosmosDbName' exists in Cosmos DB account"
} else {
    Write-Fail "Database '$CosmosDbName' NOT found in Cosmos DB account"
}

# ── Criterion 7: connection string ────────────────────────────────────────────
Write-Section "Criterion 7 - Primary connection string available"

if (-not [string]::IsNullOrWhiteSpace($env:MONGO_DB_URI)) {
    Write-Pass "Connection string present in .infra-outputs.ps1"
} else {
    $liveUri = az cosmosdb keys list `
        --name $CosmosAccount `
        --resource-group $ResourceGroup `
        --type connection-strings `
        --query "connectionStrings[0].connectionString" `
        -o tsv 2>&1

    if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace($liveUri)) {
        Write-Pass "Connection string retrievable from Azure (run provision.ps1 to save it locally)"
    } else {
        Write-Fail "Could not retrieve Cosmos DB connection string"
    }
}

# ── Summary ───────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "==================================================" -ForegroundColor Cyan
if ($FailCount -eq 0) {
    Write-Host "  All $PassCount checks passed - ticket 01 is DONE" -ForegroundColor Green
    Write-Host "==================================================" -ForegroundColor Cyan
    Write-Host ""
    exit 0
} else {
    Write-Host "  $FailCount check(s) FAILED, $PassCount passed" -ForegroundColor Red
    Write-Host "==================================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  Re-run .\infra\provision.ps1 to fix missing resources,"
    Write-Host "  then run .\infra\verify.ps1 again."
    Write-Host ""
    exit 1
}
