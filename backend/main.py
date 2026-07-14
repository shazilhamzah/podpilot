import os
import time
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
    analyze_security
)
from trivy import scan_all_images, trivy_ai_summary, trivy_to_issues
from drift_detection import (
    save_snapshot,
    load_last_two_snapshots,
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

class ChatRequest(BaseModel):
    question: str

class RefreshResponse(BaseModel):
    status: str
    pod_count: int
    refreshed_at: str

POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "300"))

_cache = {
    "snapshot": None,
    "last_updated": None
}

def get_cached_snapshot() -> dict:
    now = time.time()
    if _cache["snapshot"] is None or _cache["last_updated"] is None or (now - _cache["last_updated"] > POLL_INTERVAL_SECONDS):
        try:
            raw_snap = snapshot()
            enriched = enrich_with_cost(raw_snap)
            clean_snap = sanitize(enriched)
            _cache["snapshot"] = clean_snap
            _cache["last_updated"] = now
        except Exception as e:
            raise Exception(f"Failed to build snapshot: {str(e)}")
    return _cache["snapshot"]

@app.on_event("startup")
async def startup_event():
    print("PodPilot API starting up...")
    print("Pre-warming snapshot cache...")
    try:
        snap = get_cached_snapshot()
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
async def get_snapshot():
    try:
        snap = get_cached_snapshot()
        last_updated_ts = _cache.get("last_updated")
        cached_at = datetime.fromtimestamp(last_updated_ts, timezone.utc).isoformat() if last_updated_ts else None
        return {
            "data": snap,
            "cached_at": cached_at,
            "pod_count": len(snap.get("pods", [])),
            "node_count": len(snap.get("nodes", []))
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": str(e), "endpoint": "/snapshot"})

@app.get("/health")
async def get_health():
    try:
        snap = get_cached_snapshot()
        return proactive_health_check(snap)
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": str(e), "endpoint": "/health"})

@app.post("/chat")
async def chat(request: ChatRequest):
    try:
        snap = get_cached_snapshot()
        ans = analyze(request.question, snap)
        age = int(time.time() - _cache["last_updated"]) if _cache["last_updated"] else 0
        return {
            "question": request.question,
            "answer": ans,
            "snapshot_age_seconds": age
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": str(e), "endpoint": "/chat"})

@app.get("/cost")
async def cost():
    try:
        return analyze_cost(get_cached_snapshot())
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": str(e), "endpoint": "/cost"})

@app.get("/reliability")
async def reliability():
    try:
        return analyze_reliability(get_cached_snapshot())
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": str(e), "endpoint": "/reliability"})

@app.get("/performance")
async def performance():
    try:
        return analyze_performance(get_cached_snapshot())
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": str(e), "endpoint": "/performance"})

@app.get("/storage")
async def storage():
    try:
        return analyze_storage(get_cached_snapshot())
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": str(e), "endpoint": "/storage"})

@app.get("/security")
async def security():
    try:
        existing_result = analyze_security(get_cached_snapshot())
        trivy_result = scan_all_images(get_cached_snapshot())
        trivy_issues = trivy_to_issues(trivy_result)
        
        # merge trivy issues into existing security issues
        existing_result["issues"] = existing_result.get("issues", []) + trivy_issues
        return existing_result
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": str(e), "endpoint": "/security"})

@app.get("/trivy")
async def trivy_scan():
    # WARNING: This endpoint is SLOW (1-3 minutes on first call due to Trivy DB download).
    try:
        scan_results = scan_all_images(get_cached_snapshot())
        ai_summary = trivy_ai_summary(scan_results)
        issues = trivy_to_issues(scan_results)
        return {
            "scan_results": scan_results,
            "ai_summary": ai_summary,
            "issues": issues
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": str(e), "endpoint": "/trivy"})

@app.get("/drift")
async def drift():
    try:
        snap = get_cached_snapshot()
        save_snapshot(snap)
        
        older, newer = load_last_two_snapshots()
        if older is None:
            return {
                "status": "first_snapshot",
                "message": "First snapshot taken, nothing to compare yet.",
                "diff_summary": None,
                "ai_analysis": None,
                "changes_detected": 0
            }

        changes = diff_snapshots(older, newer)
        diff_summary = summarize_diff(changes)
        ai_explanation = explain_drift(diff_summary)

        return {
            "status": "success",
            "message": "Compared current snapshot with previous.",
            "diff_summary": diff_summary,
            "ai_analysis": ai_explanation,
            "changes_detected": len(changes)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": str(e), "endpoint": "/drift"})

@app.post("/refresh", response_model=RefreshResponse)
async def refresh():
    try:
        now = time.time()
        raw_snap = snapshot()
        enriched = enrich_with_cost(raw_snap)
        clean_snap = sanitize(enriched)
        
        _cache["snapshot"] = clean_snap
        _cache["last_updated"] = now
        
        refreshed_at = datetime.fromtimestamp(now, timezone.utc).isoformat()
        
        return RefreshResponse(
            status="refreshed",
            pod_count=len(clean_snap.get("pods", [])),
            refreshed_at=refreshed_at
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": str(e), "endpoint": "/refresh"})
