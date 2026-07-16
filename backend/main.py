import os
import time
import json
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

from snapshot import snapshot
from cost import enrich_with_cost
from sanitize import sanitize
from health import (
    analyze,
    proactive_health_check,
    analyze_cost,
    analyze_reliability,
    analyze_performance,
    analyze_storage,
    analyze_security,
    chat_with_cluster
)
from trivy import scan_all_images, trivy_ai_summary, trivy_to_issues
from drift_detection import (
    save_snapshot,
    load_last_two_snapshots,
    load_target_and_previous_snapshot,
    diff_snapshots,
    summarize_diff,
    explain_drift
)

load_dotenv(override=True)

app = FastAPI(title="PodPilot API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

from typing import Optional
class ChatRequest(BaseModel):
    question: str
    snapshot_id: Optional[str] = None

class SolutionRequest(BaseModel):
    title: str
    description: str
    remediation: str
    resources: list[str]

class SnapshotCreateRequest(BaseModel):
    name: Optional[str] = None
    comments: Optional[str] = None

class RefreshResponse(BaseModel):
    status: str
    pod_count: int
    refreshed_at: str

from db import db

POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "300"))

# In-memory fast cache as a fallback/accelerator
_in_memory_cache = None

async def load_cache() -> dict:
    global _in_memory_cache
    if _in_memory_cache is not None:
        return _in_memory_cache
        
    default_cache = {
        "snapshot": None,
        "last_updated": None,
        "analysis_results": {}
    }
    if db is None:
        _in_memory_cache = default_cache
        return _in_memory_cache
        
    try:
        doc = await db.cache.find_one({"_id": "app_cache"})
        if doc:
            doc.pop("_id", None)
            _in_memory_cache = doc
            return _in_memory_cache
    except Exception as e:
        print(f"[CACHE DB] Error loading cache from db: {e}")
        
    _in_memory_cache = default_cache
    return _in_memory_cache

async def save_cache(cache_data: dict):
    global _in_memory_cache
    _in_memory_cache = cache_data
    if db is None:
        return
    try:
        await db.cache.update_one(
            {"_id": "app_cache"},
            {"$set": cache_data},
            upsert=True
        )
    except Exception as e:
        print(f"[CACHE DB] Error saving cache to db: {e}")

def _structural_fingerprint(snap: dict) -> dict:
    """Extract only structural fields for cache invalidation.
    Ignores floating-point metrics that fluctuate on every poll."""
    return {
        "pods": sorted([
            {"name": p.get("name"), "namespace": p.get("namespace"),
             "status": p.get("status_phase") or p.get("status"),
             "restart_count": p.get("restart_count")}
            for p in snap.get("pods", [])
        ], key=lambda x: x.get("name", "")),
        "deployments": sorted([
            {"name": d.get("name"), "desired": d.get("desired_replicas"), "ready": d.get("ready_replicas")}
            for d in snap.get("deployments", [])
        ], key=lambda x: x.get("name", "")),
        "services": sorted([s.get("name") for s in snap.get("services", [])]),
        "pvcs": sorted([{"name": pvc.get("name"), "status": pvc.get("status")} for pvc in snap.get("pvcs", [])], key=lambda x: x.get("name", "")),
        "node_count": len(snap.get("nodes", [])),
    }

async def get_cached_snapshot(snapshot_id: Optional[str] = None) -> dict:
    if snapshot_id:
        from bson import ObjectId
        doc = await db.snapshots.find_one({"_id": ObjectId(snapshot_id)})
        if doc:
            return doc.get("snapshot", {})
        raise Exception("Snapshot not found")

    cache = await load_cache()
    now = time.time()
    if cache["snapshot"] is None or cache["last_updated"] is None or (now - cache["last_updated"] > POLL_INTERVAL_SECONDS):
        try:
            raw_snap = snapshot()
            enriched = enrich_with_cost(raw_snap)
            clean_snap = sanitize(enriched)
            
            old_snap = cache.get("snapshot")
            if old_snap is not None:
                # Only invalidate analysis cache when cluster structure changes,
                # not when metrics (CPU %, memory usage) fluctuate
                old_fp = _structural_fingerprint(old_snap)
                new_fp = _structural_fingerprint(clean_snap)
                if old_fp != new_fp:
                    try:
                        changes = diff_snapshots(old_snap, clean_snap)
                        diff_summary = summarize_diff(changes)
                        print(f"[CACHE INVALIDATION] Structural change detected! Diff: {diff_summary}")
                    except Exception as diff_err:
                        print(f"[CACHE INVALIDATION] Structural change detected! (diff error: {diff_err})")
                    cache["analysis_results"] = {}
                else:
                    print("[CACHE] Metrics updated, structure unchanged — keeping analysis cache.")
            else:
                print("[CACHE INIT] Initial snapshot cached.")
                cache["analysis_results"] = {}

            cache["snapshot"] = clean_snap
            cache["last_updated"] = now
            await save_cache(cache)
        except Exception as e:
            raise Exception(f"Failed to build snapshot: {str(e)}")

    return cache["snapshot"]

