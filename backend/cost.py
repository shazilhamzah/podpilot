import copy

VM_SKU = "Standard_B2s"
VM_CPU_CORES = 2
VM_MEM_GB = 4
VM_COST_PER_HOUR = 0.0416          # USD per hour

CPU_PRICE_PER_CORE_HOUR = VM_COST_PER_HOUR / VM_CPU_CORES
RAM_PRICE_PER_GB_HOUR = VM_COST_PER_HOUR / VM_MEM_GB

def enrich_with_cost(snapshot: dict) -> dict:
    """
    Takes the snapshot dict from snapshot.py and returns a deepcopy
    with cost fields added to every pod and a cost summary at the top level.
    """
    enriched = copy.deepcopy(snapshot)
    
    total_cost_per_hour = 0.0
    total_wasted_per_hour = 0.0
    total_wasted_per_month = 0.0
    
    pods = enriched.get("pods", [])
    for pod in pods:
        # Get requested resources, default to 0.0
        cpu_req = pod.get("cpu_requested")
        if cpu_req is None: cpu_req = 0.0
        
        mem_req = pod.get("mem_requested_gb")
        if mem_req is None: mem_req = 0.0
        
        # Get actual usage, default to 0.0
        cpu_actual = pod.get("cpu_actual")
        if cpu_actual is None: cpu_actual = 0.0
        
        mem_actual = pod.get("mem_actual_gb")
        if mem_actual is None: mem_actual = 0.0
        
        # Calculate costs
        cost_per_hour = (cpu_req * CPU_PRICE_PER_CORE_HOUR) + (mem_req * RAM_PRICE_PER_GB_HOUR)
        actual_cost_per_hour = (cpu_actual * CPU_PRICE_PER_CORE_HOUR) + (mem_actual * RAM_PRICE_PER_GB_HOUR)
        
        wasted_cost_per_hour = max(0.0, cost_per_hour - actual_cost_per_hour)
        wasted_cost_per_month = wasted_cost_per_hour * 730.0
        
        # Round and set fields
        pod["cost_per_hour"] = round(cost_per_hour, 6)
        pod["actual_cost_per_hour"] = round(actual_cost_per_hour, 6)
        pod["wasted_cost_per_hour"] = round(wasted_cost_per_hour, 6)
        pod["wasted_cost_per_month"] = round(wasted_cost_per_month, 6)
        
        total_cost_per_hour += pod["cost_per_hour"]
        total_wasted_per_hour += pod["wasted_cost_per_hour"]
        total_wasted_per_month += pod["wasted_cost_per_month"]

    enriched["cost_summary"] = {
        "total_cost_per_hour": round(total_cost_per_hour, 6),
        "total_wasted_per_hour": round(total_wasted_per_hour, 6),
        "total_wasted_per_month": round(total_wasted_per_month, 6),
        "reference_vm_sku": VM_SKU,
        "cpu_price_per_core_hour": round(CPU_PRICE_PER_CORE_HOUR, 6),
        "ram_price_per_gb_hour": round(RAM_PRICE_PER_GB_HOUR, 6)
    }
    
    return enriched

if __name__ == "__main__":
    import json
    from snapshot import snapshot
    raw = snapshot()
    enriched = enrich_with_cost(raw)
    print(json.dumps(enriched["cost_summary"], indent=2))
    for pod in enriched["pods"]:
        print(f"{pod['name']}: "
              f"cost=${pod['cost_per_hour']:.4f}/hr "
              f"wasted=${pod['wasted_cost_per_hour']:.4f}/hr "
              f"(${pod['wasted_cost_per_month']:.2f}/mo)")
