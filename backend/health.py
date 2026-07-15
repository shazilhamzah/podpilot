import json
import os
import re
from analyzer import client

def analyze(prompt: str, slice_data: dict) -> str:
    import json
    snapshot_json = json.dumps(slice_data, default=str)
    full_prompt = f"Here is the current cluster snapshot slice:\n\n{snapshot_json}\n\n{prompt}"
    
    chat_completion = client.chat.completions.create(
        messages=[{"role": "user", "content": full_prompt}],
        model=os.getenv("MODEL"),
        temperature=0.2,
        max_tokens=2048,
        response_format={"type": "json_object"},
    )
    return chat_completion.choices[0].message.content

def chat_with_cluster(prompt: str, snapshot: dict) -> str:
    import json
    prompt_lower = prompt.lower()

    # Determine which sections are relevant based on the question
    wants_nodes    = any(k in prompt_lower for k in ["cpu", "memory", "node", "utiliz", "capacity", "ram"])
    wants_cost     = any(k in prompt_lower for k in ["cost", "waste", "price", "spend", "money", "expensive", "budget"])
    wants_security = any(k in prompt_lower for k in ["security", "root", "limit", "port", "expose", "nodeport", "network"])
    wants_storage  = any(k in prompt_lower for k in ["pvc", "storage", "disk", "volume", "persistent"])
    wants_deploy   = any(k in prompt_lower for k in ["deploy", "replica", "scale", "rollout", "restart", "crashloop", "crash"])
    wants_pods     = any(k in prompt_lower for k in ["pod", "container", "running", "pending", "failed", "status"])

    # Always include at least pods if nothing matched
    if not any([wants_nodes, wants_cost, wants_security, wants_storage, wants_deploy, wants_pods]):
        wants_pods = True

    slice_data = {}

    if wants_cost:
        slice_data["cost_summary"] = snapshot.get("cost_summary", {})

    if wants_nodes:
        slice_data["nodes"] = [
            {
                "name": n.get("name"),
                "cpu_capacity": n.get("cpu_capacity"),
                "cpu_usage": n.get("cpu_usage"),
                "cpu_utilization_pct": round(n.get("cpu_usage", 0) / n.get("cpu_capacity", 1) * 100, 1) if n.get("cpu_capacity") else None,
                "mem_capacity_gb": round(n.get("mem_capacity_gb", 0), 2),
                "mem_usage_gb": round(n.get("mem_usage_gb", 0), 2),
                "mem_utilization_pct": round(n.get("mem_usage_gb", 0) / n.get("mem_capacity_gb", 1) * 100, 1) if n.get("mem_capacity_gb") else None,
            } for n in snapshot.get("nodes", [])
        ]

    if wants_pods or wants_cost or wants_security or wants_deploy:
        pod_fields = ["name", "namespace", "status", "status_phase", "restart_count",
                      "cpu_requested", "cpu_actual", "mem_requested_gb", "mem_actual_gb",
                      "cost_per_hour", "wasted_cost_per_month",
                      "has_cpu_limit", "has_mem_limit", "runs_as_root"]
        slice_data["pods"] = [
            {k: p.get(k) for k in pod_fields if p.get(k) is not None}
            for p in snapshot.get("pods", [])
        ]

    if wants_deploy:
        slice_data["deployments"] = [
            {"name": d.get("name"), "namespace": d.get("namespace"),
             "desired_replicas": d.get("desired_replicas"), "ready_replicas": d.get("ready_replicas")}
            for d in snapshot.get("deployments", [])
        ]

    if wants_security:
        slice_data["services"] = [
            {"name": s.get("name"), "namespace": s.get("namespace"), "type": s.get("type"), "port": s.get("port")}
            for s in snapshot.get("services", [])
        ]

    if wants_storage:
        slice_data["pvcs"] = [
            {"name": pvc.get("name"), "namespace": pvc.get("namespace"),
             "status": pvc.get("status"), "capacity_gb": pvc.get("capacity_gb"), "is_attached": pvc.get("is_attached")}
            for pvc in snapshot.get("pvcs", [])
        ]

    snapshot_json = json.dumps(slice_data, default=str)

    system_prompt = (
        "You are a Kubernetes cluster copilot with access to a live cluster snapshot. "
        "Answer the user's question using the data provided. Be concise and practical. "
        "Use bullet points or bold for clarity. Calculate percentages when asked about utilization."
    )
    full_prompt = f"Cluster snapshot:\n{snapshot_json}\n\nQuestion: {prompt}"

    chat_completion = client.chat.completions.create(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": full_prompt}
        ],
        model=os.getenv("MODEL"),
        temperature=0.3,
        max_tokens=512,
    )
    return chat_completion.choices[0].message.content



