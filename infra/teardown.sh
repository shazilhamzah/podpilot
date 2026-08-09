#!/usr/bin/env bash
# =============================================================================
# PodPilot — Infrastructure Teardown
# Ticket: 01 — Provision Core Azure Infrastructure
#
# Deletes ALL resources created by infra/provision.sh.
# Intended for dev/CI environments only.
#
# Usage:
#   chmod +x infra/teardown.sh
#   ./infra/teardown.sh
#
# Requires confirmation unless PODPILOT_FORCE_TEARDOWN=1 is set.
# =============================================================================

set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
info()    { echo -e "${CYAN}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
die()     { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }

OUTPUTS_FILE="$(dirname "$0")/.infra-outputs"
[[ -f "$OUTPUTS_FILE" ]] && source "$OUTPUTS_FILE"

RESOURCE_GROUP="${RESOURCE_GROUP:-rg-podpilot}"

echo ""
echo -e "${RED}⚠️  PodPilot Infrastructure Teardown${NC}"
echo -e "${RED}======================================${NC}"
echo ""
warn "This will permanently delete resource group '${RESOURCE_GROUP}' and ALL resources inside it:"
echo "  - AKS cluster"
echo "  - Azure Cosmos DB for MongoDB account"
echo "  - All associated networking and storage"
echo ""

if [[ "${PODPILOT_FORCE_TEARDOWN:-0}" != "1" ]]; then
    read -r -p "  Type the resource group name to confirm deletion: " CONFIRM
    if [[ "$CONFIRM" != "$RESOURCE_GROUP" ]]; then
        die "Confirmation did not match. Aborting."
    fi
fi

az account show >/dev/null 2>&1 || die "Not logged in to Azure. Run: az login"

info "Deleting resource group '${RESOURCE_GROUP}' (this may take several minutes)..."

az group delete \
    --name "$RESOURCE_GROUP" \
    --yes \
    --no-wait \
    --output none

# Remove the local outputs file
if [[ -f "$OUTPUTS_FILE" ]]; then
    rm -f "$OUTPUTS_FILE"
    info "Removed ${OUTPUTS_FILE}"
fi

echo ""
success "Deletion initiated for resource group '${RESOURCE_GROUP}'."
info "Azure is deleting resources in the background — this typically takes 5–10 minutes."
info "Check progress with: az group show --name ${RESOURCE_GROUP} --query properties.provisioningState"
echo ""
