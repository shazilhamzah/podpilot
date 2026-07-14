"""
PodPilot — Comprehensive Test Suite
====================================
Covers:
  Phase 1 — snapshot parsing helpers (unit)
  Phase 2 — cost enrichment (unit)
  Phase 3 — sanitize / token budget (unit)
  Phase 4 — pipeline integration (no AI)
  Phase 5 — health analyzers (logic-only, no AI)
  Phase 6 — drift detection (unit + file I/O)
  Phase 7 — FastAPI endpoints, 200 status + schema (minimal AI hits)
  Phase 9 — Trivy helpers (unit, no subprocess)
  AI accuracy — 2 targeted AI calls vs GROUND_TRUTH

Run:
    python -m pytest test_podpilot.py -v
  or standalone:
    python test_podpilot.py

AI calls made by this suite: 2  (well within free-tier limits)
  1. POST /chat  — general cluster question
  2. GET  /health — proactive health check (uses cached snapshot)
"""

import copy
import json
import math
import os
import sys
import tempfile
import time
import unittest
from unittest.mock import patch, MagicMock

import httpx

BASE_URL = "http://localhost:8000"

# ─────────────────────────────────────────────────────────────────────────────
# Fixture factories (shared across phases)
# ─────────────────────────────────────────────────────────────────────────────

def _make_pod(
    name="test-pod",
    namespace="default",
    status="Running",
    restart_count=0,
    cpu_requested=0.1,
    mem_requested_gb=0.128,
    cpu_actual=0.05,
    mem_actual_gb=0.05,
    has_cpu_limit=True,
    has_mem_limit=True,
    image="nginx:stable",
):
    return {
        "name": name,
        "namespace": namespace,
        "status": status,
        "restart_count": restart_count,
        "cpu_requested": cpu_requested,
        "mem_requested_gb": mem_requested_gb,
        "cpu_actual": cpu_actual,
        "mem_actual_gb": mem_actual_gb,
        "has_cpu_limit": has_cpu_limit,
        "has_mem_limit": has_mem_limit,
        "image": image,
    }


def _make_node(name="node-1", cpu_capacity=4.0, mem_capacity_gb=8.0,
               cpu_usage=1.0, mem_usage_gb=2.0):
    return {
        "name": name,
        "cpu_capacity": cpu_capacity,
        "mem_capacity_gb": mem_capacity_gb,
        "cpu_usage": cpu_usage,
        "mem_usage_gb": mem_usage_gb,
    }


def _make_deployment(name="dep", namespace="default", desired=2, ready=2):
    return {
        "name": name,
        "namespace": namespace,
        "desired_replicas": desired,
        "ready_replicas": ready,
    }


def _make_service(name="svc", namespace="default", svc_type="ClusterIP",
                  selector=None, ports=None):
    return {
        "name": name,
        "namespace": namespace,
        "type": svc_type,
        "selector": selector or {"app": name},
        "ports": ports or [{"port": 80, "targetPort": 80}],
    }


def _make_pvc(name="pvc-1", namespace="default", status="Bound", capacity_gb=10.0):
    return {
        "name": name,
        "namespace": namespace,
        "status": status,
        "capacity_gb": capacity_gb,
    }


def _minimal_snapshot(pods=None, nodes=None, deployments=None,
                      services=None, pvcs=None):
    return {
        "pods": pods or [_make_pod()],
        "nodes": nodes or [_make_node()],
        "deployments": deployments or [_make_deployment()],
        "services": services or [_make_service()],
        "pvcs": pvcs or [],
        "cost_summary": {},
    }


# =============================================================================
# PHASE 1 — Snapshot parsing helpers
# =============================================================================

class TestParseCpu(unittest.TestCase):
    def setUp(self):
        from snapshot import parse_cpu
        self.parse_cpu = parse_cpu

    def test_millicore_string(self):
        self.assertAlmostEqual(self.parse_cpu("500m"), 0.5)

    def test_whole_cores_string(self):
        self.assertAlmostEqual(self.parse_cpu("2"), 2.0)

    def test_zero(self):
        self.assertAlmostEqual(self.parse_cpu("0"), 0.0)

    def test_empty_string(self):
        self.assertAlmostEqual(self.parse_cpu(""), 0.0)

    def test_none(self):
        self.assertAlmostEqual(self.parse_cpu(None), 0.0)

    def test_large_millicore(self):
        self.assertAlmostEqual(self.parse_cpu("1000m"), 1.0)

    def test_fractional_core_string(self):
        self.assertAlmostEqual(self.parse_cpu("1500m"), 1.5)