# ═══════════════════════════════════════
# SECTION 1 — SLICE EXTRACTION HELPERS
# ═══════════════════════════════════════

def slice_cost(snapshot: dict) -> dict:
    pods = []
    for p in snapshot.get("pods", []):
        if p.get("wasted_cost_per_month") is not None and p.get("wasted_cost_per_month") > 0.5:
            pods.append({
                "name": p.get("name"),
                "namespace": p.get("namespace"),
                "cpu_requested": p.get("cpu_requested"),
                "cpu_actual": p.get("cpu_actual"),
                "mem_requested_gb": p.get("mem_requested_gb"),
                "mem_actual_gb": p.get("mem_actual_gb"),
                "wasted_cost_per_hour": p.get("wasted_cost_per_hour"),
                "wasted_cost_per_month": p.get("wasted_cost_per_month")
            })
    pvcs = [
        {
            "name": pvc.get("name"),
            "namespace": pvc.get("namespace"),
            "status": pvc.get("status")
        } for pvc in snapshot.get("pvcs", [])
    ]
    return {"cost_summary": snapshot.get("cost_summary", {}), "pods": pods, "pvcs": pvcs}

def slice_reliability(snapshot: dict) -> dict:
    pods = []
    for p in snapshot.get("pods", []):
        if p.get("restart_count", 0) > 3 or p.get("status") != "Running":
            pods.append({
                "name": p.get("name"),
                "namespace": p.get("namespace"),
                "status": p.get("status"),
                "restart_count": p.get("restart_count"),
                "has_cpu_limit": p.get("has_cpu_limit"),
                "has_mem_limit": p.get("has_mem_limit")
            })
    deployments = []
    for d in snapshot.get("deployments", []):
        r_ready = d.get("ready_replicas")
        r_desired = d.get("desired_replicas")
        if r_ready is not None and r_desired is not None and r_ready < r_desired:
            deployments.append({
                "name": d.get("name"),
                "namespace": d.get("namespace"),
                "desired_replicas": r_desired,
                "ready_replicas": r_ready
            })
    return {"pods": pods, "deployments": deployments}

def slice_performance(snapshot: dict) -> dict:
    nodes = [
        {
            "name": n.get("name"),
            "cpu_capacity": n.get("cpu_capacity"),
            "cpu_usage": n.get("cpu_usage"),
            "mem_capacity_gb": n.get("mem_capacity_gb"),
            "mem_usage_gb": n.get("mem_usage_gb")
        } for n in snapshot.get("nodes", [])
    ]
    pods = []
    for p in snapshot.get("pods", []):
        status = p.get("status")
        cpu_a = p.get("cpu_actual")
        cpu_r = p.get("cpu_requested")
        if status == "Pending" or (
            cpu_a is not None and cpu_r is not None and 
            cpu_a > 0 and cpu_r > 0 and 
            (cpu_a / cpu_r) > 0.85
        ):
            pods.append({
                "name": p.get("name"),
                "namespace": p.get("namespace"),
                "status": status,
                "cpu_requested": cpu_r,
                "cpu_actual": cpu_a,
                "mem_requested_gb": p.get("mem_requested_gb"),
                "mem_actual_gb": p.get("mem_actual_gb")
            })
    return {"nodes": nodes, "pods": pods}

def slice_storage(snapshot: dict) -> dict:
    return {
        "pvcs": [
            {
                "name": pvc.get("name"),
                "namespace": pvc.get("namespace"),
                "status": pvc.get("status"),
                "capacity_gb": pvc.get("capacity_gb"),
                "storage_class": pvc.get("storage_class")
            } for pvc in snapshot.get("pvcs", [])
        ]
    }

def slice_security(snapshot: dict) -> dict:
    services = []
    for s in snapshot.get("services", []):
        if s.get("type") in ["NodePort", "LoadBalancer"]:
            services.append({
                "name": s.get("name"),
                "namespace": s.get("namespace"),
                "type": s.get("type"),
                "port": s.get("port")
            })
    pods = [
        {
            "name": p.get("name"),
            "namespace": p.get("namespace"),
            "has_cpu_limit": p.get("has_cpu_limit"),
            "has_mem_limit": p.get("has_mem_limit")
        } for p in snapshot.get("pods", [])
    ]
    deployments = [
        {
            "name": d.get("name"),
            "namespace": d.get("namespace")
        } for d in snapshot.get("deployments", [])
    ]
    return {"services": services, "pods": pods, "deployments": deployments}

