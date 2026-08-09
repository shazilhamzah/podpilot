# 02 — Set Up Azure OpenAI and Workload Identity

**What to build:** Provision Azure OpenAI with a GPT-4o deployment and wire the cluster's identity system so PodPilot can call it without any secrets. This involves creating a user-assigned Managed Identity, assigning it the `Cognitive Services OpenAI User` and `Cost Management Reader` RBAC roles, and creating a federated credential that binds it to the `podpilot/podpilot` Kubernetes Service Account. The Kubernetes manifests (`podpilot.yaml`) are updated to annotate the Service Account with the identity's client ID and label the pod template for Workload Identity injection. When done, a pod running under the `podpilot` SA in the cluster can exchange its projected token for an Azure AD token and successfully call the Azure OpenAI API — no `AI_API_KEY` secret needed.

**Blocked by:** 01 — Provision Core Azure Infrastructure (needs the AKS OIDC issuer URL to create the federated credential).

**Status:** done

- [x] Azure OpenAI service is provisioned in the same resource group
- [x] GPT-4o model is deployed under the deployment name `gpt-4o`
- [x] User-assigned Managed Identity `podpilot-identity` exists
- [x] Identity holds `Cognitive Services OpenAI User` role scoped to the OpenAI resource
- [x] Identity holds `Cost Management Reader` role scoped to the subscription
- [x] Federated credential is created linking the identity to `system:serviceaccount:podpilot:podpilot`
- [x] `podpilot.yaml` Service Account has the `azure.workload.identity/client-id` annotation
- [x] `podpilot.yaml` pod template has the `azure.workload.identity/use: "true"` label
- [x] A test pod running under the `podpilot` SA can acquire an Azure AD token via the projected service account token
