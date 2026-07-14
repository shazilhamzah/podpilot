import re, json

response = """Based on the provided cluster snapshot, here is the requested JSON response:


```json
{
  "issues": [
    {
      "severity": "critical",
      "title": "Oversized deployment 'oversized-deployment-998dc6964-zxzvt'",
     "description": "Pod 'oversized-deployment-998dc6964-zxzvt' is requesting 0.5 GB memory, but only using 0.00292 GB, resulting in a wasted cost of $20.41/month.",
     "affected_resource": "oversized-deployment-998dc6964-zxzvt"
    }
  ],
  "summary": "Two resources in the cluster are wasting cost."
}
``` 
"""

def parse_ai_json(response: str) -> dict:
    cleaned = re.sub(r"```json|```", "", response).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        print(f"JSONDecodeError: {e}")
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            print("Match found")
            try:
                return json.loads(match.group())
            except Exception as e2:
                print(f"Regex json.loads error: {e2}")
                pass
    return {"issues": [], "summary": "Failed to parse AI response."}

res = parse_ai_json(response)
print("Result:", res)
