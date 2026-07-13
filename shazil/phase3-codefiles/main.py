"""
Podpilot - single-file backend (for now)

Pulls a live snapshot of the cluster (pods, nodes, deployments, services, PVCs)
and exposes it via FastAPI.

Run:
    pip install fastapi uvicorn kubernetes
    uvicorn main:app --reload --port 8000

Requires:
    - a working kubeconfig (local dev) or in-cluster service account (when deployed)
    - metrics-server installed in the cluster for actual CPU/memory usage
      (minikube addons enable metrics-server). Without it, actual usage
      fields will just come back as 0.
"""

import re
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from kubernetes import client, config

from cost import attach_costs
from sanitize import sanitize

app = FastAPI()

# ---------------------------------------------------------------------------
# Unit parsing helpers
# ---------------------------------------------------------------------------

def parse_cpu(value: str) -> float:
    """'2000m' or '2' -> cores as float."""
    if not value:
        return 0.0
    if value.endswith("m"):
        return float(value[:-1]) / 1000
    return float(value)


def parse_memory(value: str) -> float:
    """'4Gi' / '512Mi' / '2048Ki' -> GB as float."""
    if not value:
        return 0.0
    match = re.match(r"([\d.]+)([A-Za-z]*)", value)
    if not match:
        return 0.0
    num, unit = float(match.group(1)), match.group(2).lower()
    if unit in ("gi", "g"):
        return num
    if unit in ("mi", "m"):
        return num / 1024
    if unit in ("ki", "k"):
        return num / (1024 * 1024)
    if unit == "":
        return num / (1024 ** 3)  # raw bytes
    return num


# ---------------------------------------------------------------------------
# Kubernetes API clients
# ---------------------------------------------------------------------------

def get_api_clients(in_cluster: bool = False):
    if in_cluster:
        config.load_incluster_config()
    else:
        config.load_kube_config()

    return {
        "core": client.CoreV1Api(),
        "apps": client.AppsV1Api(),
        "custom": client.CustomObjectsApi(),
    }


# ---------------------------------------------------------------------------
# Metrics lookups (from metrics-server via the metrics.k8s.io API)
# ---------------------------------------------------------------------------

def _pod_metrics_lookup(custom):
    """pod_name -> (cpu_cores, mem_gb). Empty dict if metrics-server isn't available."""
    try:
        items = custom.list_cluster_custom_object("metrics.k8s.io", "v1beta1", "pods")["items"]
    except Exception:
        return {}
    lookup = {}
    for item in items:
        name = item["metadata"]["name"]
        cpu = sum(parse_cpu(c["usage"]["cpu"]) for c in item["containers"])
        mem = sum(parse_memory(c["usage"]["memory"]) for c in item["containers"])
        lookup[name] = (cpu, mem)
    return lookup


def _node_metrics_lookup(custom):
    """node_name -> (cpu_cores, mem_gb). Empty dict if metrics-server isn't available."""
    try:
        items = custom.list_cluster_custom_object("metrics.k8s.io", "v1beta1", "nodes")["items"]
    except Exception:
        return {}
    lookup = {}
    for item in items:
        name = item["metadata"]["name"]
        cpu = parse_cpu(item["usage"]["cpu"])
        mem = parse_memory(item["usage"]["memory"])
        lookup[name] = (cpu, mem)
    return lookup


# ---------------------------------------------------------------------------
# Per-resource snapshot builders
# ---------------------------------------------------------------------------

