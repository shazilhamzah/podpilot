import os
import copy
import requests

VM_SKU = "Standard_B2s"
VM_CPU_CORES = 2
VM_MEM_GB = 4
VM_COST_PER_HOUR = 0.0416          # USD per hour

CPU_PRICE_PER_CORE_HOUR = VM_COST_PER_HOUR / VM_CPU_CORES
RAM_PRICE_PER_GB_HOUR = VM_COST_PER_HOUR / VM_MEM_GB

OPENCOST_URL = os.getenv("OPENCOST_ENDPOINT", "http://cost-analysis-agent.kube-system.svc.cluster.local:9003/allocation/compute")

def fetch_opencost_data():
    try:
        response = requests.get(
            f"{OPENCOST_URL}?window=1h&aggregate=pod",
            timeout=5
        )
        if response.status_code == 200:
            data = response.json().get("data", [])
            if data and isinstance(data, list):
                first_window = data[0]
                allocations = {}
                for k, v in first_window.items():
                    if isinstance(v, dict):
                        if "totalCost" in v:
                            allocations[k] = v
                        else:
                            for pod_key, pod_alloc in v.items():
                                if isinstance(pod_alloc, dict) and "totalCost" in pod_alloc:
                                    allocations[pod_key] = pod_alloc
                return allocations
    except Exception:
        pass
    return None

def enrich_with_cost(snapshot: dict) -> dict:
    """
    Takes the snapshot dict from snapshot.py and returns a deepcopy
    with cost fields added to every pod and a cost summary at the top level.
    """
    enriched = copy.deepcopy(snapshot)
    
    opencost_data = fetch_opencost_data()
    summary_source = "opencost" if opencost_data is not None else "estimated"
    
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
        
        pod_key = f"{pod.get('namespace', 'default')}/{pod.get('name')}"
        
        if opencost_data and pod_key in opencost_data:
            alloc = opencost_data[pod_key]
            cost_per_hour = alloc.get("totalCost", 0.0)
            cpu_cost = alloc.get("cpuCost", 0.0)
            ram_cost = alloc.get("ramCost", 0.0)
            
            cpu_unit_price = (cpu_cost / cpu_req) if cpu_req > 0 else CPU_PRICE_PER_CORE_HOUR
            ram_unit_price = (ram_cost / mem_req) if mem_req > 0 else RAM_PRICE_PER_GB_HOUR
            
            actual_cost_per_hour = (cpu_actual * cpu_unit_price) + (mem_actual * ram_unit_price)
            pod["cost_source"] = "opencost"
        else:
            cost_per_hour = (cpu_req * CPU_PRICE_PER_CORE_HOUR) + (mem_req * RAM_PRICE_PER_GB_HOUR)
            actual_cost_per_hour = (cpu_actual * CPU_PRICE_PER_CORE_HOUR) + (mem_actual * RAM_PRICE_PER_GB_HOUR)
            pod["cost_source"] = "estimated"
        
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
        "cost_source": summary_source,
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
