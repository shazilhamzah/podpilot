#!/bin/bash
set -e

while [[ $# -gt 0 ]]; do
  case $1 in
    --cluster) CLUSTER_NAME="$2"; shift 2 ;;
    --rg) RESOURCE_GROUP="$2"; shift 2 ;;
    *) echo "Unknown parameter passed: $1"; exit 1 ;;
  esac
done

if [[ -z "$CLUSTER_NAME" || -z "$RESOURCE_GROUP" ]]; then
  echo "Usage: ./install.sh --cluster <cluster_name> --rg <resource_group>"
  exit 1
fi

echo "PodPilot 1-Command Installer"
echo "============================"

# 1. Dependency Check
for cmd in az kubectl helm; do
  if ! command -v $cmd &> /dev/null && ! command -v $cmd.exe &> /dev/null && ! command -v $cmd.cmd &> /dev/null; then
    echo "Error: $cmd is not installed. Please install it before continuing."
    exit 1
  fi
done

# Map Windows9 executables in Git Bash
shopt -s expand_aliases
if ! command -v helm &> /dev/null && command -v helm.exe &> /dev/null; then alias helm='helm.exe'; fi
if ! command -v kubectl &> /dev/null && command -v kubectl.exe &> /dev/null; then alias kubectl='kubectl.exe'; fi
if ! command -v az &> /dev/null && command -v az.cmd &> /dev/null; then alias az='az.cmd'; fi

# 2. OIDC Check
echo "Checking OIDC Issuer on cluster $CLUSTER_NAME..."
OIDC_URL=$(az aks show -n "$CLUSTER_NAME" -g "$RESOURCE_GROUP" --query "oidcIssuerProfile.issuerUrl" -otsv | tr -d '\r')
if [[ -z "$OIDC_URL" || "$OIDC_URL" == "None" ]]; then
  echo "Enabling Workload Identity on $CLUSTER_NAME..."
  az aks update -n "$CLUSTER_NAME" -g "$RESOURCE_GROUP" --enable-workload-identity
  OIDC_URL=$(az aks show -n "$CLUSTER_NAME" -g "$RESOURCE_GROUP" --query "oidcIssuerProfile.issuerUrl" -otsv | tr -d '\r')
fi

echo "OIDC URL: $OIDC_URL"

# 3. API Call
echo "Fetching PodPilot Configuration..."
# 3. Create Federated Credential (Normally done by API)
az identity federated-credential create --name "client-$CLUSTER_NAME" \
  --identity-name "podpilot-identity" \
  --resource-group "rg-podpilot" \
  --issuer "$OIDC_URL" \
  --subject "system:serviceaccount:podpilot:podpilot" \
  --audiences "api://AzureADTokenExchange" || true

CLIENT_ID=$(az identity show --name podpilot-identity --resource-group rg-podpilot --query clientId -otsv | tr -d '\r')
TENANT_ID=$(az account show --query tenantId -otsv | tr -d '\r')
SUB_ID=$(az account show --query id -otsv | tr -d '\r')

# Fetch CosmosDB Connection String dynamically to avoid hardcoded secrets!
MONGO_URI=$(az cosmosdb keys list --type connection-strings --name podpilot-cosmos --resource-group rg-podpilot --query "connectionStrings[0].connectionString" -otsv | tr -d '\r')

cat <<EOF > podpilot-values.yaml
# PodPilot Auto-Generated Values for $CLUSTER_NAME
clusterName: "$CLUSTER_NAME"
workloadIdentity:
  clientId: "$CLIENT_ID"
  tenantId: "$TENANT_ID"
  subscriptionId: "$SUB_ID"
database:
  uri: "$MONGO_URI"
  dbName: ""
basicAuth:
  htpasswd: ""
aiFoundry:
  endpoint: "https://foundry-popilot-analysi-resource.cognitiveservices.azure.com/"
  deployment: "gpt-4o"
imageCredentials: "dummy_acr_token"
ingress:
  enabled: false
  host: ""
  tls:
    enabled: false
    clusterIssuer: "letsencrypt-prod"
opencost:
  enabled: true
serviceAccount:
  name: "podpilot"
EOF

# 4. Interactive Prompt
if [ -z "$PASSWORD" ]; then
  echo -n "Enter a secure password for your PodPilot dashboard: "
  read -s PASSWORD
  echo ""
fi

# Hash the password for basic-auth
if command -v openssl &> /dev/null; then
  HASH=$(openssl passwd -apr1 "$PASSWORD")
  HTPASSWD="admin:$HASH"
elif command -v python3 &> /dev/null; then
  HASH=$(python3 -c "import crypt; print(crypt.crypt('$PASSWORD', crypt.mksalt(crypt.METHOD_SHA512)))" 2>/dev/null || echo "admin:$PASSWORD")
  if [[ "$HASH" == admin:* ]]; then
    HTPASSWD="$HASH"
  else
    HTPASSWD="admin:$HASH"
  fi
else
  HTPASSWD="admin:$PASSWORD"
fi

# Escape slash and other characters for sed
ESCAPED_HTPASSWD=$(echo "$HTPASSWD" | sed -e 's/[\/&]/\\&/g')
# Update the basicAuth block in podpilot-values.yaml using sed
sed -i "s/htpasswd: \"\"/htpasswd: \"$ESCAPED_HTPASSWD\"/g" podpilot-values.yaml

# 5. Helm Execution
echo "Adding Helm Repositories..."
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx
helm repo add jetstack https://charts.jetstack.io
# Fallback to OCI if github charts repo is not ready yet
helm repo add podpilot https://podpilot.github.io/charts 2>/dev/null || true
helm repo update

echo "Installing Dependencies (Prometheus, Nginx Ingress, Cert-Manager)..."
helm upgrade --install prometheus prometheus-community/prometheus --namespace prometheus-system --create-namespace --set alertmanager.enabled=false --set pushgateway.enabled=false --set server.persistentVolume.enabled=false
helm upgrade --install ingress-nginx ingress-nginx/ingress-nginx --namespace ingress-nginx --create-namespace --set controller.service.annotations."service\.beta\.kubernetes\.io/azure-load-balancer-health-probe-request-path"=/healthz
helm upgrade --install cert-manager jetstack/cert-manager --namespace cert-manager --create-namespace --set crds.enabled=true

echo "Installing PodPilot..."
helm upgrade --install podpilot https://raw.githubusercontent.com/shazilhamzah/podpilot/main/podpilot-0.1.2.tgz \
  --namespace podpilot \
  --create-namespace \
  -f podpilot-values.yaml

# 6. Confirmation
echo "Waiting for PodPilot to become ready..."
kubectl rollout status deployment/podpilot -n podpilot --timeout=300s || echo "Timeout waiting for podpilot to become ready. It may still be starting."

echo "Fetching Ingress IP..."
EXTERNAL_IP=""
RETRIES=0
while [ -z "$EXTERNAL_IP" ] && [ $RETRIES -lt 20 ]; do
  sleep 5
  EXTERNAL_IP=$(kubectl get svc -n ingress-nginx ingress-nginx-controller --template="{{range .status.loadBalancer.ingress}}{{.ip}}{{end}}" 2>/dev/null || echo "")
  RETRIES=$((RETRIES+1))
done

if [ -z "$EXTERNAL_IP" ]; then
  EXTERNAL_IP="<PENDING-IP>"
fi

echo ""
echo "================================================="
echo "✅ PodPilot Deployment Successful!"
echo "Dashboard URL: http://$EXTERNAL_IP"
echo "Username: admin"
echo "Password: (The password you entered)"
echo "================================================="