async def get_cached_analysis(key: str, compute_fn, snapshot_id: Optional[str] = None):
    if snapshot_id:
        from bson import ObjectId
        doc = await db.snapshots.find_one({"_id": ObjectId(snapshot_id)})
        if not doc:
            raise Exception("Snapshot not found")
            
        analysis_results = doc.get("analysis_results", {})
        if key in analysis_results:
            print(f"[DB HIT] Serving historical '{key}' from db.snapshots.")
            return analysis_results[key]
            
        print(f"[GROQ REQUEST] Historical miss for '{key}'. Sending request to Groq API...")
        result = compute_fn(doc.get("snapshot", {}))
        
        await db.snapshots.update_one(
            {"_id": ObjectId(snapshot_id)},
            {"$set": {f"analysis_results.{key}": result}}
        )
        return result

    snap = await get_cached_snapshot()
    cache = await load_cache()
    
    if "analysis_results" not in cache:
        cache["analysis_results"] = {}
        
    if key not in cache["analysis_results"]:
        print(f"[GROQ REQUEST] Cache miss for '{key}'. Sending request to Groq API...")
        cache["analysis_results"][key] = compute_fn(snap)
        await save_cache(cache)
    else:
        print(f"[CACHE HIT] Serving '{key}' from cache.")
        
    return cache["analysis_results"][key]

async def get_cached_analysis_async(key: str, compute_fn, snapshot_id: Optional[str] = None):
    if snapshot_id:
        from bson import ObjectId
        doc = await db.snapshots.find_one({"_id": ObjectId(snapshot_id)})
        if not doc:
            raise Exception("Snapshot not found")
            
        analysis_results = doc.get("analysis_results", {})
        if key in analysis_results:
            print(f"[DB HIT] Serving historical '{key}' from db.snapshots.")
            return analysis_results[key]
            
        print(f"[GROQ REQUEST] Historical miss for '{key}'. Sending async request...")
        result = await compute_fn(doc.get("snapshot", {}))
        
        await db.snapshots.update_one(
            {"_id": ObjectId(snapshot_id)},
            {"$set": {f"analysis_results.{key}": result}}
        )
        return result

    snap = await get_cached_snapshot()
    cache = await load_cache()
    
    if "analysis_results" not in cache:
        cache["analysis_results"] = {}
        
    if key not in cache["analysis_results"]:
        print(f"[GROQ REQUEST] Cache miss for '{key}'. Sending async request...")
        cache["analysis_results"][key] = await compute_fn(snap)
        await save_cache(cache)
    else:
        print(f"[CACHE HIT] Serving '{key}' from cache.")
        
    return cache["analysis_results"][key]

@app.on_event("startup")
async def startup_event():
    print("PodPilot API starting up...")
    print("Pre-warming snapshot cache...")
    try:
        snap = await get_cached_snapshot()
        print(f"Cache ready — {len(snap.get('pods', []))} pods loaded")
    except Exception as e:
        print(f"Failed to pre-warm cache: {e}")