def _snapshot_pods(core, custom):
    pods = core.list_pod_for_all_namespaces().items
    usage = _pod_metrics_lookup(custom)

    result = []
    for pod in pods:
        req_cpu_total, req_mem_total = 0.0, 0.0
        for c in pod.spec.containers:
            req = (c.resources.requests or {}) if c.resources else {}
            req_cpu_total += parse_cpu(req.get("cpu"))
            req_mem_total += parse_memory(req.get("memory"))

        restart_count = sum(
            (cs.restart_count or 0) for cs in (pod.status.container_statuses or [])
        )
        actual_cpu, actual_mem = usage.get(pod.metadata.name, (0.0, 0.0))

        result.append({
            "name": pod.metadata.name,
            "namespace": pod.metadata.namespace,
            "status_phase": pod.status.phase,
            "restart_count": restart_count,
            "cpu_requested_cores": round(req_cpu_total, 4),
            "memory_requested_gb": round(req_mem_total, 4),
            "cpu_actual_cores": round(actual_cpu, 4),
            "memory_actual_gb": round(actual_mem, 4),
        })
    return result


def _snapshot_nodes(core, custom):
    nodes = core.list_node().items
    usage = _node_metrics_lookup(custom)

    result = []
    for node in nodes:
        capacity = node.status.capacity or {}
        actual_cpu, actual_mem = usage.get(node.metadata.name, (0.0, 0.0))

        result.append({
            "name": node.metadata.name,
            "cpu_capacity_cores": round(parse_cpu(capacity.get("cpu")), 4),
            "memory_capacity_gb": round(parse_memory(capacity.get("memory")), 4),
            "cpu_actual_cores": round(actual_cpu, 4),
            "memory_actual_gb": round(actual_mem, 4),
        })
    return result


def _snapshot_deployments(apps):
    deployments = apps.list_deployment_for_all_namespaces().items
    return [
        {
            "name": d.metadata.name,
            "namespace": d.metadata.namespace,
            "desired_replicas": d.spec.replicas or 0,
            "ready_replicas": d.status.ready_replicas or 0,
        }
        for d in deployments
    ]


def _snapshot_services(core):
    services = core.list_service_for_all_namespaces().items
    result = []
    for svc in services:
        ports = [p.port for p in (svc.spec.ports or [])]
        result.append({
            "name": svc.metadata.name,
            "namespace": svc.metadata.namespace,
            "type": svc.spec.type,               # ClusterIP / NodePort / LoadBalancer
            "port": ports[0] if ports else None,  # primary port
            "ports": ports,                       # full list, in case there's more than one
        })
    return result


def _snapshot_pvcs(core):
    pvcs = core.list_persistent_volume_claim_for_all_namespaces().items
    result = []
    for pvc in pvcs:
        capacity = (pvc.status.capacity or {}).get("storage")
        result.append({
            "name": pvc.metadata.name,
            "namespace": pvc.metadata.namespace,
            "status": pvc.status.phase,  # Bound / Pending / Lost
            "storage_capacity_gb": round(parse_memory(capacity), 4) if capacity else None,
            "storage_class_name": pvc.spec.storage_class_name,
        })
    return result


# ---------------------------------------------------------------------------
# The main entry point: snapshot()
# ---------------------------------------------------------------------------

def snapshot(in_cluster: bool = False) -> dict:
    """Pulls a full point-in-time snapshot of the live cluster."""
    apis = get_api_clients(in_cluster=in_cluster)
    core, apps, custom = apis["core"], apis["apps"], apis["custom"]

    return {
        "pods": _snapshot_pods(core, custom),
        "nodes": _snapshot_nodes(core, custom),
        "deployments": _snapshot_deployments(apps),
        "services": _snapshot_services(core),
        "pvcs": _snapshot_pvcs(core),
    }


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(title="Podpilot API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten before deploying
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {"status": "ok", "service": "podpilot"}


@app.get("/snapshot/live")
def live_snapshot():
    """Pulls fresh data straight from the cluster on every call. No caching."""
    return snapshot()


@app.get("/snapshot/ai-ready")
def ai_ready_snapshot():
    """
    Phase 3 pipeline: raw snapshot -> attach cost -> sanitize.
    Small, clean, cost-enriched JSON, safe to drop straight into an LLM prompt.
    """
    raw = snapshot()
    priced = attach_costs(raw)
    clean = sanitize(priced)
    return clean