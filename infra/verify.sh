#!/usr/bin/env bash
# =============================================================================
# PodPilot — Infrastructure Verification
# Ticket: 01 — Provision Core Azure Infrastructure
#
# Asserts every acceptance criterion in the ticket.
# Exits 0 only when all checks pass.
#
# Usage:
#   chmod +x infra/verify.sh
#   ./infra/verify.sh
#
# Sources infra/.infra-outputs for connection details if present.
# All values can be overridden via environment variables.
# =============================================================================

set -uo pipefail

# ── Colour helpers ────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
PASS=0; FAIL=0

pass() { echo -e "  ${GREEN}✔${NC}  $*"; ((PASS+=1)); }
fail() { echo -e "  ${RED}✘${NC}  $*"; ((FAIL+=1)); }
section() { echo ""; echo -e "${CYAN}── $* ─────────────────────────────────────────${NC}"; }

# ── Load outputs from provision step ─────────────────────────────────────────
OUTPUTS_FILE="$(dirname "$0")/.infra-outputs"
if [[ -f "$OUTPUTS_FILE" ]]; then
    # shellcheck source=/dev/null
    source "$OUTPUTS_FILE"
fi

RESOURCE_GROUP="${RESOURCE_GROUP:-rg-podpilot}"
CLUSTER_NAME="${CLUSTER_NAME:-aks-podpilot}"
COSMOS_ACCOUNT="${COSMOS_ACCOUNT:-podpilot-cosmos}"
COSMOS_DB_NAME="${COSMOS_DB_NAME:-podpilot}"
LOCATION="${LOCATION:-eastus}"

echo ""
echo -e "${CYAN}PodPilot — Ticket 01 Infrastructure Verification${NC}"
echo -e "${CYAN}===================================================${NC}"

# ── Pre-flight ────────────────────────────────────────────────────────────────
section "Pre-flight"

command -v az      >/dev/null 2>&1 && pass "Azure CLI is installed" \
                                   || { fail "Azure CLI not found"; exit 1; }
command -v kubectl >/dev/null 2>&1 && pass "kubectl is installed" \
                                   || { fail "kubectl not found"; exit 1; }
az account show >/dev/null 2>&1    && pass "Azure CLI is authenticated" \
                                   || { fail "Not logged in — run: az login"; exit 1; }

# ── Criterion 1: Resource group ───────────────────────────────────────────────
section "Criterion 1 — Resource group exists"

if az group show --name "$RESOURCE_GROUP" --query "properties.provisioningState" -o tsv 2>/dev/null | grep -q "Succeeded"; then
    pass "Resource group '${RESOURCE_GROUP}' exists and is Succeeded"
else
    fail "Resource group '${RESOURCE_GROUP}' not found or not ready"
fi

# ── Criterion 2: AKS cluster flags ───────────────────────────────────────────
section "Criterion 2 — AKS cluster flags"

AKS_JSON=$(az aks show --name "$CLUSTER_NAME" --resource-group "$RESOURCE_GROUP" 2>/dev/null || echo "{}")

OIDC_ENABLED=$(echo "$AKS_JSON" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('oidcIssuerProfile',{}).get('enabled', False))" 2>/dev/null || echo "false")
WI_ENABLED=$(echo "$AKS_JSON"   | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('securityProfile',{}).get('workloadIdentity',{}).get('enabled', False))" 2>/dev/null || echo "false")
CA_ENABLED=$(echo "$AKS_JSON"   | python3 -c "import sys,json; d=json.load(sys.stdin); addons=d.get('addonProfiles',{}); print('costAnalysis' in addons and addons['costAnalysis'].get('enabled', False))" 2>/dev/null || echo "false")

[[ "$OIDC_ENABLED" == "True" ]]  && pass "OIDC issuer enabled"         || fail "OIDC issuer NOT enabled (--enable-oidc-issuer)"
[[ "$WI_ENABLED"   == "True" ]]  && pass "Workload Identity enabled"   || fail "Workload Identity NOT enabled (--enable-workload-identity)"
[[ "$CA_ENABLED"   == "True" ]]  && pass "Cost Analysis add-on enabled" || fail "Cost Analysis add-on NOT enabled (--enable-cost-analysis)"

# ── Criterion 3: kubectl get nodes ───────────────────────────────────────────
section "Criterion 3 — kubectl get nodes (at least 2 Ready)"

READY_NODES=$(kubectl get nodes --no-headers 2>/dev/null | grep -c " Ready" || echo 0)
if [[ "$READY_NODES" -ge 2 ]]; then
    pass "${READY_NODES} node(s) in Ready state"
else
    fail "Only ${READY_NODES} node(s) Ready — expected at least 2"
fi

# ── Criterion 4: OpenCost pods ────────────────────────────────────────────────
section "Criterion 4 — OpenCost pods running"