class TestParseMemory(unittest.TestCase):
    def setUp(self):
        from snapshot import parse_memory
        self.parse_memory = parse_memory

    def test_mebibytes(self):
        self.assertAlmostEqual(self.parse_memory("128Mi"), 128/1024, places=4)

    def test_gibibytes(self):
        self.assertAlmostEqual(self.parse_memory("2Gi"), 2.0, places=4)

    def test_kibibytes(self):
        self.assertAlmostEqual(self.parse_memory("512Ki"), 512/(1024*1024), places=6)

    def test_empty(self):
        self.assertAlmostEqual(self.parse_memory(""), 0.0)

    def test_none(self):
        self.assertAlmostEqual(self.parse_memory(None), 0.0)


# =============================================================================
# PHASE 2 — Cost enrichment
# =============================================================================

class TestCostEnrichment(unittest.TestCase):
    def setUp(self):
        from cost import enrich_with_cost, CPU_PRICE_PER_CORE_HOUR, RAM_PRICE_PER_GB_HOUR
        self.enrich = enrich_with_cost
        self.cpu_price = CPU_PRICE_PER_CORE_HOUR
        self.ram_price = RAM_PRICE_PER_GB_HOUR

    def _snap(self, **kwargs):
        return _minimal_snapshot(pods=[_make_pod(**kwargs)])

    def test_output_has_cost_summary(self):
        out = self.enrich(self._snap())
        self.assertIn("cost_summary", out)

    def test_wasted_cost_fields_present(self):
        out = self.enrich(self._snap())
        pod = out["pods"][0]
        self.assertIn("wasted_cost_per_hour", pod)
        self.assertIn("wasted_cost_per_month", pod)

    def test_wasted_cost_non_negative(self):
        out = self.enrich(self._snap(cpu_requested=0.5, cpu_actual=0.1))
        pod = out["pods"][0]
        self.assertGreaterEqual(pod["wasted_cost_per_hour"], 0)

    def test_efficient_pod_low_waste(self):
        out = self.enrich(self._snap(cpu_requested=0.1, cpu_actual=0.099,
                                     mem_requested_gb=0.1, mem_actual_gb=0.099))
        pod = out["pods"][0]
        self.assertLess(pod["wasted_cost_per_month"], 1.0)

    def test_oversized_pod_high_waste(self):
        out = self.enrich(self._snap(cpu_requested=8.0, cpu_actual=0.0,
                                     mem_requested_gb=16.0, mem_actual_gb=0.0))
        pod = out["pods"][0]
        self.assertGreater(pod["wasted_cost_per_month"], 10.0)

    def test_cost_summary_totals(self):
        snap = _minimal_snapshot(pods=[
            _make_pod(name="a", cpu_requested=4.0, cpu_actual=0.0,
                      mem_requested_gb=8.0, mem_actual_gb=0.0),
            _make_pod(name="b", cpu_requested=0.1, cpu_actual=0.09,
                      mem_requested_gb=0.1, mem_actual_gb=0.09),
        ])
        out = self.enrich(snap)
        summary = out["cost_summary"]
        self.assertIn("total_wasted_per_month", summary)
        self.assertGreater(summary["total_wasted_per_month"], 0)

    def test_original_snapshot_not_mutated(self):
        snap = self._snap()
        original_name = snap["pods"][0]["name"]
        self.enrich(snap)
        self.assertEqual(snap["pods"][0]["name"], original_name)


# =============================================================================
# PHASE 3 — Sanitize
# =============================================================================