# ═══════════════════════════════════════
# SECTION 4 — JSON PARSING HELPER
# ═══════════════════════════════════════

def parse_ai_json(response: str) -> dict:
    # strip markdown code fences if present
    cleaned = re.sub(r"```json|```", "", response).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # attempt to extract first { } block
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except:
                pass
    return {"issues": [], "summary": "Failed to parse AI response."}

# ═══════════════════════════════════════
# SECTION 2 — FIVE FOCUSED ANALYZERS
# ═══════════════════════════════════════

def analyze_cost(snapshot: dict) -> dict:
    slice_data = slice_cost(snapshot)
    prompt = """You are analyzing the cost and waste of a Kubernetes cluster.
Look for pods with high wasted_cost_per_month (requested much more than
actual usage). Look for PVCs that might be sitting unused.
Flag any pod wasting more than $5/month as warning,
more than $20/month as critical.

Respond ONLY in this JSON format, no other text:
{
  "issues": [
    {
      "severity": "critical" | "warning" | "info",
      "title": "short title under 10 words",
      "description": "one sentence explanation",
      "affected_resource": "exact pod/deployment/service/pvc name"
    }
  ],
  "summary": "one sentence overall summary of this category"
}"""
    response = analyze(prompt, slice_data)
    parsed = parse_ai_json(response)
    if "issues" not in parsed:
        return {"issues": [], "summary": "Cost analysis failed to parse."}
    return parsed

def analyze_reliability(snapshot: dict) -> dict:
    slice_data = slice_reliability(snapshot)
    prompt = """You are analyzing the reliability and health of a Kubernetes
cluster. Look for pods in CrashLoopBackOff or Pending status, high
restart counts, and deployments with ready_replicas less than
desired_replicas. Any CrashLoopBackOff pod is critical. Any deployment
with 0 ready replicas is critical. Missing resource limits is a warning.

Respond ONLY in this JSON format, no other text:
{
  "issues": [
    {
      "severity": "critical" | "warning" | "info",
      "title": "short title under 10 words",
      "description": "one sentence explanation",
      "affected_resource": "exact pod/deployment/service/pvc name"
    }
  ],
  "summary": "one sentence overall summary of this category"
}"""
    response = analyze(prompt, slice_data)
    parsed = parse_ai_json(response)
    if "issues" not in parsed:
        return {"issues": [], "summary": "Reliability analysis failed to parse."}
    return parsed

def analyze_performance(snapshot: dict) -> dict:
    slice_data = slice_performance(snapshot)
    prompt = """You are analyzing the performance of a Kubernetes cluster.
Look for pods in Pending state that cannot be scheduled — these are
critical. Look for pods where cpu_actual is more than 85% of
cpu_requested — this is a proxy for high utilization or throttling, flag as warning.
Look for nodes where cpu_usage is more than 80% of cpu_capacity.

Respond ONLY in this JSON format, no other text:
{
  "issues": [
    {
      "severity": "critical" | "warning" | "info",
      "title": "short title under 10 words",
      "description": "one sentence explanation",
      "affected_resource": "exact pod/deployment/service/pvc name"
    }
  ],
  "summary": "one sentence overall summary of this category"
}"""
    response = analyze(prompt, slice_data)
    parsed = parse_ai_json(response)
    if "issues" not in parsed:
        return {"issues": [], "summary": "Performance analysis failed to parse."}
    return parsed

def analyze_storage(snapshot: dict) -> dict:
    slice_data = slice_storage(snapshot)
    prompt = """You are analyzing the storage of a Kubernetes cluster.
Look for PVCs in Pending state — these are critical as workloads
depending on them will fail. Look for PVCs where is_attached is false —
these are orphaned and waste money, flag as warnings.

Respond ONLY in this JSON format, no other text:
{
  "issues": [
    {
      "severity": "critical" | "warning" | "info",
      "title": "short title under 10 words",
      "description": "one sentence explanation",
      "affected_resource": "exact pod/deployment/service/pvc name"
    }
  ],
  "summary": "one sentence overall summary of this category"
}"""
    response = analyze(prompt, slice_data)
    parsed = parse_ai_json(response)
    if "issues" not in parsed:
        return {"issues": [], "summary": "Storage analysis failed to parse."}
    return parsed

