# PodPilot — Client Cluster Onboarding Guide
### Deploy PodPilot into your Kubernetes cluster · Powered by our Foundry & Storage

---

> [!IMPORTANT]
> You do **not** need to provision any Azure resources. PodPilot's AI backend (Azure AI Foundry / gpt-4o) and snapshot storage (Azure Cosmos DB) are managed by us. You only need `kubectl` access to your own cluster.

---

## What you need from us first

Before you start, we will use Azure Workload Identity to securely connect your cluster to our backend without exchanging AI API keys. To set this up:

1. **You provide us:** Your cluster's OIDC Issuer URL (see Step 1 below).
2. **We provide you:** The Client ID and Tenant ID of our Managed Identity.

If your cluster does not support Azure Workload Identity, we can fallback to providing an `AZURE_OPENAI_API_KEY` and connection strings securely (e.g., via 1Password).

The endpoint and model name are already baked into the manifest — you don't need to know them.

---

## Prerequisites

| Tool | Min version | Install |
|------|-------------|---------|
| `kubectl` | 1.28+ | https://kubernetes.io/docs/tasks/tools/ |

Your `kubectl` must already be configured and pointed at your cluster.

**Cleaning up / resetting kubeconfig (if you have stale or conflicting configurations):**
* To delete a specific stale context:
  ```bash
  kubectl config delete-context <context-name>
  ```
* To completely reset and start fresh by deleting the configuration file:
  * **Windows (PowerShell):**
    ```powershell
    Remove-Item -Path "$HOME\.kube\config" -ErrorAction SilentlyContinue
    ```
  * **macOS / Linux:**
    ```bash
    rm -f ~/.kube/config
    ```

If you have not yet connected to your cluster, you can retrieve the access credentials and update your local kubeconfig:

**For Azure (AKS):**
```bash
az aks get-credentials --resource-group <resource-group-name> --name <cluster-name>
```

**Switching contexts (if multiple contexts exist):**
1. List all configured contexts:
   ```bash
   kubectl config get-contexts
   ```
2. Switch to the context for your target cluster:
   ```bash
   kubectl config use-context <context-name>
   ```

To verify that your CLI is successfully connected and authenticated to the target cluster, run:

```bash
kubectl cluster-info
# Should print your control plane URL — if it errors, fix this first.
```

No Helm or cloud provider account needed, but you must have permissions to manage your Kubernetes cluster settings.

---

## Step 1 — Enable Azure Workload Identity

Because PodPilot's AI and Storage backends reside in our tenant, we use **Cross-Tenant Azure Workload Identity** to grant your pods access securely without passing API keys.

1. **Enable the Workload Identity and OIDC features** on your AKS cluster:
   ```bash
   az aks update -n <cluster-name> -g <resource-group-name> --enable-workload-identity
   ```
2. **Retrieve your cluster's OIDC Issuer URL**:
   ```bash
   az aks show -n <cluster-name> -g <resource-group-name> --query "oidcIssuerProfile.issuerUrl" -otsv
   ```
3. **Send this URL to the PodPilot team.** We will configure our Managed Identity in our tenant to trust your cluster's OIDC issuer. We will then reply with our `Client ID` and `Tenant ID`.

---

---

## Step 2 — Apply the Manifest & Annotate ServiceAccount

Download and apply the all-in-one manifest. This will create the namespace and all required resources:

```bash
kubectl apply -f https://raw.githubusercontent.com/shazilhamzah/podpilot/main/k8s/podpilot.yaml
```

Expected output:

```
namespace/podpilot created
serviceaccount/podpilot created
...
```

Once the ServiceAccount is created, **annotate it** with the `Client ID` and `Tenant ID` provided by the PodPilot team. This tells the Azure Workload Identity webhook to fetch tokens for our tenant instead of yours:

```bash
kubectl annotate serviceaccount podpilot -n podpilot \
  azure.workload.identity/client-id="<CLIENT_ID_WE_SENT_YOU>" \
  azure.workload.identity/tenant-id="<TENANT_ID_WE_SENT_YOU>"
```