@app.get("/")
async def root():
    try:
        return {
            "status": "ok",
            "service": "PodPilot API",
            "version": "1.0.0"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": str(e), "endpoint": "/"})

@app.get("/snapshot")
async def get_snapshot(snapshot_id: Optional[str] = None):
    try:
        if snapshot_id:
            from bson import ObjectId
            doc = await db.snapshots.find_one({"_id": ObjectId(snapshot_id)})
            if not doc:
                raise HTTPException(status_code=404, detail="Snapshot not found")
            snap = doc.get("snapshot", {})
            cached_at = doc.get("captured_at")
        else:
            snap = await get_cached_snapshot()
            cache = await load_cache()
            last_updated_ts = cache.get("last_updated")
            cached_at = datetime.fromtimestamp(last_updated_ts, timezone.utc).isoformat() if last_updated_ts else None
            
        return {
            "data": snap,
            "cached_at": cached_at,
            "pod_count": len(snap.get("pods", [])),
            "node_count": len(snap.get("nodes", []))
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": str(e), "endpoint": "/snapshot"})

@app.get("/history")
async def get_history():
    try:
        # Fetch snapshots sorted by captured_at descending, including analysis_results to see what is cached
        cursor = db.snapshots.find({}, {"_id": 1, "name": 1, "comments": 1, "captured_at": 1, "analysis_results": 1}).sort("captured_at", -1)
        history = []
        async for doc in cursor:
            doc["id"] = str(doc["_id"])
            del doc["_id"]
            doc["cached_analyses"] = list(doc.get("analysis_results", {}).keys())
            if "analysis_results" in doc:
                del doc["analysis_results"]
            history.append(doc)
        return {"snapshots": history}
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": str(e), "endpoint": "/history"})

@app.get("/health")
async def get_health(snapshot_id: Optional[str] = None):
    try:
        return await get_cached_analysis("health", proactive_health_check, snapshot_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": str(e), "endpoint": "/health"})

@app.post("/chat")
async def chat(request: ChatRequest):
    try:
        from bson import ObjectId
        
        # Determine which snapshot to use
        if request.snapshot_id:
            try:
                snap_doc = await db.snapshots.find_one({"_id": ObjectId(request.snapshot_id)})
                if not snap_doc:
                    raise HTTPException(status_code=404, detail="Snapshot not found")
                snap = snap_doc.get("snapshot", {})
                age = 0 # Historical
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Invalid snapshot ID: {e}")
        else:
            snap = await get_cached_snapshot()
            cache = await load_cache()
            age = int(time.time() - cache["last_updated"]) if cache["last_updated"] else 0

        ans = chat_with_cluster(request.question, snap)
        return {
            "question": request.question,
            "answer": ans,
            "snapshot_age_seconds": age,
            "snapshot_id": request.snapshot_id or "latest"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": str(e), "endpoint": "/chat"})

@app.post("/solution")
async def get_solution(request: SolutionRequest):
    try:
        from health import get_security_solution
        ans = get_security_solution(
            title=request.title,
            description=request.description,
            remediation=request.remediation,
            resources=request.resources
        )
        return {"answer": ans}
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": str(e), "endpoint": "/solution"})

@app.get("/cost")
async def cost(snapshot_id: Optional[str] = None):
    try:
        return await get_cached_analysis("cost", analyze_cost, snapshot_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": str(e), "endpoint": "/cost"})

@app.get("/reliability")
async def reliability(snapshot_id: Optional[str] = None):
    try:
        return await get_cached_analysis("reliability", analyze_reliability, snapshot_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": str(e), "endpoint": "/reliability"})

@app.get("/performance")
async def performance(snapshot_id: Optional[str] = None):
    try:
        return await get_cached_analysis("performance", analyze_performance, snapshot_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": str(e), "endpoint": "/performance"})

@app.get("/storage")
async def storage(snapshot_id: Optional[str] = None):
    try:
        return await get_cached_analysis("storage", analyze_storage, snapshot_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": str(e), "endpoint": "/storage"})

@app.get("/security")
async def security(snapshot_id: Optional[str] = None):
    try:
        def compute_security(snap):
            existing_result = analyze_security(snap)
            trivy_result = scan_all_images(snap)
            trivy_issues = trivy_to_issues(trivy_result)
            
            # merge trivy issues into existing security issues
            existing_result["issues"] = existing_result.get("issues", []) + trivy_issues
            return existing_result
        return await get_cached_analysis("security", compute_security, snapshot_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": str(e), "endpoint": "/security"})

@app.get("/trivy")
async def trivy_scan(snapshot_id: Optional[str] = None):
    # WARNING: This endpoint is SLOW (1-3 minutes on first call due to Trivy DB download).
    try:
        def compute_trivy(snap):
            scan_results = scan_all_images(snap)
            ai_summary = trivy_ai_summary(scan_results)
            issues = trivy_to_issues(scan_results)
            return {
                "scan_results": scan_results,
                "ai_summary": ai_summary,
                "issues": issues
            }
        return await get_cached_analysis("trivy", compute_trivy, snapshot_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": str(e), "endpoint": "/trivy"})

@app.get("/drift")
async def drift(snapshot_id: Optional[str] = None):
    try:
        # If no snapshot_id provided, default to live ("latest")
        sid = snapshot_id if snapshot_id else "latest"
        
        # We need an async wrapper because get_cached_analysis expects an async function
        async def compute_drift_async(snap):
            older, newer = await load_target_and_previous_snapshot(sid)
            if older is None:
                return {
                    "status": "first_snapshot",
                    "message": "First snapshot taken, nothing to compare yet.",
                    "diff_summary": None,
                    "ai_explanation": None,
                    "changes_detected": 0
                }
            changes = diff_snapshots(older, newer)
            diff_summary = summarize_diff(changes)
            ai_explanation = explain_drift(diff_summary)
            return {
                "status": "success",
                "message": "Compared current snapshot with previous.",
                "diff_summary": diff_summary,
                "ai_explanation": ai_explanation,
                "changes_detected": len(changes)
            }
            
        return await get_cached_analysis_async("drift", compute_drift_async, snapshot_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": str(e), "endpoint": "/drift"})

@app.get("/compare")
async def compare(snap_a: str, snap_b: str):
    try:
        from bson import ObjectId
        doc_a = await db.snapshots.find_one({"_id": ObjectId(snap_a)})
        doc_b = await db.snapshots.find_one({"_id": ObjectId(snap_b)})
        if not doc_a or not doc_b:
            raise HTTPException(status_code=404, detail="One or both snapshots not found")
            
        snap_a_data = doc_a.get("snapshot", {})
        snap_b_data = doc_b.get("snapshot", {})
        
        changes = diff_snapshots(snap_a_data, snap_b_data)
        diff_summary = summarize_diff(changes)
        
        if not changes:
            return {
                "status": "success",
                "message": "Snapshots are identical.",
                "diff_summary": "",
                "ai_explanation": "No changes detected.",
                "changes_detected": 0
            }
            
        ai_explanation = explain_drift(diff_summary)
        
        return {
            "status": "success",
            "message": "Compared snapshots.",
            "diff_summary": diff_summary,
            "ai_explanation": ai_explanation,
            "changes_detected": len(changes)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": str(e), "endpoint": "/compare"})

@app.post("/refresh", response_model=RefreshResponse)
async def refresh(request: Optional[SnapshotCreateRequest] = None):
    try:
        now = time.time()
        raw_snap = snapshot()
        enriched = enrich_with_cost(raw_snap)
        clean_snap = sanitize(enriched)
        
        name = request.name if request else None
        comments = request.comments if request else None
        
        cache = await load_cache()
        
        analysis_results_to_save = {}
        old_snap = cache.get("snapshot")
        if old_snap is not None:
            old_fp = _structural_fingerprint(old_snap)
            new_fp = _structural_fingerprint(clean_snap)
            if old_fp != new_fp:
                try:
                    changes = diff_snapshots(old_snap, clean_snap)
                    diff_summary = summarize_diff(changes)
                    print(f"[CACHE INVALIDATION] Structural change detected on refresh! Diff: {diff_summary}")
                except Exception as diff_err:
                    print(f"[CACHE INVALIDATION] Structural change detected on refresh! (diff error: {diff_err})")
                cache["analysis_results"] = {}
            else:
                print("[CACHE] Metrics updated, structure unchanged — keeping analysis cache on refresh.")
                latest_doc = await db.snapshots.find_one({}, sort=[("captured_at", -1)])
                db_analysis = latest_doc.get("analysis_results", {}) if latest_doc else {}
                analysis_results_to_save = {**db_analysis, **cache.get("analysis_results", {})}
        else:
            print("[CACHE INIT] Initial snapshot cached on refresh.")
            cache["analysis_results"] = {}
            
        # Explicitly save this manually triggered snapshot
        await save_snapshot(clean_snap, name, comments, analysis_results=analysis_results_to_save)
            
        cache["snapshot"] = clean_snap
        cache["last_updated"] = now
        await save_cache(cache)
        
        refreshed_at = datetime.fromtimestamp(now, timezone.utc).isoformat()
        
        return RefreshResponse(
            status="refreshed",
            pod_count=len(clean_snap.get("pods", [])),
            refreshed_at=refreshed_at
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": str(e), "endpoint": "/refresh"})
