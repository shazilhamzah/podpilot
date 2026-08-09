"""
drift_detection.py
Podpilot - Phase 6: Drift Detection

Saves timestamped sanitized snapshots to disk, diffs the last two in plain
Python, and (only if something actually changed) asks Groq to explain the
impact of the detected changes. Groq never sees raw JSON -- only the plain
English diff string produced by diff_snapshots() + summarize_diff().

Requires:
    pip install groq

Environment:
    AI_API_KEY must be set (e.g. in a .env file or your shell environment)

Usage from main.py:
    from drift_detection import save_snapshot, load_last_two_snapshots, \
        diff_snapshots, summarize_diff, explain_drift

    @app.get("/drift/poll")
    def poll_drift():
        sanitized = sanitize_snapshot(snapshot())
        save_snapshot(sanitized)

        older, newer = load_last_two_snapshots()
        if older is None:
            return {"status": "first snapshot taken, nothing to compare yet"}

        changes = diff_snapshots(older, newer)
        diff_summary = summarize_diff(changes)
        ai_explanation = explain_drift(diff_summary)

        return {
            "changes_detected": len(changes),
            "diff_summary": diff_summary,
            "ai_explanation": ai_explanation,
        }
"""

import os
import json
import time
from datetime import datetime, timezone
from dotenv import load_dotenv
from ai_client import client, get_model_name
from openai import RateLimitError

load_dotenv(override=True)
SNAPSHOT_DIR = "snapshots"


from db import db

# ---------------------------------------------------------------------------
# Step 1: save a timestamped sanitized snapshot to database
# ---------------------------------------------------------------------------

async def save_snapshot(sanitized: dict, name: str = None, comments: str = None, analysis_results: dict = None) -> str:
    """Writes a sanitized snapshot to MongoDB with a timestamp, name, and comments.
    Returns the ObjectId string."""
    if db is None:
        print("[WARNING] Database not connected. Snapshot not saved.")
        return ""
        
    ts = datetime.now(timezone.utc).isoformat()
    if not name:
        name = f"snapshot_{int(time.time())}"
    if comments is None:
        comments = ""
        
    doc = {
        "captured_at": ts,
        "name": name,
        "comments": comments,
        "snapshot": sanitized,
        "analysis_results": analysis_results or {}
    }
    result = await db.snapshots.insert_one(doc)
    return str(result.inserted_id)


async def load_last_two_snapshots():
    """Returns (older, newer) sanitized dicts. Returns (None, latest) if
    only one snapshot exists yet, or (None, None) if there are none."""
    if db is None:
        return None, None
        
    cursor = db.snapshots.find().sort("captured_at", -1).limit(2)
    docs = await cursor.to_list(length=2)
    
    if len(docs) == 0:
        return None, None
    elif len(docs) == 1:
        return None, docs[0]["snapshot"]
    else:
        # docs is sorted newest first, so docs[1] is older, docs[0] is newer
        return docs[1]["snapshot"], docs[0]["snapshot"]

async def load_target_and_previous_snapshot(snapshot_id: str):
    """Returns (older, newer) sanitized dicts for a specific target snapshot.
    If target is the first snapshot, older will be None."""
    from bson.objectid import ObjectId
    if db is None:
        return None, None
        
    if snapshot_id == "latest":
        return await load_last_two_snapshots()
        
    try:
        target_doc = await db.snapshots.find_one({"_id": ObjectId(snapshot_id)})
        if not target_doc:
            return None, None
            
        target_time = target_doc.get("captured_at")
        cursor = db.snapshots.find({"captured_at": {"$lt": target_time}}).sort("captured_at", -1).limit(1)
        prev_docs = await cursor.to_list(length=1)
        
        older = prev_docs[0]["snapshot"] if prev_docs else None
        newer = target_doc["snapshot"]
        
        return older, newer
    except Exception:
        return None, None


# ---------------------------------------------------------------------------
# Step 2: diff two snapshots in plain Python -- no AI involved
# ---------------------------------------------------------------------------

def _index_by_key(items: list, key_fields: list) -> dict:
    return {tuple(item[k] for k in key_fields): item for item in items}