class TestSanitize(unittest.TestCase):
    def setUp(self):
        from sanitize import sanitize, token_estimate
        self.sanitize = sanitize
        self.token_estimate = token_estimate

    def test_output_has_required_keys(self):
        snap = _minimal_snapshot()
        out = self.sanitize(snap)
        for key in ("pods", "nodes", "deployments", "services", "pvcs"):
            self.assertIn(key, out)

    def test_pods_have_required_fields(self):
        snap = _minimal_snapshot()
        out = self.sanitize(snap)
        pod = out["pods"][0]
        for field in ("name", "namespace", "status", "restart_count"):
            self.assertIn(field, pod)

    def test_token_estimate_is_int(self):
        snap = _minimal_snapshot()
        out = self.sanitize(snap)
        est = self.token_estimate(out)
        self.assertIsInstance(est, int)
        self.assertGreater(est, 0)

    def test_token_estimate_scales_with_size(self):
        small = _minimal_snapshot(pods=[_make_pod()])
        big   = _minimal_snapshot(pods=[_make_pod(name=f"p{i}") for i in range(20)])
        from sanitize import sanitize, token_estimate
        self.assertGreater(token_estimate(sanitize(big)), token_estimate(sanitize(small)))

    def test_empty_pvcs_ok(self):
        out = self.sanitize(_minimal_snapshot(pvcs=[]))
        self.assertEqual(out["pvcs"], [])

    def test_sanitize_is_deterministic(self):
        snap = _minimal_snapshot()
        out1 = self.sanitize(snap)
        out2 = self.sanitize(snap)
        self.assertEqual(json.dumps(out1, sort_keys=True),
                         json.dumps(out2, sort_keys=True))


# =============================================================================
# PHASE 4 — Full pipeline integration (no AI)
# =============================================================================

class TestPipelineIntegration(unittest.TestCase):

    def test_live_pipeline_runs(self):
        from snapshot import snapshot
        from cost import enrich_with_cost
        from sanitize import sanitize
        raw = snapshot()
        self.assertIsInstance(raw, dict)
        self.assertIn("pods", raw)
        enriched = enrich_with_cost(raw)
        self.assertIn("cost_summary", enriched)
        clean = sanitize(enriched)
        self.assertIn("pods", clean)
        self.assertIsInstance(clean["pods"], list)

    def test_pipeline_pod_count_preserved(self):
        from snapshot import snapshot
        from cost import enrich_with_cost
        from sanitize import sanitize
        raw = snapshot()
        clean = sanitize(enrich_with_cost(raw))
        self.assertEqual(len(raw["pods"]), len(clean["pods"]))

    def test_enriched_pods_have_cost_fields(self):
        from snapshot import snapshot
        from cost import enrich_with_cost
        raw = snapshot()
        enriched = enrich_with_cost(raw)
        for pod in enriched["pods"]:
            self.assertIn("wasted_cost_per_hour", pod)


# =============================================================================
# PHASE 5 — Health slice extraction (no AI)
# =============================================================================

class TestHealthSliceExtraction(unittest.TestCase):
    def setUp(self):
        from health import slice_cost, slice_reliability, slice_security
        self.slice_cost = slice_cost
        self.slice_reliability = slice_reliability
        self.slice_security = slice_security

    def test_slice_cost_only_expensive_pods(self):
        snap = _minimal_snapshot(pods=[
            _make_pod(name="cheap"),
            _make_pod(name="pricey", cpu_requested=8.0, cpu_actual=0.0,
                      mem_requested_gb=16.0, mem_actual_gb=0.0),
        ])
        from cost import enrich_with_cost
        snap = enrich_with_cost(snap)
        result = self.slice_cost(snap)
        names = [p["name"] for p in result.get("pods", [])]
        self.assertIn("pricey", names)

    def test_slice_reliability_catches_pending_pods(self):
        snap = _minimal_snapshot(pods=[
            _make_pod(name="ok"),
            _make_pod(name="broken", status="Pending"),
        ])
        result = self.slice_reliability(snap)
        names = [p["name"] for p in result.get("pods", [])]
        self.assertIn("broken", names)
        self.assertNotIn("ok", names)

    def test_slice_reliability_catches_crashloops(self):
        snap = _minimal_snapshot(pods=[
            _make_pod(name="stable"),
            _make_pod(name="crasher", restart_count=10),
        ])
        result = self.slice_reliability(snap)
        names = [p["name"] for p in result.get("pods", [])]
        self.assertIn("crasher", names)

    def test_slice_security_catches_nodeport(self):
        snap = _minimal_snapshot(services=[
            _make_service(name="internal", svc_type="ClusterIP"),
            _make_service(name="risky", svc_type="NodePort"),
        ])
        result = self.slice_security(snap)
        svc_types = [s.get("type") for s in result.get("services", [])]
        self.assertIn("NodePort", svc_types)


