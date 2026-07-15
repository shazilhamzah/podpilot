import { useState, useRef, useEffect } from "react";
import {
  DollarSign,
  TrendingDown,
  Layers,
  ChevronDown,
  ChevronRight,
  AlertTriangle,
  CheckCircle2,
  Info,
} from "lucide-react";

// ---------------------------------------------------------------------------
// Mock data — shape mirrors the real /snapshot/ai-ready response from cost.py
// ---------------------------------------------------------------------------
const MOCK_SNAPSHOT = {
  cluster_cost_per_hour: 0.195,
  cluster_cost_per_month: 142.35,
  cluster_wasted_cost_per_hour: 0.0524,
  cluster_wasted_cost_per_month: 38.25,
  pods: [
    {
      name: "ml-training-pod",
      namespace: "ml-workloads",
      status_phase: "Running",
      cpu_requested_cores: 2.0,
      memory_requested_gb: 4.0,
      cpu_actual_cores: 0.18,
      memory_actual_gb: 0.31,
      cost_per_hour: 0.078,
      cost_per_month: 56.94,
      wasted_cost_per_hour: 0.0611,
      wasted_cost_per_month: 44.6,
    },
    {
      name: "legacy-api",
      namespace: "production",
      status_phase: "Running",
      cpu_requested_cores: 1.0,
      memory_requested_gb: 2.0,
      cpu_actual_cores: 0.12,
      memory_actual_gb: 0.09,
      cost_per_hour: 0.039,
      cost_per_month: 28.47,
      wasted_cost_per_hour: 0.0141,
      wasted_cost_per_month: 10.29,
    },
    {
      name: "nginx-ingress",
      namespace: "production",
      status_phase: "Running",
      cpu_requested_cores: 0.5,
      memory_requested_gb: 0.5,
      cpu_actual_cores: 0.19,
      memory_actual_gb: 0.11,
      cost_per_hour: 0.0175,
      cost_per_month: 12.78,
      wasted_cost_per_hour: 0.0025,
      wasted_cost_per_month: 1.82,
    },
    {
      name: "redis-cache",
      namespace: "production",
      status_phase: "Running",
      cpu_requested_cores: 0.5,
      memory_requested_gb: 1.0,
      cpu_actual_cores: 0.08,
      memory_actual_gb: 0.62,
      cost_per_hour: 0.0195,
      cost_per_month: 14.24,
      wasted_cost_per_hour: 0.0013,
      wasted_cost_per_month: 0.95,
    },
    {
      name: "worker-3",
      namespace: "jobs",
      status_phase: "Running",
      cpu_requested_cores: 0.25,
      memory_requested_gb: 0.5,
      cpu_actual_cores: 0.21,
      memory_actual_gb: 0.43,
      cost_per_hour: 0.00775,
      cost_per_month: 5.66,
      wasted_cost_per_hour: 0.000125,
      wasted_cost_per_month: 0.09,
    },
    {
      name: "batch-worker",
      namespace: "jobs",
      status_phase: "Pending",
      cpu_requested_cores: 1.0,
      memory_requested_gb: 1.0,
      cpu_actual_cores: 0.0,
      memory_actual_gb: 0.0,
      cost_per_hour: 0.035,
      cost_per_month: 25.55,
      wasted_cost_per_hour: 0.035,
      wasted_cost_per_month: 25.55,
    },
    {
      name: "monitoring-agent",
      namespace: "kube-system",
      status_phase: "Running",
      cpu_requested_cores: 0.1,
      memory_requested_gb: 0.25,
      cpu_actual_cores: 0.04,
      memory_actual_gb: 0.09,
      cost_per_hour: 0.0041,
      cost_per_month: 2.99,
      wasted_cost_per_hour: 0.0009,
      wasted_cost_per_month: 0.66,
    },
  ],
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function fmt$(v) {
  return `$${v.toFixed(2)}`;
}
function fmtPct(actual, requested) {
  if (!requested) return "—";
  return `${Math.round((actual / requested) * 100)}%`;
}

function groupByNamespace(pods) {
  const map = {};
  pods.forEach((p) => {
    const cost_per_month = (p.cost_per_hour || 0) * 730;
    const wasted_cost_per_month = p.wasted_cost_per_month || 0;

    if (!map[p.namespace]) {
      map[p.namespace] = {
        namespace: p.namespace,
        pods: [],
        cost_per_month: 0,
        wasted_cost_per_month: 0,
      };
    }

    const normalizedPod = {
      ...p,
      cost_per_month,
      wasted_cost_per_month,
      cpu_requested_cores: p.cpu_requested || 0,
      memory_requested_gb: p.mem_requested_gb || 0,
      cpu_actual_cores: p.cpu_actual || 0,
      memory_actual_gb: p.mem_actual_gb || 0,
    };

    map[p.namespace].pods.push(normalizedPod);
    map[p.namespace].cost_per_month += cost_per_month;
    map[p.namespace].wasted_cost_per_month += wasted_cost_per_month;
  });
  return Object.values(map).sort((a, b) => b.cost_per_month - a.cost_per_month);
}

// ---------------------------------------------------------------------------
// Donut chart (pure SVG, no library)
// ---------------------------------------------------------------------------
function DonutChart({ total, wasted }) {
  const effective = total - wasted;
  const R = 54;
  const CIRC = 2 * Math.PI * R;
  const wastedDash = (wasted / total) * CIRC;
  const effectiveDash = (effective / total) * CIRC;
  const wastePercent = Math.round((wasted / total) * 100);

  return (
    <div className="relative flex items-center justify-center" style={{ width: 148, height: 148 }}>
      <svg viewBox="0 0 140 140" width={148} height={148} className="rotate-[-90deg]">
        {/* Track */}
        <circle cx={70} cy={70} r={R} fill="none" stroke="#1c2235" strokeWidth={18} />
        {/* Effective cost arc */}
        <circle
          cx={70}
          cy={70}
          r={R}
          fill="none"
          stroke="#4f6df5"
          strokeWidth={18}
          strokeLinecap="butt"
          strokeDasharray={`${effectiveDash} ${CIRC}`}
          strokeDashoffset={0}
        />
        {/* Wasted cost arc */}
        <circle
          cx={70}
          cy={70}
          r={R}
          fill="none"
          stroke="#f5a623"
          strokeWidth={18}
          strokeLinecap="butt"
          strokeDasharray={`${wastedDash} ${CIRC}`}
          strokeDashoffset={-effectiveDash}
        />
      </svg>
      {/* Center label */}
      <div className="absolute flex flex-col items-center leading-none">
        <span className="text-[11px] text-[#9099ab] mb-1">Waste</span>
        <span className="text-[22px] font-bold text-[#f5a623]">{wastePercent}%</span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Summary metric cards
// ---------------------------------------------------------------------------
function MetricCard({ icon: Icon, label, value, sub, color, glow }) {
  return (
    <div
      className="flex flex-1 flex-col gap-2 rounded-2xl border px-5 py-4"
      style={{
        background: "rgba(23,28,42,0.7)",
        borderColor: color + "33",
        boxShadow: glow ? `0 0 28px ${color}18` : "none",
      }}
    >
      <div
        className="flex h-8 w-8 items-center justify-center rounded-xl"
        style={{ background: color + "1a" }}
      >
        <Icon size={16} style={{ color }} />
      </div>
      <div>
        <p className="m-0 text-[12px] text-[#9099ab]">{label}</p>
        <p className="m-0 mt-0.5 text-[24px] font-bold leading-none" style={{ color }}>
          {value}
        </p>
        {sub && <p className="m-0 mt-1 text-[11.5px] text-[#9099ab]">{sub}</p>}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Efficiency bar
// ---------------------------------------------------------------------------
function EfficiencyBar({ actual, requested, color = "#4f6df5" }) {
  const pct = requested > 0 ? Math.min((actual / requested) * 100, 100) : 0;
  const barColor = pct < 30 ? "#f5a623" : pct > 80 ? "#50e3c2" : "#4f6df5";
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-16 overflow-hidden rounded-full bg-[#1c2235]">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${pct}%`, background: barColor }}
        />
      </div>
      <span className="text-[11.5px] text-[#9099ab]">{Math.round(pct)}%</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Status badge for pod phase
// ---------------------------------------------------------------------------
function PhaseBadge({ phase }) {
  const cfg = {
    Running: { color: "#50e3c2", bg: "#50e3c21a" },
    Pending: { color: "#f5a623", bg: "#f5a6231a" },
    Failed: { color: "#ff6b6b", bg: "#ff6b6b1a" },
  }[phase] || { color: "#9099ab", bg: "#9099ab1a" };

  return (
    <span
      className="inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-semibold"
      style={{ color: cfg.color, background: cfg.bg }}
    >
      {phase}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Waste indicator icon
// ---------------------------------------------------------------------------
function WasteIcon({ pct }) {
  if (pct > 50)
    return <AlertTriangle size={13} className="text-[#f5a623]" />;
  if (pct < 15)
    return <CheckCircle2 size={13} className="text-[#50e3c2]" />;
  return <Info size={13} className="text-[#9099ab]" />;
}

// ---------------------------------------------------------------------------
// Namespace group row (collapsible)
// ---------------------------------------------------------------------------
function NamespaceGroup({ group, totalClusterCost }) {
  const [open, setOpen] = useState(true);
  const pct = totalClusterCost > 0 ? (group.cost_per_month / totalClusterCost) * 100 : 0;

  return (
    <div className="overflow-hidden rounded-2xl border border-[#1c2235] bg-[#0f1220]">
      {/* Group header */}
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-3 px-5 py-3.5 transition hover:bg-white/[0.02]"
      >
        {open ? (
          <ChevronDown size={15} className="shrink-0 text-[#9099ab]" />
        ) : (
          <ChevronRight size={15} className="shrink-0 text-[#9099ab]" />
        )}
        <Layers size={14} className="shrink-0 text-[#4f6df5]" />
        <span className="text-[13.5px] font-semibold text-[#e7e9ee]">{group.namespace}</span>
        <span className="ml-auto flex items-center gap-3">
          <span className="text-[12px] text-[#9099ab]">
            {group.pods.length} pod{group.pods.length !== 1 && "s"}
          </span>
          {/* namespace cost bar */}
          <div className="hidden w-24 sm:block">
            <div className="h-1.5 overflow-hidden rounded-full bg-[#1c2235]">
              <div
                className="h-full rounded-full bg-[#4f6df5] transition-all duration-500"
                style={{ width: `${Math.min(pct, 100)}%` }}
              />
            </div>
          </div>
          <span className="min-w-[64px] text-right text-[13.5px] font-bold text-[#e7e9ee]">
            {fmt$(group.cost_per_month)}<span className="text-[11px] font-normal text-[#9099ab]">/mo</span>
          </span>
          <span className="min-w-[52px] text-right text-[12px] text-[#f5a623]">
            {fmt$(group.wasted_cost_per_month)} wasted
          </span>
        </span>
      </button>

      {/* Pod rows */}
      {open && (
        <div className="border-t border-[#1c2235]">
          {/* Table header */}
          <div className="grid items-center gap-3 px-5 py-2.5 text-[11px] font-semibold uppercase tracking-wider text-[#9099ab]"
            style={{ gridTemplateColumns: "minmax(140px,2fr) 80px repeat(4,1fr) minmax(90px,1fr) minmax(80px,1fr)" }}>
            <span>Pod</span>
            <span>Phase</span>
            <span>CPU Req</span>
            <span>CPU Use%</span>
            <span>Mem Req</span>
            <span>Mem Use%</span>
            <span className="text-right">Cost/mo</span>
            <span className="text-right">Wasted/mo</span>
          </div>

          {group.pods.map((pod) => {
            const wastePct =
              pod.cost_per_month > 0
                ? (pod.wasted_cost_per_month / pod.cost_per_month) * 100
                : 0;
            return (
              <div
                key={pod.name}
                className="grid items-center gap-3 border-t border-[#1c2235] px-5 py-3.5 text-[13px] transition hover:bg-white/[0.025]"
                style={{ gridTemplateColumns: "minmax(140px,2fr) 80px repeat(4,1fr) minmax(90px,1fr) minmax(80px,1fr)" }}
              >
                {/* Name */}
                <span className="truncate font-medium text-[#e7e9ee]" title={pod.name}>
                  {pod.name}
                </span>

                {/* Phase */}
                <PhaseBadge phase={pod.status_phase} />

                {/* CPU Requested */}
                <span className="text-[#9099ab]">{pod.cpu_requested_cores}c</span>

                {/* CPU Efficiency bar */}
                <EfficiencyBar actual={pod.cpu_actual_cores} requested={pod.cpu_requested_cores} />

                {/* Memory Requested */}
                <span className="text-[#9099ab]">{pod.memory_requested_gb} GB</span>

                {/* Memory Efficiency bar */}
                <EfficiencyBar actual={pod.memory_actual_gb} requested={pod.memory_requested_gb} />

                {/* Cost per month */}
                <span className="text-right font-semibold text-[#e7e9ee]">
                  {fmt$(pod.cost_per_month)}
                </span>

                {/* Wasted */}
                <span className="flex items-center justify-end gap-1.5">
                  <WasteIcon pct={wastePct} />
                  <span
                    className="font-medium"
                    style={{ color: wastePct > 50 ? "#f5a623" : wastePct < 15 ? "#50e3c2" : "#9099ab" }}
                  >
                    {fmt$(pod.wasted_cost_per_month)}
                  </span>
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------
export default function CostBreakdown() {
  const [snap, setSnap] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchSnapshot = async () => {
      try {
        const backendUrl = import.meta.env.VITE_API_BASE_URL || `http://${window.location.hostname}:8000`;
        const response = await fetch(`${backendUrl}/snapshot`);
        if (!response.ok) throw new Error("Failed to fetch snapshot");
        const data = await response.json();
        setSnap(data.data);
      } catch (err) {
        setError(err.message);
      }
    };
    fetchSnapshot();
  }, []);

  if (error) return (
    <div className="flex flex-1 min-h-0 items-center justify-center bg-[#0d0f18]">
      <p className="text-[#ff6b6b]">Error loading cost data: {error}</p>
    </div>
  );
  if (!snap) return (
    <div className="flex flex-1 min-h-0 flex-col items-center justify-center bg-[#0d0f18] text-[#9099ab]">
      <div className="flex items-center gap-3">
        {[0, 1, 2].map((i) => (
          <div
            key={i}
            className="h-2.5 w-2.5 animate-bounce rounded-full bg-[#4f6df5]"
            style={{ animationDelay: `${i * 0.15}s` }}
          />
        ))}
      </div>
      <p className="mt-5 text-[14px] font-medium tracking-wide">Crunching cluster costs...</p>
      <p className="mt-1 text-[12px] text-[#9099ab]/60">Pulling live data from your cluster</p>
    </div>
  );

  const costSummary = snap.cost_summary || {};
  const cluster_cost_per_hour = costSummary.total_cost_per_hour || 0;
  const cluster_cost_per_month = cluster_cost_per_hour * 730;
  const cluster_wasted_cost_per_month = costSummary.total_wasted_per_month || 0;
  const cluster_wasted_cost_per_hour = costSummary.total_wasted_per_hour || 0;

  const groups = groupByNamespace(snap.pods);
  const effectiveCost = cluster_cost_per_month - cluster_wasted_cost_per_month;
  const wastePercent = cluster_cost_per_month > 0 ? Math.round(
    (cluster_wasted_cost_per_month / cluster_cost_per_month) * 100
  ) : 0;

  return (
    <div className="flex h-full min-h-0 flex-1 flex-col overflow-y-auto bg-[#0d0f18]">
      <div className="mx-auto w-full max-w-6xl px-8 py-8">

        {/* ── Page title ── */}
        <div className="mb-7">
          <h1 className="m-0 text-[22px] font-bold text-[#e7e9ee]">Cost Breakdown</h1>
          <p className="m-0 mt-1 text-[13.5px] text-[#9099ab]">
            Heuristic-based pricing · {snap.pods.length} pods across {groups.length} namespaces
          </p>
        </div>

        {/* ── Top section: summary cards + donut ── */}
        <div className="mb-8 flex flex-col gap-6 lg:flex-row lg:items-start">

          {/* Metric cards */}
          <div className="flex flex-1 flex-col gap-4">
            <div className="flex gap-4">
              <MetricCard
                icon={DollarSign}
                label="Total Monthly Cost"
                value={fmt$(cluster_cost_per_month)}
                sub={`${fmt$(cluster_cost_per_hour)}/hr`}
                color="#4f6df5"
                glow
              />
              <MetricCard
                icon={CheckCircle2}
                label="Effective Cost"
                value={fmt$(effectiveCost)}
                sub="actually utilized"
                color="#50e3c2"
              />
            </div>
            <div className="flex gap-4">
              <MetricCard
                icon={TrendingDown}
                label="Wasted Cost"
                value={fmt$(cluster_wasted_cost_per_month)}
                sub={`${fmt$(cluster_wasted_cost_per_hour)}/hr · ${wastePercent}% of budget`}
                color="#f5a623"
                glow
              />
              <MetricCard
                icon={Layers}
                label="Namespaces"
                value={groups.length}
                sub={`${snap.pods.length} pods total`}
                color="#9b8afb"
              />
            </div>
          </div>

          {/* Donut + legend */}
          <div
            className="flex shrink-0 items-center gap-7 rounded-2xl border border-[#1c2235] bg-[#0f1220] px-7 py-6"
          >
            <DonutChart total={cluster_cost_per_month} wasted={cluster_wasted_cost_per_month} />
            <div className="flex flex-col gap-4">
              <div>
                <div className="flex items-center gap-2">
                  <span className="h-2.5 w-2.5 rounded-full bg-[#4f6df5]" />
                  <span className="text-[12.5px] text-[#9099ab]">Effective Spend</span>
                </div>
                <p className="m-0 mt-0.5 pl-[18px] text-[18px] font-bold text-[#e7e9ee]">
                  {fmt$(effectiveCost)}
                </p>
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <span className="h-2.5 w-2.5 rounded-full bg-[#f5a623]" />
                  <span className="text-[12.5px] text-[#9099ab]">Wasted Resources</span>
                </div>
                <p className="m-0 mt-0.5 pl-[18px] text-[18px] font-bold text-[#f5a623]">
                  {fmt$(cluster_wasted_cost_per_month)}
                </p>
              </div>
              <p className="m-0 mt-1 max-w-[160px] text-[11.5px] leading-snug text-[#9099ab]">
                Wasted cost = requested but unused CPU & memory
              </p>
            </div>
          </div>
        </div>

        {/* ── Namespace cost share bar ── */}
        <div className="mb-7 overflow-hidden rounded-2xl border border-[#1c2235] bg-[#0f1220] px-5 py-4">
          <p className="m-0 mb-3 text-[12px] font-semibold uppercase tracking-wider text-[#9099ab]">
            Cost by namespace
          </p>
          {/* Stacked bar */}
          <div className="flex h-5 w-full overflow-hidden rounded-full">
            {groups.map((g, i) => {
              const pct = (g.cost_per_month / cluster_cost_per_month) * 100;
              const COLORS = ["#4f6df5", "#9b8afb", "#50e3c2", "#f5a623", "#ff6b6b"];
              return (
                <div
                  key={g.namespace}
                  title={`${g.namespace}: ${fmt$(g.cost_per_month)}/mo`}
                  className="h-full first:rounded-l-full last:rounded-r-full transition-all"
                  style={{ width: `${pct}%`, background: COLORS[i % COLORS.length] }}
                />
              );
            })}
          </div>
          {/* Legend */}
          <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1.5">
            {groups.map((g, i) => {
              const COLORS = ["#4f6df5", "#9b8afb", "#50e3c2", "#f5a623", "#ff6b6b"];
              return (
                <div key={g.namespace} className="flex items-center gap-1.5">
                  <span className="h-2 w-2 rounded-full" style={{ background: COLORS[i % COLORS.length] }} />
                  <span className="text-[12px] text-[#9099ab]">{g.namespace}</span>
                  <span className="text-[12px] font-semibold text-[#e7e9ee]">{fmt$(g.cost_per_month)}</span>
                </div>
              );
            })}
          </div>
        </div>

        {/* ── Per-namespace groups ── */}
        <div className="flex flex-col gap-4">
          <p className="m-0 text-[12px] font-semibold uppercase tracking-wider text-[#9099ab]">
            Pod-level breakdown
          </p>
          {groups.map((g) => (
            <NamespaceGroup
              key={g.namespace}
              group={g}
              totalClusterCost={cluster_cost_per_month}
            />
          ))}
        </div>

        {/* ── Footer note ── */}
        <p className="mt-6 text-center text-[11.5px] leading-relaxed text-[#9099ab]">
          Pricing heuristic · {" "}
          <span className="text-[#4f6df5]">$0.031/vCPU-hr</span> + <span className="text-[#4f6df5]">$0.004/GB-hr</span> · 730 hrs/month · not linked to cloud billing API
        </p>
      </div>
    </div>
  );
}
