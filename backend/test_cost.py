import json
from snapshot import snapshot
from cost import enrich_with_cost
from sanitize import sanitize
from health import analyze_cost, slice_cost, analyze

print("Building snapshot...")
clean = sanitize(enrich_with_cost(snapshot()))

print("Running analyze_cost...")
slice_data = slice_cost(clean)

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
print("--- RAW AI RESPONSE ---")
print(response)
print("-----------------------")