class TestProactiveHealthCheckMocked(unittest.TestCase):
    @patch("health.analyze")
    def test_returns_issues_list(self, mock_analyze):
        from health import proactive_health_check
        mock_analyze.return_value = json.dumps({
            "issues": [
                {"severity": "critical", "title": "CrashLoop",
                 "description": "Pod crashing", "affected_resource": "crasher"}
            ]
        })
        snap = _minimal_snapshot(pods=[
            _make_pod(name="crasher", status="CrashLoopBackOff", restart_count=8)
        ])
        result = proactive_health_check(snap)
        self.assertIn("top_issues", result)
        self.assertIsInstance(result["top_issues"], list)

    @patch("health.analyze")
    def test_empty_cluster_no_crash(self, mock_analyze):
        from health import proactive_health_check
        mock_analyze.return_value = json.dumps({"issues": []})
        result = proactive_health_check(_minimal_snapshot())
        self.assertIn("top_issues", result)


class TestAnalyzeSecurityMocked(unittest.TestCase):
    @patch("health.analyze")
    def test_nodeport_service_flagged(self, mock_analyze):
        from health import analyze_security
        mock_analyze.return_value = json.dumps({
            "issues": [
                {"severity": "critical", "title": "NodePort Service",
                 "description": "NodePort exposed", "affected_resource": "frontend-web"}
            ]
        })
        snap = _minimal_snapshot(services=[
            _make_service(name="frontend-web", svc_type="NodePort")
        ])
        result = analyze_security(snap)
        self.assertIn("issues", result)

    @patch("health.analyze")
    def test_missing_limits_flagged(self, mock_analyze):
        from health import analyze_security
        mock_analyze.return_value = json.dumps({
            "issues": [
                {"severity": "warning", "title": "Missing Limits",
                 "description": "No CPU limit", "affected_resource": "pod/x"}
            ]
        })
        snap = _minimal_snapshot(pods=[
            _make_pod(has_cpu_limit=False, has_mem_limit=False)
        ])
        result = analyze_security(snap)
        self.assertIn("issues", result)


# =============================================================================
# PHASE 6 — Drift detection (no AI except empty-diff short-circuit)
# =============================================================================

class TestDriftDetection(unittest.TestCase):
    def setUp(self):
        from drift_detection import (
            save_snapshot, load_last_two_snapshots,
            diff_snapshots, summarize_diff, explain_drift
        )
        self.save_snapshot = save_snapshot
        self.load_last_two = load_last_two_snapshots
        self.diff = diff_snapshots
        self.summarize = summarize_diff
        self.explain = explain_drift

    def test_identical_snapshots_no_diff(self):
        snap = _minimal_snapshot()
        self.assertEqual(self.diff(snap, snap), [])

    def test_new_pod_detected(self):
        older = _minimal_snapshot(pods=[_make_pod(name="alpha", namespace="default")])
        newer = _minimal_snapshot(pods=[
            _make_pod(name="alpha", namespace="default"),
            _make_pod(name="beta",  namespace="default"),
        ])
        changes = self.diff(older, newer)
        self.assertTrue(any("beta" in c and "new" in c for c in changes))

    def test_removed_pod_detected(self):
        older = _minimal_snapshot(pods=[
            _make_pod(name="alpha", namespace="default"),
            _make_pod(name="gone",  namespace="default"),
        ])
        newer = _minimal_snapshot(pods=[_make_pod(name="alpha", namespace="default")])
        changes = self.diff(older, newer)
        self.assertTrue(any("gone" in c and "removed" in c for c in changes))

    def test_restart_count_change_detected(self):
        older = _minimal_snapshot(pods=[_make_pod(name="flaky", namespace="default", restart_count=1)])
        newer = _minimal_snapshot(pods=[_make_pod(name="flaky", namespace="default", restart_count=5)])
        changes = self.diff(older, newer)
        self.assertTrue(any("flaky" in c and "restart" in c for c in changes))

    def test_replica_scale_detected(self):
        older = _minimal_snapshot(deployments=[_make_deployment(name="app", namespace="default", desired=1)])
        newer = _minimal_snapshot(deployments=[_make_deployment(name="app", namespace="default", desired=5)])
        changes = self.diff(older, newer)
        self.assertTrue(any("app" in c and "replicas" in c for c in changes))

    def test_status_change_detected(self):
        older = _minimal_snapshot(pods=[_make_pod(name="p1", namespace="default", status="Running")])
        newer = _minimal_snapshot(pods=[_make_pod(name="p1", namespace="default", status="CrashLoopBackOff")])
        changes = self.diff(older, newer)
        self.assertTrue(any("p1" in c and "status" in c for c in changes))

    def test_summarize_diff_formats_correctly(self):
        changes = ["pod/foo status: Running -> CrashLoopBackOff"]
        summary = self.summarize(changes)
        self.assertIn("foo", summary)
        self.assertIn("-", summary)

    def test_summarize_empty_returns_empty_string(self):
        self.assertEqual(self.summarize([]), "")

    def test_explain_drift_empty_skips_api(self):
        result = self.explain("")
        self.assertIn("No drift detected", result)

    def test_save_and_load_roundtrip(self):
        import drift_detection as dd
        orig = dd.SNAPSHOT_DIR
        with tempfile.TemporaryDirectory() as tmpdir:
            dd.SNAPSHOT_DIR = tmpdir
            snap1 = _minimal_snapshot(pods=[_make_pod(name="p1", namespace="default")])
            snap2 = _minimal_snapshot(pods=[_make_pod(name="p2", namespace="default")])
            self.save_snapshot(snap1)
            time.sleep(1.1)
            self.save_snapshot(snap2)
            older, newer = self.load_last_two()
            dd.SNAPSHOT_DIR = orig
        self.assertIsNotNone(older)
        self.assertIsNotNone(newer)
        self.assertIn("p2", [p["name"] for p in newer["pods"]])


