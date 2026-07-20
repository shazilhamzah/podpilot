import os
import time
import json
from datetime import datetime, timezone
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
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
from trivy import scan_all_images, trivy_ai_summary, trivy_to_issues, warm_trivy_cache
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
    hide_system: Optional[bool] = False

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
            loop = asyncio.get_event_loop()
            raw_snap = await loop.run_in_executor(None, snapshot)
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

def filter_system_resources(snap: dict) -> dict:
    SYSTEM_NAMESPACES = {'kube-system', 'kube-public', 'kube-node-lease'}
    filtered = {
        "captured_at": snap.get("captured_at"),
        "cluster_name": snap.get("cluster_name"),
        "nodes": snap.get("nodes", []),
    }
    filtered["pods"] = [p for p in snap.get("pods", []) if p.get("namespace") not in SYSTEM_NAMESPACES]
    filtered["deployments"] = [d for d in snap.get("deployments", []) if d.get("namespace") not in SYSTEM_NAMESPACES]
    filtered["services"] = [s for s in snap.get("services", []) if s.get("namespace") not in SYSTEM_NAMESPACES]
    filtered["pvcs"] = [p for p in snap.get("pvcs", []) if p.get("namespace") not in SYSTEM_NAMESPACES]
    
    total_cost_per_hour = sum(p.get("cost_per_hour", 0.0) for p in filtered["pods"])
    total_wasted_per_hour = sum(p.get("wasted_cost_per_hour", 0.0) for p in filtered["pods"])
    total_wasted_per_month = total_wasted_per_hour * 730
    
    filtered["cost_summary"] = {
        "total_cost_per_hour": total_cost_per_hour,
        "total_wasted_per_hour": total_wasted_per_hour,
        "total_wasted_per_month": total_wasted_per_month
    }
    return filtered

def enrich_issues_with_namespaces(result: dict, snap: dict) -> dict:
    if not result or "issues" not in result:
        return result
    resource_ns = {}
    for p in snap.get("pods", []):
        if p.get("name") and p.get("namespace"):
            resource_ns[p["name"]] = p["namespace"]
    for d in snap.get("deployments", []):
        if d.get("name") and d.get("namespace"):
            resource_ns[d["name"]] = d["namespace"]
    for s in snap.get("services", []):
        if s.get("name") and s.get("namespace"):
            resource_ns[s["name"]] = s["namespace"]
    for pvc in snap.get("pvcs", []):
        if pvc.get("name") and pvc.get("namespace"):
            resource_ns[pvc["name"]] = pvc["namespace"]

    image_ns = {}
    for p in snap.get("pods", []):
        ns = p.get("namespace")
        if ns:
            for img in p.get("images", []):
                if img not in image_ns:
                    image_ns[img] = set()
                image_ns[img].add(ns)
            img = p.get("image")
            if img:
                if img not in image_ns:
                    image_ns[img] = set()
                image_ns[img].add(ns)

    for issue in result["issues"]:
        res_name = issue.get("affected_resource")
        if not res_name:
            continue
        if res_name in resource_ns:
            issue["namespace"] = resource_ns[res_name]
            continue
        found = False
        for k, ns in resource_ns.items():
            if k in res_name or res_name in k:
                issue["namespace"] = ns
                found = True
                break
        if found:
            continue
        if res_name in image_ns:
            issue["namespace"] = list(image_ns[res_name])[0]
            continue
        for img, namespaces in image_ns.items():
            if img in res_name or res_name in img:
                issue["namespace"] = list(namespaces)[0]
                found = True
                break
        if found:
            continue
    return result

async def get_cached_analysis(key: str, compute_fn, snapshot_id: Optional[str] = None):
    import asyncio
    loop = asyncio.get_event_loop()
    
    if snapshot_id:
        from bson import ObjectId
        doc = await db.snapshots.find_one({"_id": ObjectId(snapshot_id)})
        if not doc:
            raise Exception("Snapshot not found")
        
        analysis_results = doc.get("analysis_results", {})
        if key in analysis_results:
            print(f"[DB HIT] Serving historical '{key}' from db.snapshots.")
            return enrich_issues_with_namespaces(analysis_results[key], doc.get("snapshot", {}))
            
        print(f"[GROQ REQUEST] Historical miss for '{key}'. Sending request to Groq API...")
        result = await loop.run_in_executor(None, compute_fn, doc.get("snapshot", {}))
        
        await db.snapshots.update_one(
            {"_id": ObjectId(snapshot_id)},
            {"$set": {f"analysis_results.{key}": result}}
        )
        return enrich_issues_with_namespaces(result, doc.get("snapshot", {}))

    snap = await get_cached_snapshot()
    cache = await load_cache()
    
    if "analysis_results" not in cache:
        cache["analysis_results"] = {}
        
    if key not in cache["analysis_results"]:
        print(f"[GROQ REQUEST] Cache miss for '{key}'. Sending request to Groq API...")
        cache["analysis_results"][key] = await loop.run_in_executor(None, compute_fn, snap)
        await save_cache(cache)
    else:
        print(f"[CACHE HIT] Serving '{key}' from cache.")
        
    return enrich_issues_with_namespaces(cache["analysis_results"][key], snap)

