# 05 — Replace Hardcoded Costs with Live OpenCost Data

**What to build:** Replace the static VM SKU price constants in the cost module with real per-pod cost data pulled from the OpenCost allocation API that the AKS Cost Analysis add-on exposes inside the cluster. Each pod in the snapshot gains a `cost_source` field — `"opencost"` when real data is available, `"estimated"` when OpenCost is unreachable (local dev). The cost summary also carries this field. When running in AKS the dashboard cost figures reflect actual billed Azure spend. When running locally the old estimation logic kicks in silently as a fallback, so the developer experience is unchanged.

**Blocked by:** 03 — Swap AI Backend from Groq to Azure OpenAI **and** 04 — Migrate Persistent Storage to Azure Cosmos DB (the app must be fully deployed end-to-end in AKS, which means the Cost Analysis add-on from ticket 01 must also be running and accumulating data).

**Status:** done

- [x] Cost module queries the in-cluster OpenCost allocation API aggregated by pod
- [x] Per-pod `cost_per_hour`, `actual_cost_per_hour`, `wasted_cost_per_hour`, and `wasted_cost_per_month` are derived from OpenCost `totalCost`, `cpuCost`, and `ramCost` fields when available
- [x] Each pod in the snapshot includes a `cost_source` field: `"opencost"` or `"estimated"`
- [x] Top-level `cost_summary` includes a `cost_source` field reflecting whether any OpenCost data was used
- [x] When the OpenCost endpoint is unreachable the module falls back to estimated costs without raising an error
- [x] The OpenCost endpoint URL is configurable via an environment variable
- [x] Cost figures shown in the AKS-deployed dashboard match actual Azure billed amounts (spot-check against the Azure Cost Analysis view in the portal)