def diff_snapshots(older: dict, newer: dict) -> list:
    """Compares two sanitized snapshots and returns a list of plain-English
    change descriptions. Returns an empty list if nothing changed."""
    changes = []

    # Deployments: replica count changes
    old_deploys = _index_by_key(older["deployments"], ["namespace", "name"])
    new_deploys = _index_by_key(newer["deployments"], ["namespace", "name"])
    for key, new_d in new_deploys.items():
        old_d = old_deploys.get(key)
        if old_d and old_d["desired_replicas"] != new_d["desired_replicas"]:
            changes.append(
                f"deployment/{new_d['name']} (ns: {new_d['namespace']}) replicas: "
                f"{old_d['desired_replicas']} -> {new_d['desired_replicas']}"
            )

    # Pods: new, removed, restarts, status changes
    old_pods = _index_by_key(older["pods"], ["namespace", "name"])
    new_pods = _index_by_key(newer["pods"], ["namespace", "name"])
    for key, new_p in new_pods.items():
        old_p = old_pods.get(key)
        if not old_p:
            changes.append(f"pod/{new_p['name']} (ns: {new_p['namespace']}) is new")
            continue
        if old_p["restart_count"] != new_p["restart_count"]:
            changes.append(
                f"pod/{new_p['name']} restart count: {old_p['restart_count']} -> {new_p['restart_count']}"
            )
        if old_p["status"] != new_p["status"]:
            changes.append(
                f"pod/{new_p['name']} status: {old_p['status']} -> {new_p['status']}"
            )
    for key, old_p in old_pods.items():
        if key not in new_pods:
            changes.append(f"pod/{old_p['name']} (ns: {old_p['namespace']}) was removed")

    # Services: type changes -- using .get() defensively until confirmed
    old_svcs = _index_by_key(older.get("services", []), ["namespace", "name"])
    new_svcs = _index_by_key(newer.get("services", []), ["namespace", "name"])
    for key, new_s in new_svcs.items():
        old_s = old_svcs.get(key)
        if old_s and old_s.get("type") != new_s.get("type"):
            changes.append(
                f"service/{new_s['name']} type: {old_s.get('type')} -> {new_s.get('type')}"
            )

    # PVCs: status changes -- using .get() defensively until confirmed
    old_pvcs = _index_by_key(older.get("pvcs", []), ["namespace", "name"])
    new_pvcs = _index_by_key(newer.get("pvcs", []), ["namespace", "name"])
    for key, new_v in new_pvcs.items():
        old_v = old_pvcs.get(key)
        if old_v and old_v.get("status") != new_v.get("status"):
            changes.append(
                f"pvc/{new_v['name']} status: {old_v.get('status')} -> {new_v.get('status')}"
            )

    return changes

def summarize_diff(changes: list) -> str:
    """Joins the change list into one plain-text block for the AI prompt.
    Returns an empty string if there are no changes -- this is what
    explain_drift() checks to decide whether to call the API at all."""
    if not changes:
        return ""
    return "\n".join(f"- {c}" for c in changes)


# ---------------------------------------------------------------------------
# Step 3: only call Groq if there's an actual diff
# ---------------------------------------------------------------------------

def explain_drift(diff_summary: str, max_retries: int = 3) -> str:
    """Sends ONLY the plain-English diff string to Groq -- never raw JSON.
    Returns immediately with no API call if nothing changed, which is what
    protects your free-tier quota from being burned on empty poll cycles."""
    if not diff_summary:
        return "No drift detected."

    system_prompt = (
        "You are Podpilot's drift analyst. You will be given a list of "
        "changes detected in a Kubernetes cluster between two snapshots. "
        "Explain, in 2-3 sentences per change, what likely caused it and "
        "whether it needs attention. Be concise and specific."
    )

    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=get_model_name(),
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": diff_summary},
                ],
                max_completion_tokens=400,
            )
            return response.choices[0].message.content
        except RateLimitError:
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
            else:
                return "Drift detected, but the AI explanation is unavailable right now (rate limited)."