"""
PodPilot Test Suite — Phases 1, 2, 3 pipeline

Tests:
  - snapshot.parse_cpu / parse_memory (unit)
  - cost.enrich_with_cost (unit)
  - sanitize.sanitize / token_estimate (unit)
  - Full pipeline: enrich_with_cost -> sanitize (integration)

Run with:
    python -m pytest test_podpilot.py -v
  or:
    python test_podpilot.py
"""

import copy
import json
import math
import sys
import unittest

# ── imports from our own modules ──────────────────────────────────────────────
from snapshot import parse_cpu, parse_memory
from cost import (
    enrich_with_cost,
    CPU_PRICE_PER_CORE_HOUR,
    RAM_PRICE_PER_GB_HOUR,
    VM_SKU,
)
from sanitize import sanitize, token_estimate


# ─────────────────────────────────────────────────────────────────────────────
# Shared test fixture helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_pod(
    name="test-pod",
    namespace="default",
    status="Running",
    restart_count=0,
    cpu_requested=0.1,
    mem_requested_gb=0.125,
    cpu_actual=0.05,
    mem_actual_gb=0.05,
    has_cpu_limit=True,
    has_mem_limit=True,
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
    }


def _make_node(
    name="minikube",
    cpu_capacity=2.0,
    mem_capacity_gb=8.0,
    cpu_usage=0.3,
    mem_usage_gb=1.5,
):
    return {
        "name": name,
        "cpu_capacity": cpu_capacity,
        "mem_capacity_gb": mem_capacity_gb,
        "cpu_usage": cpu_usage,
        "mem_usage_gb": mem_usage_gb,
    }


def _make_deployment(name="dep", namespace="default", desired=1, ready=1):
    return {
        "name": name,
        "namespace": namespace,
        "desired_replicas": desired,
        "ready_replicas": ready,
    }


def _make_service(name="svc", namespace="default", svc_type="ClusterIP", port=80):
    return {"name": name, "namespace": namespace, "type": svc_type, "port": port}


def _make_pvc(name="pvc", namespace="default", status="Bound", capacity_gb=1.0, storage_class="standard"):
    return {
        "name": name,
        "namespace": namespace,
        "status": status,
        "capacity_gb": capacity_gb,
        "storage_class": storage_class,
    }


def _base_snapshot(**kwargs):
    """Minimal valid snapshot."""
    base = {
        "captured_at": "2026-07-13T10:00:00Z",
        "cluster_name": "minikube",
        "nodes": [_make_node()],
        "pods": [_make_pod()],
        "deployments": [_make_deployment()],
        "services": [_make_service()],
        "pvcs": [_make_pvc()],
    }
    base.update(kwargs)
    return base


# ─────────────────────────────────────────────────────────────────────────────
# PART 1 — parse_cpu
# ─────────────────────────────────────────────────────────────────────────────

class TestParseCpu(unittest.TestCase):

    def test_millicores(self):
        self.assertAlmostEqual(parse_cpu("500m"), 0.5)

    def test_1000m_equals_1_core(self):
        self.assertAlmostEqual(parse_cpu("1000m"), 1.0)

    def test_plain_integer_string(self):
        self.assertAlmostEqual(parse_cpu("2"), 2.0)

    def test_plain_float_string(self):
        self.assertAlmostEqual(parse_cpu("0.5"), 0.5)

    def test_nanocores(self):
        self.assertAlmostEqual(parse_cpu("1000000000n"), 1.0)

    def test_microcores(self):
        self.assertAlmostEqual(parse_cpu("1000000u"), 1.0)

    def test_zero_string(self):
        self.assertAlmostEqual(parse_cpu("0"), 0.0)

    def test_empty_string_returns_zero(self):
        self.assertEqual(parse_cpu(""), 0.0)

    def test_none_returns_zero(self):
        self.assertEqual(parse_cpu(None), 0.0)

    def test_int_input(self):
        self.assertEqual(parse_cpu(2), 2.0)

    def test_float_input(self):
        self.assertEqual(parse_cpu(1.5), 1.5)

    def test_invalid_string_returns_zero(self):
        self.assertEqual(parse_cpu("not-a-number"), 0.0)

    def test_125m(self):
        self.assertAlmostEqual(parse_cpu("125m"), 0.125)

    def test_large_millicores(self):
        self.assertAlmostEqual(parse_cpu("4000m"), 4.0)

    def test_small_nanocores(self):
        self.assertAlmostEqual(parse_cpu("500000000n"), 0.5)