---

## Step 3 — Create the Secret

This is the **only** place you put the credentials we sent you (if any). Never commit this to git. 
*(If you are fully passwordless via Workload Identity, you may omit the AI_API_KEY depending on how we set up your database).*

**For macOS / Linux (Bash/Zsh):**

```bash
kubectl delete secret podpilot-secrets -n podpilot --ignore-not-found

kubectl create secret generic podpilot-secrets \
  --namespace podpilot \
  --from-literal=AZURE_OPENAI_ENDPOINT="https://foundry-popilot-analysi-resource.openai.azure.com/" \
  --from-literal=AZURE_OPENAI_DEPLOYMENT="gpt-4o" \
  --from-literal=CLUSTER_NAME="<your-cluster-name>" \
  --from-literal=MONGO_DB_URI="<MONGO_DB_URI_PROVIDED_BY_PODPILOT_TEAM>"
```

**For Windows (PowerShell):**

```powershell
kubectl delete secret podpilot-secrets -n podpilot --ignore-not-found

kubectl create secret generic podpilot-secrets `
  --namespace podpilot `
  --from-literal=AZURE_OPENAI_ENDPOINT="https://foundry-popilot-analysi-resource.openai.azure.com/" `
  --from-literal=AZURE_OPENAI_DEPLOYMENT="gpt-4o" `
  --from-literal=CLUSTER_NAME="<your-cluster-name>" `
  --from-literal=MONGO_DB_URI="<MONGO_DB_URI_PROVIDED_BY_PODPILOT_TEAM>"
```

> [!TIP]
> Set `CLUSTER_NAME` to something descriptive like `"acme-prod-eastus"` — it shows up in the PodPilot UI header so we can identify your cluster in support calls.

Confirm the secret was created:

```bash
kubectl get secret podpilot-secrets -n podpilot
# NAME                TYPE     DATA   AGE
# podpilot-secrets    Opaque   5      5s
```

> [!NOTE]
> The manifest **does not** contain any credentials — they come entirely from this Secret.

After adding the secret, restart the deployment so it picks up the credentials:

```bash
kubectl rollout restart deployment/podpilot -n podpilot
```

---

## Step 4 — Wait for the Pod to Come Up

```bash
kubectl rollout status deployment/podpilot -n podpilot --timeout=120s
```

```
deployment "podpilot" successfully rolled out
```

If it takes more than 2 minutes, jump to [Troubleshooting](#troubleshooting).

---

## Step 5 — Access the Dashboard

### Option A — LoadBalancer (AKS / EKS / GKE)

```bash
kubectl get svc podpilot -n podpilot
```

```
NAME        TYPE           CLUSTER-IP     EXTERNAL-IP      PORT(S)        AGE
podpilot    LoadBalancer   10.0.152.201   52.168.45.123    80:31204/TCP   2m
```

Wait until `EXTERNAL-IP` shows a real IP (may take 1–2 min), then open `http://<EXTERNAL-IP>` in your browser.

### Option B — Port Forward (any cluster, no public IP needed)

```bash
kubectl port-forward -n podpilot svc/podpilot 8080:80
```

Then open `http://localhost:8080`.

### Quick health check

```bash
curl http://<EXTERNAL-IP>/api/status
# {"status": "ok", "cluster": "your-cluster-name"}
```

---

## What PodPilot can and cannot do in your cluster

PodPilot runs under a dedicated `ServiceAccount` with a `ClusterRole` that grants **strictly read-only** access:

| Permission | Granted? |
|---|---|
| View pods, nodes, events, services, namespaces | ✅ |
| View deployments, statefulsets, daemonsets, jobs | ✅ |
| View resource quotas and PVCs | ✅ |
| Read metrics (CPU / memory via metrics-server) | ✅ |
| **Create, delete, or modify anything** | ❌ Never |
| **Access secrets or configmaps** | ❌ Never |

You can inspect the exact rules yourself:

