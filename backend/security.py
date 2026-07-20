"""
security.py
Podpilot - security checks

Runs entirely on the already-sanitized snapshot dict (the output of
sanitize() in sanitize.py) -- no extra Kubernetes API calls needed, since
the fields it needs (runs_as_root, has_cpu_limit, has_mem_limit, images,
service type) are already present there.
"""


def check_root_containers(pods: list) -> dict:
    affected = [f"{p['namespace']}/{p['name']}" for p in pods if p.get("runs_as_root")]
    return {"name": "Root containers", "passed": len(affected) == 0, "affected": affected}


def check_missing_cpu_limits(pods: list) -> dict:
    affected = [f"{p['namespace']}/{p['name']}" for p in pods if not p.get("has_cpu_limit")]
    return {"name": "Missing CPU limits", "passed": len(affected) == 0, "affected": affected}


def check_missing_memory_limits(pods: list) -> dict:
    affected = [f"{p['namespace']}/{p['name']}" for p in pods if not p.get("has_mem_limit")]
    return {"name": "Missing memory limits", "passed": len(affected) == 0, "affected": affected}


def check_unpinned_images(pods: list) -> dict:
    affected = []
    for p in pods:
        for image in p.get("images", []):
            if image.endswith(":latest") or ":" not in image:
                affected.append(f"{p['namespace']}/{p['name']}: {image}")
    return {"name": "Unpinned image tags", "passed": len(affected) == 0, "affected": affected}


def check_open_nodeports(services: list) -> dict:
    affected = [f"{s['namespace']}/{s['name']}" for s in services if s.get("type") == "NodePort"]
    return {"name": "Open NodePorts", "passed": len(affected) == 0, "affected": affected}


def run_all_checks(clean_snapshot: dict) -> list:
    """Takes the sanitized snapshot dict (sanitize.py's output) and returns
    a list of check results: [{name, passed, affected}, ...]"""
    pods = clean_snapshot.get("pods", [])
    services = clean_snapshot.get("services", [])

    return [
        check_root_containers(pods),
        check_missing_cpu_limits(pods),
        check_missing_memory_limits(pods),
        check_unpinned_images(pods),
        check_open_nodeports(services),
    ]