# ─────────────────────────────────────────────────────────────────────────────
# PART 2 — parse_memory
# ─────────────────────────────────────────────────────────────────────────────

class TestParseMemory(unittest.TestCase):

    def test_kibibytes(self):
        # 1024 Ki = 1 Mi = 1/1024 Gi
        self.assertAlmostEqual(parse_memory("1024Ki"), 1 / 1024)

    def test_mebibytes(self):
        self.assertAlmostEqual(parse_memory("1024Mi"), 1.0)

    def test_gibibytes(self):
        self.assertAlmostEqual(parse_memory("2Gi"), 2.0)

    def test_tebibytes(self):
        self.assertAlmostEqual(parse_memory("1Ti"), 1024.0)

    def test_pebibytes(self):
        self.assertAlmostEqual(parse_memory("1Pi"), 1024 ** 2)

    def test_exbibytes(self):
        self.assertAlmostEqual(parse_memory("1Ei"), 1024 ** 3)

    def test_decimal_kilobytes(self):
        # 1 K = 1000 bytes
        expected = 1000 / (1024 ** 3)
        self.assertAlmostEqual(parse_memory("1K"), expected)

    def test_decimal_megabytes(self):
        expected = (1000 ** 2) / (1024 ** 3)
        self.assertAlmostEqual(parse_memory("1M"), expected)

    def test_decimal_gigabytes(self):
        expected = (1000 ** 3) / (1024 ** 3)
        self.assertAlmostEqual(parse_memory("1G"), expected)

    def test_raw_bytes(self):
        expected = 1073741824 / (1024 ** 3)  # 1 GiB in bytes / GiB
        self.assertAlmostEqual(parse_memory("1073741824"), expected)

    def test_empty_string_returns_zero(self):
        self.assertEqual(parse_memory(""), 0.0)

    def test_none_returns_zero(self):
        self.assertEqual(parse_memory(None), 0.0)

    def test_zero_string(self):
        self.assertEqual(parse_memory("0"), 0.0)

    def test_int_input(self):
        expected = 1073741824 / (1024 ** 3)
        self.assertAlmostEqual(parse_memory(1073741824), expected)

    def test_invalid_string_returns_zero(self):
        self.assertEqual(parse_memory("badvalue"), 0.0)

    def test_256Mi(self):
        self.assertAlmostEqual(parse_memory("256Mi"), 256 / 1024)

    def test_512Mi(self):
        self.assertAlmostEqual(parse_memory("512Mi"), 0.5)


# ─────────────────────────────────────────────────────────────────────────────
# PART 3 — enrich_with_cost
# ─────────────────────────────────────────────────────────────────────────────

