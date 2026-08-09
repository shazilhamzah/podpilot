import os
import json
import time
from ai_client import client, get_model_name

SYSTEM_PROMPT = """
You are PodPilot, an expert Kubernetes infrastructure analyst.
You are given a live snapshot of a Kubernetes cluster as JSON.
Your job is to answer questions about this cluster accurately and concisely.

Rules you must follow:
- Always cite specific pod, deployment, service, or PVC names from the 
  snapshot in your answers. Never give generic advice.
- If the data does not support a conclusion, say so explicitly.
- For cost questions always include dollar amounts from the snapshot data.
- For security questions always name the specific resource that is at risk.
- Keep answers concise — 3 to 8 sentences max unless a list is more appropriate.
- Never make up pod names or values not present in the snapshot.
- If a question cannot be answered from the snapshot data alone, say:
  "This information is not available in the current snapshot."
"""

def analyze_all_categories(snapshot: dict) -> dict:
    questions = {
        "cost": "Which pods are wasting the most money based on the difference between requested and actual resource usage? List them with specific dollar amounts per month.",
        "reliability": "Which pods or deployments are unhealthy? Look for crash-looping pods, high restart counts, deployments with zero ready replicas, and missing liveness or readiness probes.",
        "performance": "Are any pods being CPU throttled or starved of resources? Are there any pending pods that cannot be scheduled? Identify specific resources.",
        "storage": "Are there any PVCs that are unattached, in Pending state, or potentially misconfigured? List them by name.",
        "security": "What are the security risks in this cluster? Look for services exposed as NodePort or LoadBalancer, containers that may be running as root, and images using the latest tag. Name every affected resource."
    }

    if not snapshot or not snapshot.get("pods"):
        return {cat: "Snapshot is empty. Please ensure the cluster is running and metrics-server is enabled." for cat in questions}

    snapshot_json = json.dumps(snapshot, default=str)
    
    prompt = f"Here is the current cluster snapshot:\n\n{snapshot_json}\n\n"
    prompt += "Please analyze the snapshot and answer the following questions for each category. "
    prompt += "Return ONLY a valid JSON object with the exact keys: cost, reliability, performance, storage, security. "
    prompt += "The value for each key should be your text response for that category.\n\n"
    for cat, q in questions.items():
        prompt += f"{cat.upper()} QUESTION: {q}\n"

    max_retries = 6
    backoff_factor = 2
    delay = 5  # Start with 5s delay for any transient errors
    
    for attempt in range(max_retries):
        try:
            chat_completion = client.chat.completions.create(
                messages=[
                    {
                        "role": "system",
                        "content": SYSTEM_PROMPT,
                    },
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
                model=get_model_name(),
                temperature=0.2,
                max_tokens=2048,
                response_format={"type": "json_object"},
            )
            return json.loads(chat_completion.choices[0].message.content)
        except Exception as e:
            is_transient = (
                "429" in str(e) or "500" in str(e) or "503" in str(e) or
                any(keyword in str(e).lower() for keyword in ["quota", "overloaded", "temporarily", "unavailable", "demand"])
            )
            if is_transient and attempt < max_retries - 1:
                print(f"Transient error. Retrying in {delay} seconds (attempt {attempt + 1}/{max_retries})...")
                time.sleep(delay)
                delay *= backoff_factor
                continue
            return {cat: f"Error contacting Azure OpenAI API: {e}" for cat in questions}
            
    return {cat: "Max retries exceeded" for cat in questions}

if __name__ == "__main__":
    from snapshot import snapshot
    from cost import enrich_with_cost
    from sanitize import sanitize

    print("Building snapshot pipeline...")
    clean = sanitize(enrich_with_cost(snapshot()))
    print(f"Snapshot ready — {len(clean.get('pods', []))} pods loaded\n")

    print("Sending snapshot to Azure OpenAI for full analysis...\n")
    results = analyze_all_categories(clean)

    categories = ["cost", "reliability", "performance", "storage", "security"]

    for cat in categories:
        print(f"{'='*50}")
        print(f"CATEGORY: {cat.upper()}")
        print(f"{'='*50}")
        print(results.get(cat, "No analysis returned for this category."))
        print()