async def get_cached_analysis_async(key: str, compute_fn, snapshot_id: Optional[str] = None):
    if snapshot_id:
        from bson import ObjectId
        doc = await db.snapshots.find_one({"_id": ObjectId(snapshot_id)})
        if not doc:
            raise Exception("Snapshot not found")
            
        analysis_results = doc.get("analysis_results", {})
        if key in analysis_results:
            print(f"[DB HIT] Serving historical '{key}' from db.snapshots.")
            return enrich_issues_with_namespaces(analysis_results[key], doc.get("snapshot", {}))
            
        print(f"[GROQ REQUEST] Historical miss for '{key}'. Sending async request...")
        result = await compute_fn(doc.get("snapshot", {}))
        
        await db.snapshots.update_one(
            {"_id": ObjectId(snapshot_id)},
            {"$set": {f"analysis_results.{key}": result}}
        )
        return enrich_issues_with_namespaces(result, doc.get("snapshot", {}))

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
        
    return enrich_issues_with_namespaces(cache["analysis_results"][key], snap)

@app.on_event("startup")
async def startup_event():
    print("PodPilot API starting up...")
    print("Pre-warming snapshot cache...")
    try:
        snap = await get_cached_snapshot()
        print(f"Cache ready — {len(snap.get('pods', []))} pods loaded")
    except Exception as e:
        print(f"Failed to pre-warm cache: {e}")
    print("Pre-warming Trivy image scan cache from MongoDB...")
    await warm_trivy_cache()

@app.get("/api/status")
async def root():
    try:
        return {
            "status": "ok",
            "service": "PodPilot API",
            "version": "1.0.0"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": str(e), "endpoint": "/api/status"})

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

        if request.hide_system:
            snap = filter_system_resources(snap)

        import asyncio
        loop = asyncio.get_event_loop()
        ans = await loop.run_in_executor(None, chat_with_cluster, request.question, snap)
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
        import asyncio
        loop = asyncio.get_event_loop()
        ans = await loop.run_in_executor(
            None, 
            get_security_solution, 
            request.title, 
            request.description, 
            request.remediation, 
            request.resources
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
        async def compute_security(snap):
            existing_result = analyze_security(snap)
            trivy_result = await scan_all_images(snap)
            trivy_issues = trivy_to_issues(trivy_result)

            # merge trivy issues into existing security issues
            existing_result["issues"] = existing_result.get("issues", []) + trivy_issues
            return existing_result
        return await get_cached_analysis_async("security", compute_security, snapshot_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": str(e), "endpoint": "/security"})

@app.get("/trivy")
async def trivy_scan(snapshot_id: Optional[str] = None):
    # First call may be slow if images are not yet cached in MongoDB.
    try:
        async def compute_trivy(snap):
            scan_results = await scan_all_images(snap)
            ai_summary = trivy_ai_summary(scan_results)
            issues = trivy_to_issues(scan_results)
            return {
                "scan_results": scan_results,
                "ai_summary": ai_summary,
                "issues": issues
            }
        return await get_cached_analysis_async("trivy", compute_trivy, snapshot_id)
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
            
            import asyncio
            loop = asyncio.get_event_loop()
            ai_explanation = await loop.run_in_executor(None, explain_drift, diff_summary)
            
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
            
        import asyncio
        loop = asyncio.get_event_loop()
        ai_explanation = await loop.run_in_executor(None, explain_drift, diff_summary)
        
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
        import asyncio
        loop = asyncio.get_event_loop()
        raw_snap = await loop.run_in_executor(None, snapshot)
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

# ---------------------------------------------------------------------------
# Frontend Static Files (single-image Docker mode)
# Set SERVE_FRONTEND=true to enable. The Dockerfile builds React into ./static
# ---------------------------------------------------------------------------
_STATIC_DIR = Path(__file__).parent / "static"
if os.getenv("SERVE_FRONTEND", "false").lower() == "true" and _STATIC_DIR.exists():
    # Serve /assets/* (JS/CSS bundles) from static/assets/
    _assets_dir = _STATIC_DIR / "assets"
    if _assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(_assets_dir)), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        """Catch-all: serve React index.html for any unknown path (SPA routing)."""
        index = _STATIC_DIR / "index.html"
        if index.exists():
            return FileResponse(str(index))
        raise HTTPException(status_code=404, detail="Frontend not found")

