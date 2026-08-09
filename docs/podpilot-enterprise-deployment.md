# PodPilot — Client Cluster Onboarding Guide
### Deploy PodPilot into your Kubernetes cluster · Powered by our Foundry & Storage

---

> [!IMPORTANT]
> You do **not** need to provision any Azure resources. PodPilot's AI backend (Azure AI Foundry / gpt-4o) and snapshot storage (Azure Cosmos DB) are managed by us. You only need `kubectl` access to your own cluster.

---

## What you need from us first

Before you start, request the following from the PodPilot team. We will send them securely (e.g. via 1Password, Azure Key Vault share, or an encrypted email):

| Credential | Description |
|---|---|
| `AZURE_OPENAI_API_KEY` | API key for our Foundry endpoint |
| `MONGO_DB_URI` | Connection string to our Cosmos DB (scoped read/write to your tenant's namespace) |

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

No Azure CLI, no Helm, no cloud provider account needed.

---

## Step 1 — Apply the Manifest

Download and apply the all-in-one manifest. This will create the namespace and all required resources:

```bash
kubectl apply -f https://raw.githubusercontent.com/shazilhamzah/podpilot/main/k8s/podpilot.yaml
```

Expected output:

```
namespace/podpilot created
serviceaccount/podpilot created
clusterrole.rbac.authorization.k8s.io/podpilot-reader created
clusterrolebinding.rbac.authorization.k8s.io/podpilot-reader-binding created
deployment.apps/podpilot created
service/podpilot created
```

---

## Step 2 — Create the Secret

This is the **only** place you put the credentials we sent you. Never commit this to git.

```bash
# Replace the two placeholder values with what we sent you
kubectl create secret generic podpilot-secrets \
  --namespace podpilot \
  --from-literal=AZURE_OPENAI_ENDPOINT="https://foundry-popilot-analysi-resource.openai.azure.com/openai/v1" \
  --from-literal=AZURE_OPENAI_DEPLOYMENT="gpt-4o" \
  --from-literal=MONGO_DB_URI="<MONGO_DB_URI_WE_SENT_YOU>" \
  --from-literal=AI_API_KEY="<AZURE_OPENAI_API_KEY_WE_SENT_YOU>" \
  --from-literal=CLUSTER_NAME="<your-cluster-name>"
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

## Step 3 — Wait for the Pod to Come Up

```bash
kubectl rollout status deployment/podpilot -n podpilot --timeout=120s
```

```
deployment "podpilot" successfully rolled out
```

If it takes more than 2 minutes, jump to [Troubleshooting](#troubleshooting).

---

## Step 4 — Access the Dashboard

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