```bash
kubectl describe clusterrole podpilot-reader
```

---

## Troubleshooting

### Pod stuck in `Pending`

```bash
kubectl describe pod -n podpilot -l app=podpilot | grep -A 10 Events
```

- **Insufficient resources** — your cluster nodes are full. Free up resources or add a node.
- **ImagePullBackOff** — your nodes may not have outbound internet access to Docker Hub (`docker.io/shazilhamzah/podpilot`). Ask your network team to whitelist it.

### Pod in `CrashLoopBackOff`

```bash
kubectl logs -n podpilot -l app=podpilot --previous
```

- **`KeyError: AI_API_KEY`** — the secret key name is wrong. Check with `kubectl get secret podpilot-secrets -n podpilot -o yaml`.
- **`pymongo.errors.ServerSelectionTimeoutError`** — your cluster's egress firewall is blocking outbound traffic to `*.mongo.cosmos.azure.com:10255`. Ask your network team to allow it.
- **`openai.AuthenticationError`** — the API key we sent you is incorrect or expired. Contact the PodPilot team for a new one.

### Chat / AI features return empty

Your cluster may be blocking outbound HTTPS to `*.openai.azure.com`. The pod needs egress access to:

```
foundry-popilot-analysi-resource.openai.azure.com   port 443
```

Ask your network/security team to whitelist this domain.

### CPU / Memory always shows `0`

Install `metrics-server` in your cluster:

```bash
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
```

Give it ~60 seconds, then refresh the PodPilot dashboard.

### `EXTERNAL-IP` stays `<pending>` forever

Your cluster doesn't have a cloud load balancer controller (common on bare-metal or on-prem). Use port-forward instead:

```bash
kubectl port-forward -n podpilot svc/podpilot 8080:80
```

Or ask your platform team to set up an Ingress controller.

---

## Uninstall

```bash
kubectl delete -f https://raw.githubusercontent.com/shazilhamzah/podpilot/main/k8s/podpilot.yaml
```

This removes everything PodPilot created in your cluster. Your cluster workloads are untouched. Data in our Cosmos DB (your snapshots) will be retained for 30 days then purged — contact us sooner if you need it deleted immediately.

---

## Outbound network requirements (firewall allowlist)

If your cluster runs in a restricted network, your security/network team needs to allow **outbound HTTPS (port 443)** to:

| Destination | Purpose |
|---|---|
| `foundry-popilot-analysi-resource.openai.azure.com` | Azure AI Foundry (LLM calls) |
| `podpilot-cosmos.mongo.cosmos.azure.com` | Cosmos DB (snapshot storage) |
| `registry-1.docker.io` / `docker.io` | Pull the PodPilot container image (one-time) |

No inbound firewall rules are needed.

---

*PodPilot · `docker.io/shazilhamzah/podpilot:latest` · Contact: support@podpilot.io*

---
---

# 🛑 INTERNAL ONLY: PodPilot Team OIDC Setup 🛑
*(Do not include this section when sending the guide to the client)*

When a client sends you their **OIDC Issuer URL**, run these Azure CLI commands in our tenant to authorize their cluster. This creates a trust relationship so their pods can access our Azure OpenAI resources without an API key.

