from health import proactive_health_check
from snapshot import snapshot
from cost import enrich_with_cost
from sanitize import sanitize
import json

clean = sanitize(enrich_with_cost(snapshot()))
res = proactive_health_check(clean)
print("TOP ISSUES len:", len(res['top_issues']))
print("Original critical/warning count:", res['critical_count'], res['warning_count'])
