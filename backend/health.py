import json
import os
import re
from ai_client import client, get_model_name

def analyze(prompt: str, slice_data: dict) -> str:
    import json
    snapshot_json = json.dumps(slice_data, default=str)
    full_prompt = f"Here is the current cluster snapshot slice:\n\n{snapshot_json}\n\n{prompt}"
    
    chat_completion = client.chat.completions.create(
        messages=[{"role": "user", "content": full_prompt}],
        model=get_model_name(),
        temperature=0.2,
        max_tokens=4096,
        response_format={"type": "json_object"},
    )
    return chat_completion.choices[0].message.content

def chat_with_cluster(prompt: str, snapshot: dict, history: list = None) -> str:
    import json
    prompt_lower = prompt.lower()

    # Determine which sections are relevant based on the question
    # (Checking history messages too just in case)
    combined_text = prompt_lower
    if history:
        for msg in history:
            combined_text += " " + str(msg.get("content", "")).lower()

    wants_nodes    = any(k in combined_text for k in ["cpu", "memory", "node", "utiliz", "capacity", "ram"])
    wants_cost     = any(k in combined_text for k in ["cost", "waste", "price", "spend", "money", "expensive", "budget"])
    wants_security = any(k in combined_text for k in ["security", "root", "limit", "port", "expose", "nodeport", "network"])
    wants_storage  = any(k in combined_text for k in ["pvc", "storage", "disk", "volume", "persistent"])
    wants_deploy   = any(k in combined_text for k in ["deploy", "replica", "scale", "rollout", "restart", "crashloop", "crash"])
    wants_pods     = any(k in combined_text for k in ["pod", "container", "running", "pending", "failed", "status"])

    # Always include at least pods if nothing matched
    if not any([wants_nodes, wants_cost, wants_security, wants_storage, wants_deploy, wants_pods]):
        wants_pods = True

    slice_data = {
        "metadata": {
            "total_pods": len(snapshot.get("pods", [])),
            "total_nodes": len(snapshot.get("nodes", [])),
            "total_deployments": len(snapshot.get("deployments", [])),
            "total_replicasets": len(snapshot.get("replicasets", [])),
            "total_services": len(snapshot.get("services", [])),
            "total_pvcs": len(snapshot.get("pvcs", [])),
        }
    }

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

    if wants_pods:
        slice_data["pods"] = [
            {
                "name": p.get("name"),
                "namespace": p.get("namespace"),
                "status": p.get("status"),
                "status_phase": p.get("status_phase"),
                "cpu_requested": p.get("cpu_requested"),
                "mem_requested_gb": p.get("mem_requested_gb"),
                "cpu_actual": p.get("cpu_actual"),
                "mem_actual_gb": p.get("mem_actual_gb"),
                "cost_source": p.get("cost_source", "estimated"),
            } for p in snapshot.get("pods", [])
        ]

    if wants_deploy:
        slice_data["deployments"] = snapshot.get("deployments", [])
        slice_data["replicasets"] = snapshot.get("replicasets", [])

    if wants_security:
        slice_data["services"] = snapshot.get("services", [])
        slice_data["secrets"] = [{"name": s.get("name"), "namespace": s.get("namespace")} for s in snapshot.get("secrets", [])]
        slice_data["networkpolicies"] = snapshot.get("networkpolicies", [])
    elif any(k in combined_text for k in ["service", "port"]):
        slice_data["services"] = snapshot.get("services", [])

    if wants_storage:
        slice_data["pvcs"] = snapshot.get("pvcs", [])

    snapshot_json = json.dumps(slice_data, default=str)

    system_prompt = (
        "You are a Kubernetes cluster copilot with access to a live cluster snapshot. "
        "Answer the user's question using the data provided. Be concise and practical. "
        "Use bullet points or bold for clarity. Calculate percentages when asked about utilization.\n\n"
        f"Cluster snapshot:\n{snapshot_json}"
    )
    
    messages = [{"role": "system", "content": system_prompt}]
    
    if history:
        for msg in history:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role in ["user", "assistant"] and content:
                messages.append({"role": role, "content": content})
                
    messages.append({"role": "user", "content": prompt})

    chat_completion = client.chat.completions.create(
        messages=messages,
        model=get_model_name(),
        temperature=0.3,
        max_tokens=1024,
    )
    return chat_completion.choices[0].message.content


