"""
Podpilot - Phase 3, Job 1: Cost heuristic

Attaches a $/hr and $/month estimate to each pod based on its requested
CPU and memory, against a flat reference VM price. Also rolls up a
cluster-wide total, and computes "wasted" cost (requested but not
actually used).

This does NOT call any cloud billing API - it's a heuristic based on
generic on-demand VM pricing. Swap the constants below for real pricing
later without touching the rest of the app.
"""

# ---------------------------------------------------------------------------
# Reference pricing (approximate, general-purpose on-demand VM rates)
# ---------------------------------------------------------------------------

PRICE_PER_CORE_HOUR = 0.031   # $ per vCPU-hour
PRICE_PER_GB_HOUR = 0.004     # $ per GB-hour
HOURS_PER_MONTH = 730         # 365 * 24 / 12


def _cost(cpu_cores: float, mem_gb: float) -> float:
    """Raw $/hr for a given amount of CPU + memory."""
    return (cpu_cores * PRICE_PER_CORE_HOUR) + (mem_gb * PRICE_PER_GB_HOUR)


def _pod_cost(pod: dict) -> dict:
    """Cost fields for a single pod: requested cost + wasted cost."""
    cpu_req = pod.get("cpu_requested_cores", 0.0)
    mem_req = pod.get("memory_requested_gb", 0.0)
    cpu_actual = pod.get("cpu_actual_cores", 0.0)
    mem_actual = pod.get("memory_actual_gb", 0.0)

    hourly = _cost(cpu_req, mem_req)

    wasted_cpu = max(0.0, cpu_req - cpu_actual)
    wasted_mem = max(0.0, mem_req - mem_actual)
    wasted_hourly = _cost(wasted_cpu, wasted_mem)

    return {
        "cost_per_hour": round(hourly, 5),
        "cost_per_month": round(hourly * HOURS_PER_MONTH, 2),
        "wasted_cost_per_hour": round(wasted_hourly, 5),
        "wasted_cost_per_month": round(wasted_hourly * HOURS_PER_MONTH, 2),
    }


def attach_costs(snapshot: dict) -> dict:
    """
    Mutates + returns the snapshot: adds cost fields to every pod,
    and adds cluster-wide totals at the top level.
    """
    total_hourly = 0.0
    total_wasted_hourly = 0.0

    for pod in snapshot.get("pods", []):
        cost = _pod_cost(pod)
        pod.update(cost)
        total_hourly += cost["cost_per_hour"]
        total_wasted_hourly += cost["wasted_cost_per_hour"]

    snapshot["cluster_cost_per_hour"] = round(total_hourly, 5)
    snapshot["cluster_cost_per_month"] = round(total_hourly * HOURS_PER_MONTH, 2)
    snapshot["cluster_wasted_cost_per_hour"] = round(total_wasted_hourly, 5)
    snapshot["cluster_wasted_cost_per_month"] = round(total_wasted_hourly * HOURS_PER_MONTH, 2)

    return snapshot