class TestEnrichWithCost(unittest.TestCase):

    def setUp(self):
        self.snap = _base_snapshot()

    # ── immutability ──────────────────────────────────────────────────────────
    def test_input_not_mutated(self):
        original = copy.deepcopy(self.snap)
        enrich_with_cost(self.snap)
        self.assertEqual(self.snap, original)

    # ── returned structure ────────────────────────────────────────────────────
    def test_returns_dict(self):
        result = enrich_with_cost(self.snap)
        self.assertIsInstance(result, dict)

    def test_cost_summary_present(self):
        result = enrich_with_cost(self.snap)
        self.assertIn("cost_summary", result)

    def test_cost_summary_keys(self):
        result = enrich_with_cost(self.snap)
        cs = result["cost_summary"]
        for key in ("total_cost_per_hour", "total_wasted_per_hour",
                    "total_wasted_per_month", "reference_vm_sku",
                    "cpu_price_per_core_hour", "ram_price_per_gb_hour"):
            self.assertIn(key, cs, f"Missing key: {key}")

    def test_reference_vm_sku(self):
        result = enrich_with_cost(self.snap)
        self.assertEqual(result["cost_summary"]["reference_vm_sku"], VM_SKU)

    # ── per-pod cost fields ───────────────────────────────────────────────────
    def test_pod_has_cost_fields(self):
        result = enrich_with_cost(self.snap)
        pod = result["pods"][0]
        for field in ("cost_per_hour", "actual_cost_per_hour",
                      "wasted_cost_per_hour", "wasted_cost_per_month"):
            self.assertIn(field, pod, f"Missing field: {field}")

    def test_cost_per_hour_formula(self):
        snap = _base_snapshot(pods=[_make_pod(cpu_requested=1.0, mem_requested_gb=1.0)])
        result = enrich_with_cost(snap)
        expected = round(CPU_PRICE_PER_CORE_HOUR + RAM_PRICE_PER_GB_HOUR, 6)
        self.assertAlmostEqual(result["pods"][0]["cost_per_hour"], expected, places=6)

    def test_actual_cost_formula(self):
        snap = _base_snapshot(pods=[_make_pod(cpu_actual=0.5, mem_actual_gb=0.5)])
        result = enrich_with_cost(snap)
        expected = round(0.5 * CPU_PRICE_PER_CORE_HOUR + 0.5 * RAM_PRICE_PER_GB_HOUR, 6)
        self.assertAlmostEqual(result["pods"][0]["actual_cost_per_hour"], expected, places=6)

    def test_wasted_cost_never_negative(self):
        # actual > requested should clamp wasted to 0
        snap = _base_snapshot(pods=[_make_pod(cpu_requested=0.05, mem_requested_gb=0.05,
                                               cpu_actual=0.9, mem_actual_gb=0.9)])
        result = enrich_with_cost(snap)
        self.assertEqual(result["pods"][0]["wasted_cost_per_hour"], 0.0)
        self.assertEqual(result["pods"][0]["wasted_cost_per_month"], 0.0)

    def test_wasted_per_month_is_730x_hourly(self):
        snap = _base_snapshot(pods=[_make_pod(cpu_requested=1.0, mem_requested_gb=1.0,
                                               cpu_actual=0.0, mem_actual_gb=0.0)])
        result = enrich_with_cost(snap)
        pod = result["pods"][0]
        self.assertAlmostEqual(pod["wasted_cost_per_month"],
                               round(pod["wasted_cost_per_hour"] * 730, 6), places=5)

    # ── None / missing field handling ─────────────────────────────────────────
    def test_none_cpu_requested_gives_zero_cost(self):
        snap = _base_snapshot(pods=[_make_pod(cpu_requested=None, mem_requested_gb=None)])
        result = enrich_with_cost(snap)
        self.assertEqual(result["pods"][0]["cost_per_hour"], 0.0)

    def test_none_cpu_actual_gives_zero_wasted(self):
        snap = _base_snapshot(pods=[_make_pod(cpu_requested=0.0, mem_requested_gb=0.0,
                                               cpu_actual=None, mem_actual_gb=None)])
        result = enrich_with_cost(snap)
        self.assertEqual(result["pods"][0]["wasted_cost_per_hour"], 0.0)

    def test_empty_pods_list(self):
        snap = _base_snapshot(pods=[])
        result = enrich_with_cost(snap)
        self.assertEqual(result["cost_summary"]["total_cost_per_hour"], 0.0)
        self.assertEqual(result["cost_summary"]["total_wasted_per_hour"], 0.0)
        self.assertEqual(result["cost_summary"]["total_wasted_per_month"], 0.0)

    def test_rounding_to_6_places(self):
        snap = _base_snapshot(pods=[_make_pod(cpu_requested=1/3, mem_requested_gb=1/3)])
        result = enrich_with_cost(snap)
        cost = result["pods"][0]["cost_per_hour"]
        # Should be exactly 6 decimal places (no trailing noise)
        self.assertEqual(cost, round(cost, 6))

    # ── cost aggregates ───────────────────────────────────────────────────────
    def test_total_cost_is_sum_of_pods(self):
        pods = [
            _make_pod("a", cpu_requested=0.5, mem_requested_gb=0.25),
            _make_pod("b", cpu_requested=0.3, mem_requested_gb=0.1),
        ]
        snap = _base_snapshot(pods=pods)
        result = enrich_with_cost(snap)
        total = sum(p["cost_per_hour"] for p in result["pods"])
        self.assertAlmostEqual(result["cost_summary"]["total_cost_per_hour"], total, places=5)

    def test_total_wasted_per_month_is_sum_of_pods(self):
        pods = [
            _make_pod("a", cpu_requested=1.0, mem_requested_gb=0.5, cpu_actual=0.0, mem_actual_gb=0.0),
            _make_pod("b", cpu_requested=0.5, mem_requested_gb=0.25, cpu_actual=0.0, mem_actual_gb=0.0),
        ]
        snap = _base_snapshot(pods=pods)
        result = enrich_with_cost(snap)
        total = sum(p["wasted_cost_per_month"] for p in result["pods"])
        self.assertAlmostEqual(result["cost_summary"]["total_wasted_per_month"], total, places=4)

    def test_multiple_pods_cost_accumulated_correctly(self):
        pods = [_make_pod(f"pod-{i}", cpu_requested=0.1, mem_requested_gb=0.1,
                           cpu_actual=0.0, mem_actual_gb=0.0) for i in range(5)]
        snap = _base_snapshot(pods=pods)
        result = enrich_with_cost(snap)
        single_cost = round(0.1 * CPU_PRICE_PER_CORE_HOUR + 0.1 * RAM_PRICE_PER_GB_HOUR, 6)
        self.assertAlmostEqual(result["cost_summary"]["total_cost_per_hour"],
                               single_cost * 5, places=4)

    # ── oversized deployment scenario ─────────────────────────────────────────
    def test_oversized_pod_high_wasted_cost(self):
        """Pod requesting 500m CPU / 512Mi RAM with near-zero actual usage."""
        snap = _base_snapshot(pods=[_make_pod(
            cpu_requested=0.5, mem_requested_gb=0.5,
            cpu_actual=0.001, mem_actual_gb=0.003,
        )])
        result = enrich_with_cost(snap)
        pod = result["pods"][0]
        self.assertGreater(pod["wasted_cost_per_hour"], 0.01)
        self.assertGreater(pod["wasted_cost_per_month"], 7.0)

    # ── no-limits pod (zero cost) ─────────────────────────────────────────────
    def test_pod_with_no_requests_has_zero_cost(self):
        snap = _base_snapshot(pods=[_make_pod(cpu_requested=0.0, mem_requested_gb=0.0)])
        result = enrich_with_cost(snap)
        self.assertEqual(result["pods"][0]["cost_per_hour"], 0.0)