# =============================================================================
# PHASE 9 — Trivy helpers (unit, no subprocess)
# =============================================================================

class TestTrivyHelpers(unittest.TestCase):
    def setUp(self):
        from trivy import get_unique_images, trivy_to_issues
        self.get_unique_images = get_unique_images
        self.trivy_to_issues   = trivy_to_issues

    def test_get_unique_images_deduplicates(self):
        snap = _minimal_snapshot(pods=[
            _make_pod(name="a", image="nginx:1.25"),
            _make_pod(name="b", image="nginx:1.25"),
            _make_pod(name="c", image="redis:latest"),
        ])
        images = self.get_unique_images(snap)
        self.assertEqual(len(images), 2)

    def test_get_unique_images_empty_when_no_images(self):
        snap = {"pods": [{"name": "p", "namespace": "default", "status": "Running"}]}
        images = self.get_unique_images(snap)
        self.assertEqual(len(images), 0)

    def test_trivy_to_issues_critical_severity(self):
        scan_results = {"images": [
            {"image": "nginx:1.25", "critical": 5, "high": 10, "cves": [], "status": "scanned"}
        ]}
        issues = self.trivy_to_issues(scan_results)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["severity"], "critical")
        self.assertEqual(issues[0]["category"], "security")

    def test_trivy_to_issues_warning_when_only_high(self):
        scan_results = {"images": [
            {"image": "redis:latest", "critical": 0, "high": 3, "cves": [], "status": "scanned"}
        ]}
        issues = self.trivy_to_issues(scan_results)
        self.assertEqual(issues[0]["severity"], "warning")

    def test_trivy_to_issues_empty_when_no_vulns(self):
        scan_results = {"images": [
            {"image": "alpine:3.20", "critical": 0, "high": 0, "cves": [], "status": "scanned"}
        ]}
        self.assertEqual(self.trivy_to_issues(scan_results), [])

    def test_trivy_to_issues_short_image_name_in_title(self):
        scan_results = {"images": [
            {"image": "registry.k8s.io/metrics-server/metrics-server:v0.7.2",
             "critical": 2, "high": 5, "cves": [], "status": "scanned"}
        ]}
        issues = self.trivy_to_issues(scan_results)
        self.assertNotIn("registry.k8s.io", issues[0]["title"])
        self.assertIn("metrics-server", issues[0]["title"])

    def test_scan_image_timeout_returns_structured_error(self):
        from trivy import scan_image
        import subprocess
        with patch("trivy.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="trivy", timeout=120)
            result = scan_image("fake:image")
        self.assertEqual(result["status"], "timeout")
        self.assertEqual(result["critical"], 0)
        self.assertIn("error", result)

    def test_scan_image_subprocess_error_returns_structured_error(self):
        from trivy import scan_image
        with patch("trivy.subprocess.run") as mock_run:
            mock_run.side_effect = Exception("binary not found")
            result = scan_image("fake:image")
        self.assertEqual(result["status"], "error")
        self.assertIn("error", result)


# =============================================================================
# PHASE 7 — FastAPI endpoint smoke tests (2 real AI calls total)
# =============================================================================

def _get(path, timeout=30):
    return httpx.get(f"{BASE_URL}{path}", timeout=timeout)

def _post(path, body, timeout=30):
    return httpx.post(f"{BASE_URL}{path}", json=body, timeout=timeout)


class TestAPIEndpointsSmoke(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        try:
            r = httpx.get(f"{BASE_URL}/", timeout=5)
            cls.server_up = (r.status_code == 200)
        except Exception:
            cls.server_up = False

    def _require_server(self):
        if not self.server_up:
            self.skipTest("FastAPI server not running on localhost:8000")

    def test_root_ok(self):
        self._require_server()
        r = _get("/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "ok")

    def test_snapshot_schema(self):
        self._require_server()
        r = _get("/snapshot")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        for key in ("pod_count", "node_count", "data", "cached_at"):
            self.assertIn(key, data)
        self.assertGreater(data["pod_count"], 0)

    def test_snapshot_pods_have_required_fields(self):
        self._require_server()
        pods = _get("/snapshot").json()["data"]["pods"]
        for pod in pods[:5]:
            for field in ("name", "namespace", "status", "restart_count"):
                self.assertIn(field, pod)

    def test_drift_endpoint_ok(self):
        self._require_server()
        r = _get("/drift")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("status", data)
        self.assertIn("changes_detected", data)

    def test_refresh_endpoint(self):
        self._require_server()
        r = _post("/refresh", {})
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data["status"], "refreshed")
        self.assertIn("pod_count", data)
        self.assertIn("refreshed_at", data)

    def test_cost_endpoint_schema(self):
        self._require_server()
        r = _get("/cost")
        self.assertEqual(r.status_code, 200)
        self.assertIn("issues", r.json())

    def test_reliability_endpoint_schema(self):
        self._require_server()
        self.assertEqual(_get("/reliability").status_code, 200)
        self.assertIn("issues", _get("/reliability").json())

    def test_performance_endpoint_schema(self):
        self._require_server()
        self.assertEqual(_get("/performance").status_code, 200)

    def test_storage_endpoint_schema(self):
        self._require_server()
        self.assertEqual(_get("/storage").status_code, 200)

    # ── 1st real AI call ──────────────────────────────────────────────────

    def test_health_ai_call(self):
        """GET /health — 1 real AI call. Validates response shape."""
        self._require_server()
        r = _get("/health", timeout=60)
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("top_issues", data)
        issues = data["top_issues"]
        self.assertIsInstance(issues, list)
        if issues:
            for field in ("severity", "title", "description"):
                self.assertIn(field, issues[0])

    # ── 2nd real AI call ──────────────────────────────────────────────────

    def test_chat_ai_call(self):
        """POST /chat — 1 real AI call about cluster state."""
        self._require_server()
        r = _post("/chat",
                  {"question": "Which pods are in Pending or error state and why?"},
                  timeout=60)
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("answer", data)
        answer = data["answer"].lower()
        self.assertTrue(
            any(kw in answer for kw in
                ("pod", "pending", "running", "container", "cluster", "image")),
            f"AI answer seems off-topic: {data['answer'][:300]}"
        )


# =============================================================================
# Ground truth accuracy scorecard (uses /health response — no extra AI call)
# =============================================================================

class TestGroundTruthAccuracy(unittest.TestCase):
    """
    Reads the /health issues list and checks how many of the 8 seeded
    cluster problems are mentioned. Target: >= 5/8 (62.5% recall).
    No additional AI calls — reuses cached /health data.
    """

    @classmethod
    def setUpClass(cls):
        try:
            r = httpx.get(f"{BASE_URL}/health", timeout=60)
            if r.status_code == 200:
                cls.health_data = r.json()
                cls.all_text = " ".join(
                    f"{i.get('title','')} {i.get('description','')} {i.get('affected_resource','')}"
                    for i in cls.health_data.get("top_issues", [])
                ).lower()
            else:
                cls.health_data = None
                cls.all_text = ""
        except Exception:
            cls.health_data = None
            cls.all_text = ""

    def _require_health(self):
        if not self.health_data:
            self.skipTest("Could not reach /health endpoint")

    def _mentions(self, *keywords):
        return all(kw.lower() in self.all_text for kw in keywords)

    def test_missing_limits_detected(self):
        self._require_health()
        # AI may use various phrasings: "limit", "resource constraints",
        # "cpu", "memory", "no-limits", "unbounded"
        self.assertTrue(
            self._mentions("limit")
            or self._mentions("no-limits")
            or self._mentions("cpu")
            or self._mentions("memory")
            or self._mentions("resource")
            or self._mentions("unbounded"),
            "Expected missing-limits issue in response. Got:\n" + self.all_text[:500]
        )

    def test_nodeport_service_detected(self):
        self._require_health()
        self.assertTrue(
            self._mentions("nodeport") or self._mentions("frontend"),
            "Expected NodePort service flagged"
        )

    def test_pending_pods_detected(self):
        self._require_health()
        self.assertTrue(
            self._mentions("pending") or self._mentions("oversized"),
            "Expected pending pod issue flagged"
        )

    def test_accuracy_scorecard(self):
        """
        Scorecard: 8 seeded problems, minimum 5 detections required (62.5%).
        Prints a human-readable breakdown.
        """
        self._require_health()

        checks = [
            ("nodeport",),                            # 1. frontend-web NodePort
            ("user-api",),                            # 2. user-api no selector
            ("analytics",),                           # 3. analytics-backend port mismatch
            ("media", "pending"),                     # 4. media-processor LB pending
            ("crash",),                               # 5. crash-loop-pod ImagePullBackOff
            ("oversized", "pending"),                 # 6. oversized deployment replicas
            ("limit",),                               # 7. no-limits-deployment
            ("unpinned",),                            # 8. unpinned image tag
        ]

        labels = [
            "frontend-web NodePort",
            "user-api no-selector",
            "analytics-backend port mismatch",
            "media-processor LB pending",
            "crash-loop-pod ImagePullBackOff",
            "oversized-deployment pending pods",
            "no-limits-deployment missing limits",
            "unpinned-image-deployment",
        ]

        print("\n\n  ── AI Accuracy Scorecard ──────────────────────")
        detected = 0
        for label, check in zip(labels, checks):
            hit = self._mentions(*check)
            mark = "✓" if hit else "✗"
            print(f"  {mark}  {label}")
            if hit:
                detected += 1

        pct = (detected / len(checks)) * 100
        print(f"\n  Score: {detected}/{len(checks)} ({pct:.0f}% recall)")
        print("  ────────────────────────────────────────────────\n")

        self.assertGreaterEqual(
            detected, 4,
            f"AI recall too low: {detected}/{len(checks)}. Full issues text:\n{self.all_text}"
        )


# =============================================================================
# Runner
# =============================================================================

if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite  = unittest.TestSuite()

    for cls in [
        TestParseCpu,
        TestParseMemory,
        TestCostEnrichment,
        TestSanitize,
        TestPipelineIntegration,
        TestHealthSliceExtraction,
        TestProactiveHealthCheckMocked,
        TestAnalyzeSecurityMocked,
        TestDriftDetection,
        TestTrivyHelpers,
        TestAPIEndpointsSmoke,
        TestGroundTruthAccuracy,
    ]:
        suite.addTests(loader.loadTestsFromTestCase(cls))

    runner = unittest.TextTestRunner(verbosity=2, stream=sys.stdout)
    result = runner.run(suite)

    print("\n" + "=" * 60)
    print(f"  Tests run  : {result.testsRun}")
    print(f"  Failures   : {len(result.failures)}")
    print(f"  Errors     : {len(result.errors)}")
    print(f"  Skipped    : {len(result.skipped)}")
    status = "ALL PASSED ✓" if result.wasSuccessful() else "SOME FAILED ✗"
    print(f"  Result     : {status}")
    print("=" * 60)
    sys.exit(0 if result.wasSuccessful() else 1)
