import os
import json
import google.generativeai as genai
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure Gemini
api_key = os.getenv("GEMINI_API_KEY")
if api_key:
    genai.configure(api_key=api_key)

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

def analyze(question: str, snapshot: dict) -> str:
    if not snapshot or not snapshot.get("pods"):
        return "Snapshot is empty. Please ensure the cluster is running and metrics-server is enabled."

    snapshot_json = json.dumps(snapshot, default=str)
    
    user_content = f"Here is the current cluster snapshot:\n\n{snapshot_json}\n\nQuestion: {question}"
    
    try:
        model = genai.GenerativeModel(
            model_name="gemini-2.5-flash",
            system_instruction=SYSTEM_PROMPT
        )
        response = model.generate_content(
            user_content,
            generation_config=genai.types.GenerationConfig(
                max_output_tokens=1024,
                temperature=0.2
            )
        )
        return response.text
    except Exception as e:
        return f"Error contacting Gemini API: {e}"

def analyze_category(category: str, snapshot: dict) -> str:
    questions = {
        "cost": "Which pods are wasting the most money based on the difference between requested and actual resource usage? List them with specific dollar amounts per month.",
        "reliability": "Which pods or deployments are unhealthy? Look for crash-looping pods, high restart counts, deployments with zero ready replicas, and missing liveness or readiness probes.",
        "performance": "Are any pods being CPU throttled or starved of resources? Are there any pending pods that cannot be scheduled? Identify specific resources.",
        "storage": "Are there any PVCs that are unattached, in Pending state, or potentially misconfigured? List them by name.",
        "security": "What are the security risks in this cluster? Look for services exposed as NodePort or LoadBalancer, containers that may be running as root, and images using the latest tag. Name every affected resource."
    }
    
    question = questions.get(category)
    if not question:
        return "Unknown category. Valid options: cost, reliability, performance, storage, security"
        
    return analyze(question, snapshot)

if __name__ == "__main__":
    from snapshot import snapshot
    from cost import enrich_with_cost
    from sanitize import sanitize

    print("Building snapshot pipeline...")
    clean = sanitize(enrich_with_cost(snapshot()))
    print(f"Snapshot ready — {len(clean.get('pods', []))} pods loaded\n")

    categories = ["cost", "reliability", "performance", "storage", "security"]

    for cat in categories:
        print(f"{'='*50}")
        print(f"CATEGORY: {cat.upper()}")
        print(f"{'='*50}")
        answer = analyze_category(cat, clean)
        print(answer)
        print()