# ─────────────────────────────────────────────────────────────────────────────
# PART 4 — sanitize
# ─────────────────────────────────────────────────────────────────────────────

class TestSanitize(unittest.TestCase):

    def _enriched_snap(self, **kwargs):
        return enrich_with_cost(_base_snapshot(**kwargs))

    # ── structure ─────────────────────────────────────────────────────────────
    def test_returns_dict(self):
        self.assertIsInstance(sanitize(self._enriched_snap()), dict)

    def test_top_level_keys_exact(self):
        result = sanitize(self._enriched_snap())
        expected = {"captured_at", "cluster_name", "cost_summary",
                    "nodes", "pods", "deployments", "services", "pvcs"}
        self.assertEqual(set(result.keys()), expected)

    def test_captured_at_preserved(self):
        snap = self._enriched_snap()
        result = sanitize(snap)
        self.assertEqual(result["captured_at"], snap["captured_at"])

    def test_cluster_name_preserved(self):
        snap = self._enriched_snap()
        result = sanitize(snap)
        self.assertEqual(result["cluster_name"], snap["cluster_name"])

    # ── cost_summary stripped correctly ───────────────────────────────────────
    def test_cost_summary_has_exactly_3_keys(self):
        result = sanitize(self._enriched_snap())
        self.assertEqual(set(result["cost_summary"].keys()),
                         {"total_cost_per_hour", "total_wasted_per_hour", "total_wasted_per_month"})

    def test_cost_summary_no_reference_vm_sku(self):
        result = sanitize(self._enriched_snap())
        self.assertNotIn("reference_vm_sku", result["cost_summary"])

    # ── pod fields ────────────────────────────────────────────────────────────
    def test_pod_has_exactly_required_fields(self):
        result = sanitize(self._enriched_snap())
        expected_fields = {
            "name", "namespace", "status", "restart_count",
            "cpu_requested", "mem_requested_gb", "cpu_actual", "mem_actual_gb",
            "has_cpu_limit", "has_mem_limit",
            "cost_per_hour", "wasted_cost_per_hour", "wasted_cost_per_month",
        }
        self.assertEqual(set(result["pods"][0].keys()), expected_fields)

    def test_pod_no_actual_cost_per_hour(self):
        """actual_cost_per_hour is internal only — must not leak into sanitized output."""
        result = sanitize(self._enriched_snap())
        self.assertNotIn("actual_cost_per_hour", result["pods"][0])

    def test_pod_types_correct(self):
        result = sanitize(self._enriched_snap())
        pod = result["pods"][0]
        self.assertIsInstance(pod["name"], str)
        self.assertIsInstance(pod["namespace"], str)
        self.assertIsInstance(pod["status"], str)
        self.assertIsInstance(pod["restart_count"], int)
        self.assertIsInstance(pod["cpu_requested"], float)
        self.assertIsInstance(pod["mem_requested_gb"], float)
        self.assertIsInstance(pod["cpu_actual"], float)
        self.assertIsInstance(pod["mem_actual_gb"], float)
        self.assertIsInstance(pod["has_cpu_limit"], bool)
        self.assertIsInstance(pod["has_mem_limit"], bool)
        self.assertIsInstance(pod["cost_per_hour"], float)
        self.assertIsInstance(pod["wasted_cost_per_hour"], float)
        self.assertIsInstance(pod["wasted_cost_per_month"], float)

    # ── node fields ───────────────────────────────────────────────────────────
    def test_node_has_exact_fields(self):
        result = sanitize(self._enriched_snap())
        expected = {"name", "cpu_capacity", "mem_capacity_gb", "cpu_usage", "mem_usage_gb"}
        self.assertEqual(set(result["nodes"][0].keys()), expected)

    # ── deployment fields ─────────────────────────────────────────────────────
    def test_deployment_has_exact_fields(self):
        result = sanitize(self._enriched_snap())
        expected = {"name", "namespace", "desired_replicas", "ready_replicas"}
        self.assertEqual(set(result["deployments"][0].keys()), expected)

    # ── service fields ────────────────────────────────────────────────────────
    def test_service_has_exact_fields(self):
        result = sanitize(self._enriched_snap())
        expected = {"name", "namespace", "type", "port"}
        self.assertEqual(set(result["services"][0].keys()), expected)

    # ── pvc fields ────────────────────────────────────────────────────────────
    def test_pvc_has_exact_fields(self):
        result = sanitize(self._enriched_snap())
        expected = {"name", "namespace", "status", "capacity_gb", "storage_class"}
        self.assertEqual(set(result["pvcs"][0].keys()), expected)

    # ── empty collections ─────────────────────────────────────────────────────
    def test_empty_nodes(self):
        result = sanitize(enrich_with_cost(_base_snapshot(nodes=[])))
        self.assertEqual(result["nodes"], [])

    def test_empty_pods(self):
        result = sanitize(enrich_with_cost(_base_snapshot(pods=[])))
        self.assertEqual(result["pods"], [])

    def test_empty_pvcs(self):
        result = sanitize(enrich_with_cost(_base_snapshot(pvcs=[])))
        self.assertEqual(result["pvcs"], [])

    # ── missing / None field resilience ───────────────────────────────────────
    def test_missing_cost_summary_defaults_to_zero(self):
        snap = _base_snapshot()  # no cost_summary key yet
        result = sanitize(snap)
        self.assertEqual(result["cost_summary"]["total_cost_per_hour"], 0.0)

    def test_pod_missing_optional_fields_does_not_crash(self):
        """Sanitize should not crash even if a pod is mostly empty."""
        minimal_pod = {"name": "bare-pod"}
        snap = _base_snapshot(pods=[minimal_pod])
        try:
            result = sanitize(enrich_with_cost(snap))
            self.assertEqual(result["pods"][0]["name"], "bare-pod")
        except Exception as exc:
            self.fail(f"sanitize crashed on minimal pod: {exc}")

    def test_none_values_cast_correctly(self):
        pod = _make_pod()
        pod["restart_count"] = None
        snap = _base_snapshot(pods=[pod])
        result = sanitize(enrich_with_cost(snap))
        # Should cast None to 0 without crashing
        self.assertEqual(result["pods"][0]["restart_count"], 0)

    # ── no mutation of input ──────────────────────────────────────────────────
    def test_input_not_mutated(self):
        enriched = enrich_with_cost(_base_snapshot())
        original = copy.deepcopy(enriched)
        sanitize(enriched)
        self.assertEqual(enriched, original)

    # ── JSON serializable ─────────────────────────────────────────────────────
    def test_output_is_json_serializable(self):
        result = sanitize(self._enriched_snap())
        try:
            json.dumps(result)
        except TypeError as exc:
            self.fail(f"Output is not JSON serializable: {exc}")

    # ── token_estimate ────────────────────────────────────────────────────────
    def test_token_estimate_returns_int(self):
        result = sanitize(self._enriched_snap())
        self.assertIsInstance(token_estimate(result), int)

    def test_token_estimate_positive(self):
        result = sanitize(self._enriched_snap())
        self.assertGreater(token_estimate(result), 0)

    def test_token_estimate_formula(self):
        d = {"key": "value"}
        raw = json.dumps(d)
        self.assertEqual(token_estimate(d), len(raw) // 4)

    def test_small_cluster_under_token_budget(self):
        """A single-node minikube cluster should comfortably fit within 6000 tokens."""
        pods = [_make_pod(f"pod-{i}") for i in range(10)]
        result = sanitize(enrich_with_cost(_base_snapshot(pods=pods)))
        tokens = token_estimate(result)
        self.assertLess(tokens, 6000, f"Token count {tokens} exceeds 6000 for a 10-pod cluster.")


# ─────────────────────────────────────────────────────────────────────────────
# PART 5 — Full pipeline integration
# ─────────────────────────────────────────────────────────────────────────────

class TestFullPipeline(unittest.TestCase):

    def _run_pipeline(self, **kwargs):
        raw = _base_snapshot(**kwargs)
        enriched = enrich_with_cost(raw)
        return sanitize(enriched)

    def test_pipeline_returns_dict(self):
        self.assertIsInstance(self._run_pipeline(), dict)

    def test_pipeline_preserves_pod_count(self):
        pods = [_make_pod(f"p{i}") for i in range(4)]
        result = self._run_pipeline(pods=pods)
        self.assertEqual(len(result["pods"]), 4)

    def test_pipeline_preserves_node_count(self):
        nodes = [_make_node(f"node-{i}") for i in range(2)]
        result = self._run_pipeline(nodes=nodes)
        self.assertEqual(len(result["nodes"]), 2)

    def test_pipeline_cost_fields_flow_through(self):
        pods = [_make_pod(cpu_requested=0.5, mem_requested_gb=0.5,
                           cpu_actual=0.0, mem_actual_gb=0.0)]
        result = self._run_pipeline(pods=pods)
        pod = result["pods"][0]
        self.assertGreater(pod["cost_per_hour"], 0.0)
        self.assertGreater(pod["wasted_cost_per_hour"], 0.0)
        self.assertGreater(pod["wasted_cost_per_month"], 0.0)

    def test_pipeline_cost_summary_flows_through(self):
        result = self._run_pipeline()
        cs = result["cost_summary"]
        self.assertIn("total_cost_per_hour", cs)
        self.assertIn("total_wasted_per_hour", cs)
        self.assertIn("total_wasted_per_month", cs)

    def test_pipeline_output_is_json_serializable(self):
        result = self._run_pipeline()
        try:
            json.dumps(result)
        except TypeError as exc:
            self.fail(f"Pipeline output is not JSON serializable: {exc}")

    def test_crash_loop_pod_scenario(self):
        """Simulate a crash-loop pod: pending, has cost, wasted = cost."""
        pod = _make_pod(
            name="crash-loop-pod",
            namespace="podpilot-demo",
            status="Pending",
            restart_count=12,
            cpu_requested=0.05,
            mem_requested_gb=0.0625,
            cpu_actual=0.0,
            mem_actual_gb=0.0,
            has_cpu_limit=True,
            has_mem_limit=True,
        )
        result = self._run_pipeline(pods=[pod])
        p = result["pods"][0]
        self.assertEqual(p["status"], "Pending")
        self.assertEqual(p["restart_count"], 12)
        self.assertGreater(p["cost_per_hour"], 0.0)
        # wasted == cost when actual == 0
        self.assertAlmostEqual(p["wasted_cost_per_hour"], p["cost_per_hour"], places=6)

    def test_no_limits_pod_scenario(self):
        """No requests set → cost and wasted both 0."""
        pod = _make_pod(
            name="no-limits-pod",
            cpu_requested=0.0,
            mem_requested_gb=0.0,
            cpu_actual=0.05,
            mem_actual_gb=0.03,
            has_cpu_limit=False,
            has_mem_limit=False,
        )
        result = self._run_pipeline(pods=[pod])
        p = result["pods"][0]
        self.assertFalse(p["has_cpu_limit"])
        self.assertFalse(p["has_mem_limit"])
        self.assertEqual(p["cost_per_hour"], 0.0)
        self.assertEqual(p["wasted_cost_per_hour"], 0.0)

    def test_oversized_deployment_scenario(self):
        """5 replicas requesting large resources, near-zero actual → high wastage."""
        pods = [
            _make_pod(
                f"oversized-{i}",
                namespace="podpilot-demo",
                cpu_requested=0.5,
                mem_requested_gb=0.5,
                cpu_actual=0.002,
                mem_actual_gb=0.003,
            )
            for i in range(5)
        ]
        result = self._run_pipeline(pods=pods)
        total_wasted_month = result["cost_summary"]["total_wasted_per_month"]
        # 5 replicas × ~$11/mo each = ~$55/mo wasted
        self.assertGreater(total_wasted_month, 50.0)

    def test_nodeport_service_type_preserved(self):
        svc = _make_service(name="exposed", svc_type="NodePort", port=32001)
        result = self._run_pipeline(services=[svc])
        self.assertEqual(result["services"][0]["type"], "NodePort")
        self.assertEqual(result["services"][0]["port"], 32001)

    def test_orphan_pvc_scenario(self):
        pvc = _make_pvc(name="orphan-pvc", namespace="podpilot-demo",
                         status="Bound", capacity_gb=1.0, storage_class="standard")
        result = self._run_pipeline(pvcs=[pvc])
        p = result["pvcs"][0]
        self.assertEqual(p["name"], "orphan-pvc")
        self.assertEqual(p["status"], "Bound")
        self.assertEqual(p["capacity_gb"], 1.0)

    def test_empty_cluster_pipeline(self):
        """No pods/nodes/services — pipeline should return empty lists without crashing."""
        result = self._run_pipeline(pods=[], nodes=[], deployments=[], services=[], pvcs=[])
        self.assertEqual(result["pods"], [])
        self.assertEqual(result["nodes"], [])
        self.assertEqual(result["deployments"], [])
        self.assertEqual(result["services"], [])
        self.assertEqual(result["pvcs"], [])
        self.assertEqual(result["cost_summary"]["total_cost_per_hour"], 0.0)

    def test_pipeline_single_line_call(self):
        """Verifies the documented one-liner works end-to-end on synthetic data."""
        raw = _base_snapshot()
        clean = sanitize(enrich_with_cost(raw))
        self.assertIn("pods", clean)
        self.assertIn("cost_summary", clean)


# ─────────────────────────────────────────────────────────────────────────────
# entry point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    unittest.main(verbosity=2)
