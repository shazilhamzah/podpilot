import time
import json
from snapshot import snapshot
from cost import enrich_with_cost
from sanitize import sanitize
from drift_detection import save_snapshot, load_last_two_snapshots, diff_snapshots

s = sanitize(enrich_with_cost(snapshot()))
save_snapshot(s)
time.sleep(1.1)
save_snapshot(s)
o, n = load_last_two_snapshots()
print("Diffs:", diff_snapshots(o, n))
