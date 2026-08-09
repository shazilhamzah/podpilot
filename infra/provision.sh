#!/usr/bin/env bash
# =============================================================================
# PodPilot — Core Azure Infrastructure Provisioning
# Ticket: 01 — Provision Core Azure Infrastructure
#
# Provisions:
#   - Azure resource group
#   - AKS cluster (OIDC issuer + Workload Identity + Cost Analysis / OpenCost)
#   - Azure Cosmos DB for MongoDB account + podpilot database
#
# Usage:
#   chmod +x infra/provision.sh
#   ./infra/provision.sh
#
# Idempotent: safe to re-run — existing resources are detected and skipped.
# =============================================================================

set -euo pipefail

# ── Colour helpers ────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
info()    { echo -e "${CYAN}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
die()     { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }

# ── Configuration — override via environment variables ────────────────────────
RESOURCE_GROUP="${RESOURCE_GROUP:-rg-podpilot}"
CLUSTER_NAME="${CLUSTER_NAME:-aks-podpilot}"
COSMOS_ACCOUNT="${COSMOS_ACCOUNT:-podpilot-cosmos}"
COSMOS_DB_NAME="${COSMOS_DB_NAME:-podpilot}"
LOCATION="${LOCATION:-eastus}"
NODE_COUNT="${NODE_COUNT:-2}"
COSMOS_SERVER_VERSION="${COSMOS_SERVER_VERSION:-7.0}"

# ── Pre-flight checks ─────────────────────────────────────────────────────────
command -v az      >/dev/null 2>&1 || die "Azure CLI (az) is not installed. See https://docs.microsoft.com/cli/azure/install-azure-cli"
command -v kubectl >/dev/null 2>&1 || die "kubectl is not installed."

az account show >/dev/null 2>&1 || die "Not logged in to Azure. Run: az login"

SUBSCRIPTION_ID=$(az account show --query id -o tsv)
info "Using subscription: $(az account show --query name -o tsv) (${SUBSCRIPTION_ID})"
info "Deploying to region: ${LOCATION}"
echo ""

# ── 1. Resource Group ─────────────────────────────────────────────────────────
info "Step 1/5 — Resource group"

if az group show --name "$RESOURCE_GROUP" >/dev/null 2>&1; then
    warn "Resource group '${RESOURCE_GROUP}' already exists — skipping creation."
else
    az group create \
        --name "$RESOURCE_GROUP" \
        --location "$LOCATION" \
        --output none
    success "Resource group '${RESOURCE_GROUP}' created."
fi

# ── 2. AKS Cluster ────────────────────────────────────────────────────────────
info "Step 2/5 — AKS cluster (this may take 5–10 minutes)"

if az aks show --name "$CLUSTER_NAME" --resource-group "$RESOURCE_GROUP" >/dev/null 2>&1; then
    warn "AKS cluster '${CLUSTER_NAME}' already exists — skipping creation."
else
    az aks create \
        --resource-group "$RESOURCE_GROUP" \
        --name "$CLUSTER_NAME" \
        --node-count "$NODE_COUNT" \
        --enable-oidc-issuer \
        --enable-workload-identity \
        --enable-cost-analysis \
        --generate-ssh-keys \
        --output none
    success "AKS cluster '${CLUSTER_NAME}' created with ${NODE_COUNT} nodes."
fi

# ── 3. Kubeconfig ─────────────────────────────────────────────────────────────
info "Step 3/5 — Fetching kubeconfig"

az aks get-credentials \
    --resource-group "$RESOURCE_GROUP" \
    --name "$CLUSTER_NAME" \
    --overwrite-existing \
    --output none

success "Kubeconfig updated. Current context: $(kubectl config current-context)"

# ── 4. Cosmos DB Account ──────────────────────────────────────────────────────
info "Step 4/5 — Azure Cosmos DB for MongoDB account (this may take 3–5 minutes)"

if az cosmosdb show --name "$COSMOS_ACCOUNT" --resource-group "$RESOURCE_GROUP" >/dev/null 2>&1; then
    warn "Cosmos DB account '${COSMOS_ACCOUNT}' already exists — skipping creation."
else
    az cosmosdb create \
        --name "$COSMOS_ACCOUNT" \
        --resource-group "$RESOURCE_GROUP" \
        --locations "regionName=${LOCATION}" "failoverPriority=0" \
        --kind MongoDB \
        --server-version "$COSMOS_SERVER_VERSION" \
        --output none
    success "Cosmos DB account '${COSMOS_ACCOUNT}' created (MongoDB ${COSMOS_SERVER_VERSION})."
fi

# ── 5. Cosmos DB Database ─────────────────────────────────────────────────────
info "Step 5/5 — Cosmos DB database '${COSMOS_DB_NAME}'"

if az cosmosdb mongodb database show \
        --account-name "$COSMOS_ACCOUNT" \
        --resource-group "$RESOURCE_GROUP" \
        --name "$COSMOS_DB_NAME" >/dev/null 2>&1; then
    warn "Cosmos DB database '${COSMOS_DB_NAME}' already exists — skipping creation."
else
    az cosmosdb mongodb database create \
        --account-name "$COSMOS_ACCOUNT" \
        --resource-group "$RESOURCE_GROUP" \
        --name "$COSMOS_DB_NAME" \
        --output none
    success "Cosmos DB database '${COSMOS_DB_NAME}' created."
fi

# ── Output: connection string ─────────────────────────────────────────────────
echo ""
info "Retrieving Cosmos DB primary connection string..."

COSMOS_CONNECTION_STRING=$(az cosmosdb keys list \
    --name "$COSMOS_ACCOUNT" \
    --resource-group "$RESOURCE_GROUP" \
    --type connection-strings \
    --query "connectionStrings[0].connectionString" \
    -o tsv)

# Strip trailing whitespace / carriage returns
COSMOS_CONNECTION_STRING=$(echo "$COSMOS_CONNECTION_STRING" | tr -d '\r\n')

# Write to a local .infra-outputs file — add to .gitignore
OUTPUTS_FILE="$(dirname "$0")/.infra-outputs"
{
    echo "# Auto-generated by infra/provision.sh — DO NOT COMMIT"
    echo "RESOURCE_GROUP=${RESOURCE_GROUP}"
    echo "CLUSTER_NAME=${CLUSTER_NAME}"
    echo "COSMOS_ACCOUNT=${COSMOS_ACCOUNT}"
    echo "COSMOS_DB_NAME=${COSMOS_DB_NAME}"
    echo "LOCATION=${LOCATION}"
    echo "SUBSCRIPTION_ID=${SUBSCRIPTION_ID}"
    echo "MONGO_DB_URI=${COSMOS_CONNECTION_STRING}"
} > "$OUTPUTS_FILE"

chmod 600 "$OUTPUTS_FILE"

echo ""
echo -e "${GREEN}════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}✅  Core Azure infrastructure provisioned successfully!${NC}"
echo -e "${GREEN}════════════════════════════════════════════════════════════${NC}"
echo ""
echo "  Resource group : ${RESOURCE_GROUP}"
echo "  AKS cluster    : ${CLUSTER_NAME} (${NODE_COUNT} nodes)"
echo "  Cosmos DB      : ${COSMOS_ACCOUNT}/${COSMOS_DB_NAME} (MongoDB ${COSMOS_SERVER_VERSION})"
echo ""
echo "  🔐 Connection string written to: ${OUTPUTS_FILE}"
echo "     (chmod 600 — keep this file out of git)"
echo ""
echo "  Next steps:"
echo "    1. Run ./infra/verify.sh to validate all acceptance criteria"
echo "    2. Proceed to ticket 02 (Azure OpenAI + Workload Identity)"
echo ""
