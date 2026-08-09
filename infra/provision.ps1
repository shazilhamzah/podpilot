# =============================================================================
# PodPilot - Core Azure Infrastructure Provisioning
# Ticket: 01 - Provision Core Azure Infrastructure
#
# Provisions:
#   - Azure resource group
#   - AKS cluster (OIDC issuer + Workload Identity + Cost Analysis / OpenCost)
#   - Azure Cosmos DB for MongoDB account + podpilot database
#
# Usage:
#   .\infra\provision.ps1
#
# Idempotent: safe to re-run; existing resources are detected and skipped.
# Override any default via environment variables before running, e.g.:
#   $env:LOCATION = "westeurope"; .\infra\provision.ps1
# =============================================================================

#Requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Info { param($Msg) Write-Host "[INFO]  $Msg" -ForegroundColor Cyan   }
function Write-Ok   { param($Msg) Write-Host "[OK]    $Msg" -ForegroundColor Green  }
function Write-Warn { param($Msg) Write-Host "[WARN]  $Msg" -ForegroundColor Yellow }
function Write-Err  { param($Msg) Write-Host "[ERROR] $Msg" -ForegroundColor Red; exit 1 }

# ── Configuration ─────────────────────────────────────────────────────────────
$ResourceGroup       = if ($env:RESOURCE_GROUP)        { $env:RESOURCE_GROUP }        else { "rg-podpilot" }
$ClusterName         = if ($env:CLUSTER_NAME)          { $env:CLUSTER_NAME }          else { "aks-podpilot" }
$CosmosAccount       = if ($env:COSMOS_ACCOUNT)        { $env:COSMOS_ACCOUNT }        else { "podpilot-cosmos" }
$CosmosDbName        = if ($env:COSMOS_DB_NAME)        { $env:COSMOS_DB_NAME }        else { "podpilot" }
$Location            = if ($env:LOCATION)              { $env:LOCATION }              else { "eastus" }
$NodeCount           = if ($env:NODE_COUNT)            { $env:NODE_COUNT }            else { "2" }
$CosmosServerVersion = if ($env:COSMOS_SERVER_VERSION) { $env:COSMOS_SERVER_VERSION } else { "7.0" }

# ── Pre-flight checks ─────────────────────────────────────────────────────────
if (-not (Get-Command az      -ErrorAction SilentlyContinue)) {
    Write-Err "Azure CLI (az) not found. Install from https://aka.ms/installazurecliwindows"
}
if (-not (Get-Command kubectl -ErrorAction SilentlyContinue)) {
    Write-Err "kubectl not found. Install from https://kubernetes.io/docs/tasks/tools/install-kubectl-windows/"
}

$null = az account show 2>&1
if ($LASTEXITCODE -ne 0) { Write-Err "Not logged in to Azure. Run: az login" }

$SubscriptionId   = az account show --query id   -o tsv
$SubscriptionName = az account show --query name -o tsv

Write-Info "Using subscription: $SubscriptionName ($SubscriptionId)"
Write-Info "Deploying to region: $Location"
Write-Host ""

# ── 1. Resource Group ─────────────────────────────────────────────────────────
Write-Info "Step 1/5 - Resource group"

$null = az group show --name $ResourceGroup 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Warn "Resource group '$ResourceGroup' already exists - skipping creation."
} else {
    az group create --name $ResourceGroup --location $Location --output none
    Write-Ok "Resource group '$ResourceGroup' created."
}

# ── 2. AKS Cluster ────────────────────────────────────────────────────────────
Write-Info "Step 2/5 - AKS cluster (this may take 5-10 minutes)"

$null = az aks show --name $ClusterName --resource-group $ResourceGroup 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Warn "AKS cluster '$ClusterName' already exists - skipping creation."
} else {
    az aks create `
        --resource-group $ResourceGroup `
        --name $ClusterName `
        --node-count $NodeCount `
        --enable-oidc-issuer `
        --enable-workload-identity `
        --enable-cost-analysis `
        --generate-ssh-keys `
        --output none
    Write-Ok "AKS cluster '$ClusterName' created with $NodeCount nodes."
}