```bash
# 1. Set the variables
IDENTITY_NAME="podpilot-identity"              # Our managed identity name
RESOURCE_GROUP="rg-podpilot"                   # Our resource group
CLIENT_OIDC_ISSUER="<URL_RECEIVED_FROM_CLIENT>" # Paste the URL here
CLIENT_CLUSTER_NAME="acme-corp-prod"           # Used to name the credential
FEDERATED_CREDENTIAL_NAME="client-${CLIENT_CLUSTER_NAME}"

# 2. Create the federated credential
# This tells Azure AD to trust tokens signed by the client's cluster
az identity federated-credential create \
  --name $FEDERATED_CREDENTIAL_NAME \
  --identity-name $IDENTITY_NAME \
  --resource-group $RESOURCE_GROUP \
  --issuer $CLIENT_OIDC_ISSUER \
  --subject "system:serviceaccount:podpilot:podpilot" \
  --audience "api://AzureADTokenExchange"

# 3. Ensure the identity has access to AI and Storage
PRINCIPAL_ID=$(az identity show --name $IDENTITY_NAME --resource-group $RESOURCE_GROUP --query principalId -otsv)
az role assignment create --assignee $PRINCIPAL_ID --role "Cognitive Services OpenAI User" --scope "/subscriptions/$(az account show --query id -otsv)/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.CognitiveServices/accounts/foundry-popilot-analysi-resource"
az cosmosdb sql role assignment create --account-name podpilot-cosmos --resource-group $RESOURCE_GROUP --principal-id $PRINCIPAL_ID --scope "/" --role-definition-id 00000000-0000-0000-0000-000000000002

# 4. Get the IDs and URI to send back to the client
CLIENT_ID=$(az identity show --name $IDENTITY_NAME --resource-group $RESOURCE_GROUP --query clientId -otsv)
TENANT_ID=$(az account show --query tenantId -otsv)
MONGO_DB_URI=$(az cosmosdb keys list -n podpilot-cosmos -g $RESOURCE_GROUP --type connection-strings --query "connectionStrings[0].connectionString" -otsv)

echo -e "\n✅ Success! Send the following to the client:\n"
echo "Client ID: $CLIENT_ID"
echo "Tenant ID: $TENANT_ID"
echo "Mongo DB URI: $MONGO_DB_URI"
```

### Option B — PowerShell (Windows)

```powershell
# 1. Set the variables
$IDENTITY_NAME = "podpilot-identity"              # Our managed identity name
$RESOURCE_GROUP = "rg-podpilot"                   # Our resource group
$CLIENT_OIDC_ISSUER = "<URL_RECEIVED_FROM_CLIENT>" # Paste the URL here
$CLIENT_CLUSTER_NAME = "acme-corp-prod"           # Used to name the credential
$FEDERATED_CREDENTIAL_NAME = "client-$CLIENT_CLUSTER_NAME"

# 2. Create the federated credential
# This tells Azure AD to trust tokens signed by the client's cluster
az identity federated-credential create `
  --name $FEDERATED_CREDENTIAL_NAME `
  --identity-name $IDENTITY_NAME `
  --resource-group $RESOURCE_GROUP `
  --issuer $CLIENT_OIDC_ISSUER `
  --subject "system:serviceaccount:podpilot:podpilot" `
  --audience "api://AzureADTokenExchange"

# 3. Ensure the identity has access to AI and Storage
$PRINCIPAL_ID = az identity show --name $IDENTITY_NAME --resource-group $RESOURCE_GROUP --query principalId -otsv
$SUB_ID = az account show --query id -otsv
az role assignment create --assignee $PRINCIPAL_ID --role "Cognitive Services OpenAI User" --scope "/subscriptions/$SUB_ID/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.CognitiveServices/accounts/foundry-popilot-analysi-resource"
az cosmosdb sql role assignment create --account-name podpilot-cosmos --resource-group $RESOURCE_GROUP --principal-id $PRINCIPAL_ID --scope "/" --role-definition-id 00000000-0000-0000-0000-000000000002

# 4. Get the IDs and URI to send back to the client
$CLIENT_ID = az identity show --name $IDENTITY_NAME --resource-group $RESOURCE_GROUP --query clientId -otsv
$TENANT_ID = az account show --query tenantId -otsv
$MONGO_DB_URI = az cosmosdb keys list -n podpilot-cosmos -g $RESOURCE_GROUP --type connection-strings --query "connectionStrings[0].connectionString" -otsv

Write-Host ""
Write-Host "✅ Success! Send the following to the client:" -ForegroundColor Green
Write-Host ""
Write-Host "Client ID: $CLIENT_ID"
Write-Host "Tenant ID: $TENANT_ID"
Write-Host "Mongo DB URI: $MONGO_DB_URI"
```
