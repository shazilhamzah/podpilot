# 06 — Frontend Live Cost Badge

**What to build:** Surface the `cost_source` field (introduced in ticket 05) in the dashboard so users immediately know whether cost figures are real Azure billing data or estimates. The cost section should show a **🟢 Live Azure Cost** badge when the source is `"opencost"` and a **🟡 Estimated** badge when it is `"estimated"`. No backend changes are required — this is purely a UI enhancement reading an already-present field in the API response.

**Blocked by:** 05 — Replace Hardcoded Costs with Live OpenCost Data (the `cost_source` field must exist in the API response before the UI can read it).

**Status:** done

- [x] Cost section of the dashboard reads `cost_source` from the API response
- [x] A **🟢 Live Azure Cost** badge is displayed when `cost_source` is `"opencost"`
- [x] A **🟡 Estimated** badge is displayed when `cost_source` is `"estimated"` or the field is absent
- [x] Badge is visible both at the summary level and per-pod in the cost breakdown view
- [x] Badge renders correctly in both light and dark modes (if applicable)
- [x] No backend or API contract changes are introduced by this ticket