# ── 3. Kubeconfig ─────────────────────────────────────────────────────────────
Write-Info "Step 3/5 - Fetching kubeconfig"

az aks get-credentials `
    --resource-group $ResourceGroup `
    --name $ClusterName `
    --overwrite-existing `
    --output none

$CurrentContext = kubectl config current-context
Write-Ok "Kubeconfig updated. Current context: $CurrentContext"

# ── 4. Cosmos DB Account ──────────────────────────────────────────────────────
Write-Info "Step 4/5 - Azure Cosmos DB for MongoDB account (this may take 3-5 minutes)"

$null = az cosmosdb show --name $CosmosAccount --resource-group $ResourceGroup 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Warn "Cosmos DB account '$CosmosAccount' already exists - skipping creation."
} else {
    az cosmosdb create `
        --name $CosmosAccount `
        --resource-group $ResourceGroup `
        --locations "regionName=$Location" "failoverPriority=0" `
        --kind MongoDB `
        --server-version $CosmosServerVersion `
        --output none
    Write-Ok "Cosmos DB account '$CosmosAccount' created (MongoDB $CosmosServerVersion)."
}

# ── 5. Cosmos DB Database ─────────────────────────────────────────────────────
Write-Info "Step 5/5 - Cosmos DB database '$CosmosDbName'"

$null = az cosmosdb mongodb database show `
    --account-name $CosmosAccount `
    --resource-group $ResourceGroup `
    --name $CosmosDbName 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Warn "Cosmos DB database '$CosmosDbName' already exists - skipping creation."
} else {
    az cosmosdb mongodb database create `
        --account-name $CosmosAccount `
        --resource-group $ResourceGroup `
        --name $CosmosDbName `
        --output none
    Write-Ok "Cosmos DB database '$CosmosDbName' created."
}

# ── Output: connection string ─────────────────────────────────────────────────
Write-Host ""
Write-Info "Retrieving Cosmos DB primary connection string..."

$CosmosConnectionString = az cosmosdb keys list `
    --name $CosmosAccount `
    --resource-group $ResourceGroup `
    --type connection-strings `
    --query "connectionStrings[0].connectionString" `
    -o tsv

$CosmosConnectionString = $CosmosConnectionString.Trim()

# Write outputs file (gitignored - contains secrets)
$OutputsFile = Join-Path $PSScriptRoot ".infra-outputs.ps1"
$OutputsContent = @"
# Auto-generated by infra/provision.ps1 - DO NOT COMMIT
`$env:RESOURCE_GROUP       = "$ResourceGroup"
`$env:CLUSTER_NAME         = "$ClusterName"
`$env:COSMOS_ACCOUNT       = "$CosmosAccount"
`$env:COSMOS_DB_NAME       = "$CosmosDbName"
`$env:LOCATION             = "$Location"
`$env:SUBSCRIPTION_ID      = "$SubscriptionId"
`$env:MONGO_DB_URI         = "$CosmosConnectionString"
"@
Set-Content -Path $OutputsFile -Value $OutputsContent -Encoding UTF8

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  Core Azure infrastructure provisioned successfully!"        -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Resource group : $ResourceGroup"
Write-Host "  AKS cluster    : $ClusterName ($NodeCount nodes)"
Write-Host "  Cosmos DB      : $CosmosAccount/$CosmosDbName (MongoDB $CosmosServerVersion)"
Write-Host ""
Write-Host "  Connection string written to: $OutputsFile" -ForegroundColor Yellow
Write-Host "  (keep this file out of git - it is already in .gitignore)" -ForegroundColor Yellow
Write-Host ""
Write-Host "  Next steps:"
Write-Host "    1. Run .\infra\verify.ps1 to validate all acceptance criteria"
Write-Host "    2. Proceed to ticket 02 (Azure OpenAI + Workload Identity)"
Write-Host ""
