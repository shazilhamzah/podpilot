"""
Podpilot - Phase 3, Job 2: Sanitization

Projects a (cost-enriched) snapshot down to the minimal set of fields
an AI copilot needs to reason about cost/health. Shortens key names to
save tokens, drops anything redundant, and rounds numbers.

This never adds data - only removes/renames. Run it LAST, after
attach_costs(), so cost fields are present to be kept.
"""


def _sanitize_pod(pod: dict) -> dict:
    return {
        "name": pod["name"],
        "ns": pod["namespace"],
        "status": pod["status_phase"],
        "restarts": pod["restart_count"],
        "cpu_req": pod["cpu_requested_cores"],
        "mem_req_gb": pod["memory_requested_gb"],
        "cpu_actual": pod["cpu_actual_cores"],
        "mem_actual_gb": pod["memory_actual_gb"],
        "cost_hr": pod.get("cost_per_hour", 0.0),
        "wasted_cost_hr": pod.get("wasted_cost_per_hour", 0.0),
    }


def _sanitize_node(node: dict) -> dict:
    return {
        "name": node["name"],
        "cpu_cap": node["cpu_capacity_cores"],
        "mem_cap_gb": node["memory_capacity_gb"],
        "cpu_actual": node["cpu_actual_cores"],
        "mem_actual_gb": node["memory_actual_gb"],
    }


def _sanitize_deployment(dep: dict) -> dict:
    return {
        "name": dep["name"],
        "ns": dep["namespace"],
        "desired": dep["desired_replicas"],
        "ready": dep["ready_replicas"],
    }


def _sanitize_service(svc: dict) -> dict:
    return {
        "name": svc["name"],
        "ns": svc["namespace"],
        "type": svc["type"],
        "port": svc.get("port"),
    }


def _sanitize_pvc(pvc: dict) -> dict:
    return {
        "name": pvc["name"],
        "ns": pvc["namespace"],
        "status": pvc["status"],
        "cap_gb": pvc.get("storage_capacity_gb"),
    }


def sanitize(snapshot: dict) -> dict:
    """Returns a NEW, minimal dict - does not mutate the input."""
    return {
        "pods": [_sanitize_pod(p) for p in snapshot.get("pods", [])],
        "nodes": [_sanitize_node(n) for n in snapshot.get("nodes", [])],
        "deployments": [_sanitize_deployment(d) for d in snapshot.get("deployments", [])],
        "services": [_sanitize_service(s) for s in snapshot.get("services", [])],
        "pvcs": [_sanitize_pvc(p) for p in snapshot.get("pvcs", [])],
        "cluster_cost_per_hour": snapshot.get("cluster_cost_per_hour"),
        "cluster_cost_per_month": snapshot.get("cluster_cost_per_month"),
        "cluster_wasted_cost_per_hour": snapshot.get("cluster_wasted_cost_per_hour"),
        "cluster_wasted_cost_per_month": snapshot.get("cluster_wasted_cost_per_month"),
    }