def get_security_solution(title: str, description: str, remediation: str, resources: list) -> str:
    system_prompt = (
        "You are an expert Kubernetes security engineer. "
        "Provide a short, actionable solution, specifically a kubectl command or YAML snippet if applicable, "
        "to fix the following Kubernetes security issue. Do not include unnecessary explanations."
    )
    full_prompt = (
        f"Title: {title}\n"
        f"Description: {description}\n"
        f"Remediation: {remediation}\n"
        f"Affected Resources: {', '.join(resources)}"
    )

    chat_completion = client.chat.completions.create(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": full_prompt}
        ],
        model=get_model_name(),
        temperature=0.2,
        max_tokens=1024,
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
                "has_mem_limit": p.get("has_mem_limit"),
                "probes": p.get("probes"),
                "lifecycle_hooks": p.get("lifecycle_hooks")
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
    return {
        "pods": pods, 
        "deployments": deployments,
        "statefulsets": snapshot.get("statefulsets", []),
        "daemonsets": snapshot.get("daemonsets", []),
        "jobs": snapshot.get("jobs", []),
        "hpas": snapshot.get("hpas", [])
    }

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
    return {
        "nodes": nodes, 
        "pods": pods,
        "hpas": snapshot.get("hpas", []),
        "cronjobs": snapshot.get("cronjobs", [])
    }

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
        ],
        "statefulsets": snapshot.get("statefulsets", [])
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
            "has_mem_limit": p.get("has_mem_limit"),
            "runs_as_root": p.get("runs_as_root")
        } for p in snapshot.get("pods", [])
    ]
    deployments = [
        {
            "name": d.get("name"),
            "namespace": d.get("namespace")
        } for d in snapshot.get("deployments", [])
    ]
    return {
        "services": services, 
        "pods": pods, 
        "deployments": deployments,
        "networkpolicies": snapshot.get("networkpolicies", []),
        "ingresses": snapshot.get("ingresses", []),
        "secrets": snapshot.get("secrets", []),
        "configmaps": snapshot.get("configmaps", [])
    }

# ═══════════════════════════════════════
# SECTION 4 — JSON PARSING HELPER
# ═══════════════════════════════════════

def parse_ai_json(response: str) -> dict:
    cleaned = re.sub(r"```json|```", "", response).strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
            except:
                return {"issues": [], "summary": "Failed to parse AI response."}
        else:
            return {"issues": [], "summary": "Failed to parse AI response."}

    # Resilient extraction
    if "analysis" in data and isinstance(data["analysis"], dict):
        data = data["analysis"]
        
    issues = data.get("issues", [])
    if isinstance(issues, dict):
        # AI returned a dict of categories instead of a flat list
        flat_issues = []
        for cat, items in issues.items():
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict):
                        flat_issues.append({
                            "severity": item.get("severity", "warning"),
                            "title": item.get("title", cat.replace("_", " ").title()),
                            "description": item.get("description", f"Detected {cat}"),
                            "affected_resource": item.get("affected_resource") or item.get("name") or "Unknown"
                        })
        issues = flat_issues

    return {
        "issues": issues if isinstance(issues, list) else [],
        "summary": data.get("summary", "Analysis completed.")
    }

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
    
    issues = []
    
    for s in slice_data.get("services", []):
        if s.get("type") in ["NodePort", "LoadBalancer"]:
            issues.append({
                "severity": "critical",
                "title": f"Exposed {s.get('type')} service",
                "description": f"Service {s.get('name')} is exposed as {s.get('type')}, which may pose security risks.",
                "affected_resource": s.get("name")
            })
            
    for p in slice_data.get("pods", []):
        if not p.get("has_cpu_limit") or not p.get("has_mem_limit"):
            issues.append({
                "severity": "warning",
                "title": "Pod missing resource limits",
                "description": f"Pod {p.get('name')} lacks CPU and memory limits, risking resource exhaustion.",
                "affected_resource": p.get("name")
            })
        if p.get("runs_as_root"):
            issues.append({
                "severity": "warning",
                "title": "Pod runs as root",
                "description": f"Pod {p.get('name')} runs as root, increasing security risks.",
                "affected_resource": p.get("name")
            })
            
    summary = f"Detected {len(issues)} security issues including exposed services and pods running with root privileges or missing resource limits."
    
    return {
        "issues": issues,
        "summary": summary
    }

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

    top_issues = deduped_issues

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
