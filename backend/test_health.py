from health import proactive_health_check
from snapshot import snapshot
from cost import enrich_with_cost
from sanitize import sanitize
import json

clean = sanitize(enrich_with_cost(snapshot()))
print(f"Total pods: {len(clean['pods'])}")
res = proactive_health_check(clean)
print(f"Top Issues len: {len(res['top_issues'])}")
print(f"Category counts in Top Issues:")
cats = {}
for i in res['top_issues']:
    cats[i.get('category')] = cats.get(i.get('category'), 0) + 1
print(cats)