OPENCOST_RUNNING=$(kubectl get pods -n kube-system -l app=opencost --no-headers 2>/dev/null | grep -c "Running" || echo 0)
if [[ "$OPENCOST_RUNNING" -ge 1 ]]; then
    pass "${OPENCOST_RUNNING} OpenCost pod(s) running in kube-system"
else
    fail "No OpenCost pods found running in kube-system"
fi

# Quick HTTP check on allocation endpoint via port-forward (background)
section "Criterion 4b — OpenCost allocation endpoint responds"

# Start port-forward in background, give it 3 seconds, probe, then kill
kubectl port-forward -n kube-system svc/opencost 19090:9090 >/dev/null 2>&1 &
PF_PID=$!
sleep 3

HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
    "http://localhost:19090/allocation/compute?window=1d&aggregate=pod&accumulate=false" \
    --max-time 5 2>/dev/null || echo "000")

kill "$PF_PID" 2>/dev/null || true

if [[ "$HTTP_STATUS" == "200" ]]; then
    pass "OpenCost allocation endpoint returned HTTP 200"
else
    fail "OpenCost allocation endpoint returned HTTP ${HTTP_STATUS} (expected 200)"
fi

# ── Criterion 5: Cosmos DB account ───────────────────────────────────────────
section "Criterion 5 — Cosmos DB for MongoDB account"

COSMOS_KIND=$(az cosmosdb show \
    --name "$COSMOS_ACCOUNT" \
    --resource-group "$RESOURCE_GROUP" \
    --query "kind" -o tsv 2>/dev/null || echo "")

COSMOS_VER=$(az cosmosdb show \
    --name "$COSMOS_ACCOUNT" \
    --resource-group "$RESOURCE_GROUP" \
    --query "apiProperties.serverVersion" -o tsv 2>/dev/null || echo "")

[[ "$COSMOS_KIND" == "MongoDB" ]]   && pass "Cosmos DB kind is MongoDB"             || fail "Cosmos DB kind is '${COSMOS_KIND}' (expected MongoDB)"
[[ "$COSMOS_VER"  == "7.0"     ]]   && pass "Cosmos DB server version is 7.0"       || fail "Cosmos DB server version is '${COSMOS_VER}' (expected 7.0)"

# ── Criterion 6: podpilot database ───────────────────────────────────────────
section "Criterion 6 — Cosmos DB 'podpilot' database exists"

DB_EXISTS=$(az cosmosdb mongodb database show \
    --account-name "$COSMOS_ACCOUNT" \
    --resource-group "$RESOURCE_GROUP" \
    --name "$COSMOS_DB_NAME" \
    --query "name" -o tsv 2>/dev/null || echo "")

[[ "$DB_EXISTS" == "$COSMOS_DB_NAME" ]] \
    && pass "Database '${COSMOS_DB_NAME}' exists in Cosmos DB account" \
    || fail "Database '${COSMOS_DB_NAME}' NOT found in Cosmos DB account"

# ── Criterion 7: connection string documented ─────────────────────────────────
section "Criterion 7 — Primary connection string available"

if [[ -f "$OUTPUTS_FILE" ]] && grep -q "^MONGO_DB_URI=" "$OUTPUTS_FILE"; then
    CONN=$(grep "^MONGO_DB_URI=" "$OUTPUTS_FILE" | cut -d= -f2-)
    if [[ -n "$CONN" ]]; then
        pass "Connection string present in ${OUTPUTS_FILE}"
    else
        fail "MONGO_DB_URI key exists but value is empty in ${OUTPUTS_FILE}"
    fi
else
    # Try to fetch it live
    LIVE_CONN=$(az cosmosdb keys list \
        --name "$COSMOS_ACCOUNT" \
        --resource-group "$RESOURCE_GROUP" \
        --type connection-strings \
        --query "connectionStrings[0].connectionString" \
        -o tsv 2>/dev/null | tr -d '\r\n' || echo "")
    if [[ -n "$LIVE_CONN" ]]; then
        pass "Connection string retrievable from Azure (not yet saved to .infra-outputs)"
    else
        fail "Could not retrieve Cosmos DB connection string"
    fi
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo -e "${CYAN}══════════════════════════════════════════════════${NC}"
if [[ "$FAIL" -eq 0 ]]; then
    echo -e "${GREEN}✅  All ${PASS} checks passed — ticket 01 is DONE${NC}"
    echo -e "${CYAN}══════════════════════════════════════════════════${NC}"
    echo ""
    exit 0
else
    echo -e "${RED}❌  ${FAIL} check(s) FAILED, ${PASS} passed${NC}"
    echo -e "${CYAN}══════════════════════════════════════════════════${NC}"
    echo ""
    echo "  Re-run ./infra/provision.sh to fix missing resources,"
    echo "  then run ./infra/verify.sh again."
    echo ""
    exit 1
fi
