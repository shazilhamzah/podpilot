def token_estimate(snapshot: dict) -> int:
    import json
    raw = json.dumps(snapshot, default=str)
    return len(raw) // 4          # rough estimate: 4 chars per token

def sanitize(snapshot: dict) -> dict:
    """
    Takes the cost-enriched snapshot dict and returns a stripped-down
    version with exactly the fields required by the LLM prompt.
    Builds a fresh dict to avoid mutations and bloat.
    """
    clean = {
        "captured_at": str(snapshot.get("captured_at", "")),
        "cluster_name": str(snapshot.get("cluster_name", "")),
        "cost_summary": {},
        "nodes": [],
        "pods": [],
        "deployments": [],
        "services": [],
        "pvcs": []
    }
    
    # Cost Summary
    cs = snapshot.get("cost_summary", {})
    clean["cost_summary"] = {
        "total_cost_per_hour": float(cs.get("total_cost_per_hour", 0.0)),
        "total_wasted_per_hour": float(cs.get("total_wasted_per_hour", 0.0)),
        "total_wasted_per_month": float(cs.get("total_wasted_per_month", 0.0))
    }
    
    # Nodes
    for node in snapshot.get("nodes", []):
        clean["nodes"].append({
            "name": str(node.get("name", "")),
            "cpu_capacity": float(node.get("cpu_capacity", 0.0)),
            "mem_capacity_gb": float(node.get("mem_capacity_gb", 0.0)),
            "cpu_usage": float(node.get("cpu_usage", 0.0)),
            "mem_usage_gb": float(node.get("mem_usage_gb", 0.0))
        })
        
    # Pods
    for pod in snapshot.get("pods", []):
        clean["pods"].append({
            "name": str(pod.get("name") or ""),
            "namespace": str(pod.get("namespace") or ""),
            "status": str(pod.get("status") or ""),
            "restart_count": int(pod.get("restart_count") or 0),
            "cpu_requested": float(pod.get("cpu_requested") or 0.0),
            "mem_requested_gb": float(pod.get("mem_requested_gb") or 0.0),
            "cpu_actual": float(pod.get("cpu_actual") or 0.0),
            "mem_actual_gb": float(pod.get("mem_actual_gb") or 0.0),
            "has_cpu_limit": bool(pod.get("has_cpu_limit") or False),
            "has_mem_limit": bool(pod.get("has_mem_limit") or False),
            "cost_per_hour": float(pod.get("cost_per_hour") or 0.0),
            "wasted_cost_per_hour": float(pod.get("wasted_cost_per_hour") or 0.0),
            "wasted_cost_per_month": float(pod.get("wasted_cost_per_month") or 0.0)
        })
        
    # Deployments
    for dep in snapshot.get("deployments", []):
        clean["deployments"].append({
            "name": str(dep.get("name", "")),
            "namespace": str(dep.get("namespace", "")),
            "desired_replicas": int(dep.get("desired_replicas", 0)),
            "ready_replicas": int(dep.get("ready_replicas", 0))
        })
        
    # Services
    for svc in snapshot.get("services", []):
        clean["services"].append({
            "name": str(svc.get("name", "")),
            "namespace": str(svc.get("namespace", "")),
            "type": str(svc.get("type", "")),
            "port": int(svc.get("port", 0))
        })
        
    # PVCs
    for pvc in snapshot.get("pvcs", []):
        clean["pvcs"].append({
            "name": str(pvc.get("name", "")),
            "namespace": str(pvc.get("namespace", "")),
            "status": str(pvc.get("status", "")),
            "capacity_gb": float(pvc.get("capacity_gb", 0.0)),
            "storage_class": str(pvc.get("storage_class", ""))
        })

    # Token check
    if token_estimate(clean) > 6000:
        print("WARNING: sanitized snapshot exceeds 6000 tokens. Consider filtering to podpilot-demo namespace only.")

    return clean

if __name__ == "__main__":
    import json
    from snapshot import snapshot
    from cost import enrich_with_cost
    
    raw = snapshot()
    enriched = enrich_with_cost(raw)
    clean = sanitize(enriched)
    tokens = token_estimate(clean)
    
    print(f"Token estimate: ~{tokens} tokens")
    print(f"Pods: {len(clean['pods'])}")
    print(f"Nodes: {len(clean['nodes'])}")
    print(json.dumps(clean, indent=2, default=str))