def analyze_security(snapshot: dict) -> dict:
    slice_data = slice_security(snapshot)
    prompt = """You are analyzing the security posture of a Kubernetes cluster.
Services exposed as NodePort or LoadBalancer are warnings or critical
depending on what they expose. Pods with no CPU or memory limits are
warnings as they can be exploited for resource exhaustion.
Flag every NodePort service as critical.
Flag every pod missing resource limits as warning.
Flag every pod where runs_as_root is true as a warning.

Respond ONLY in this JSON format, no other text:
{
  "issues": [
    {
      "severity": "critical" | "warning" | "info",
      "title": "short title under 10 words",
      "description": "one sentence explanation",
      "affected_resource": "exact pod/deployment/service/pvc name"
    }
  ],
  "summary": "one sentence overall summary of this category"
}"""
    response = analyze(prompt, slice_data)
    parsed = parse_ai_json(response)
    if "issues" not in parsed:
        return {"issues": [], "summary": "Security analysis failed to parse."}
    return parsed

# ═══════════════════════════════════════
# SECTION 3 — PROACTIVE HEALTH CHECK
# ═══════════════════════════════════════

def proactive_health_check(snapshot: dict) -> dict:
    cost_res = analyze_cost(snapshot)
    reliability_res = analyze_reliability(snapshot)
    performance_res = analyze_performance(snapshot)
    storage_res = analyze_storage(snapshot)
    security_res = analyze_security(snapshot)

    all_issues = []
    
    for category, res in [
        ("cost", cost_res),
        ("reliability", reliability_res),
        ("performance", performance_res),
        ("storage", storage_res),
        ("security", security_res)
    ]:
        for issue in res.get("issues", []):
            issue["category"] = category
            all_issues.append(issue)

    # Deduplicate by affected_resource + title combination
    seen = set()
    deduped_issues = []
    for issue in all_issues:
        # Cast to str because AI sometimes returns a list of resources instead of a string
        res = str(issue.get("affected_resource"))
        title = str(issue.get("title"))
        
        # Update the issue dict if it was a list so it's JSON serializable easily
        if isinstance(issue.get("affected_resource"), list):
            issue["affected_resource"] = res
            
        key = (res, title)
        if key not in seen:
            seen.add(key)
            deduped_issues.append(issue)
            
    # Rank by severity
    SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}
    deduped_issues.sort(key=lambda x: SEVERITY_ORDER.get(x.get("severity", "info"), 2))

    top_issues = deduped_issues[:10]

    critical_count = sum(1 for x in deduped_issues if x.get("severity") == "critical")
    warning_count = sum(1 for x in deduped_issues if x.get("severity") == "warning")
    info_count = sum(1 for x in deduped_issues if x.get("severity") == "info")

    return {
        "top_issues": top_issues,
        "category_summaries": {
            "cost": cost_res.get("summary", ""),
            "reliability": reliability_res.get("summary", ""),
            "performance": performance_res.get("summary", ""),
            "storage": storage_res.get("summary", ""),
            "security": security_res.get("summary", "")
        },
        "critical_count": critical_count,
        "warning_count": warning_count,
        "info_count": info_count
    }

# ═══════════════════════════════════════
# VERIFICATION
# ═══════════════════════════════════════

if __name__ == "__main__":
    from snapshot import snapshot
    from cost import enrich_with_cost
    from sanitize import sanitize

    print("Building snapshot...")
    clean = sanitize(enrich_with_cost(snapshot()))
    print(f"Snapshot ready — {len(clean['pods'])} pods\n")

    print("Running proactive health check...")
    result = proactive_health_check(clean)

    print(f"\nCRITICAL: {result['critical_count']}")
    print(f"WARNING:  {result['warning_count']}")
    print(f"INFO:     {result['info_count']}")

    print("\nTOP ISSUES:")
    for i, issue in enumerate(result["top_issues"], 1):
        print(f"{i}. [{issue.get('severity', 'info').upper()}] "
              f"[{issue.get('category', 'unknown')}] "
              f"{issue.get('title', 'Unknown')} — {issue.get('affected_resource', 'Unknown')}")

    print("\nCATEGORY SUMMARIES:")
    for cat, summary in result["category_summaries"].items():
        print(f"{cat.upper()}: {summary}")
