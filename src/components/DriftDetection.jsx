import { useState } from "react";
import {
  GitCompareArrows,
  RefreshCw,
  Sparkles,
  Plus,
  Minus,
  ArrowRight,
  RotateCcw,
  AlertTriangle,
  Server,
  Box,
  Network,
  HardDrive,
  Clock,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
} from "lucide-react";

// ---------------------------------------------------------------------------
// Mock data — mirrors the real /drift/poll response from main.py + drift_detection.py
// ---------------------------------------------------------------------------
const MOCK_POLL_RESULT = {
  changes_detected: 6,
  diff_summary: `- deployment/batch-worker (ns: jobs) replicas: 2 -> 4
- pod/ml-training-pod-v2 (ns: ml-workloads) is new
- pod/legacy-api-74d9f (ns: production) status: Running -> CrashLoopBackOff
- pod/old-cache-xyz (ns: production) was removed
- pod/worker-3 restart count: 1 -> 4
- service/frontend type: ClusterIP -> NodePort`,
  ai_explanation: `**deployment/batch-worker replicas: 2 → 4**
This scale-up was likely triggered by a Horizontal Pod Autoscaler responding to elevated queue depth or CPU load. Monitor closely — if traffic has normalised, consider scaling back to avoid unnecessary cost.

**pod/ml-training-pod-v2 is new**
A new training pod has been scheduled in the ml-workloads namespace. This is expected if a new experiment was kicked off. Verify it has appropriate resource limits to avoid starving other workloads.

**pod/legacy-api-74d9f status: Running → CrashLoopBackOff**
The pod is repeatedly crashing, which usually indicates a misconfiguration, OOM kill, or unhandled startup error. Check logs immediately with \`kubectl logs legacy-api-74d9f -n production\` — this is likely impacting production traffic.

**pod/old-cache-xyz was removed**
A cache pod was removed from the production namespace. If this was not intentional, it could indicate an eviction due to resource pressure or a manual delete. Verify downstream services aren't depending on this pod.

**pod/worker-3 restart count: 1 → 4**
Three additional restarts in a short window suggest worker-3 is becoming unhealthy. Common causes include memory leaks or failed health checks. Consider checking the pod's resource usage and recent logs.

**service/frontend type: ClusterIP → NodePort**
The frontend service was changed to NodePort, exposing it directly on the node's IP. This is a security concern — ensure firewall rules are in place and consider switching to an Ingress controller for production traffic.`,
};

// Snapshot timeline mock (what the "timeline" tab shows)
const MOCK_TIMELINE = [
  {
    id: "snap-004",
    timestamp: "2026-07-15T12:28:00Z",
    label: "12:28 UTC",
    changes: 6,
    severity: "critical",
  },
  {
    id: "snap-003",
    timestamp: "2026-07-15T12:08:00Z",
    label: "12:08 UTC",
    changes: 1,
    severity: "info",
  },
  {
    id: "snap-002",
    timestamp: "2026-07-15T11:48:00Z",
    label: "11:48 UTC",
    changes: 0,
    severity: "clean",
  },
  {
    id: "snap-001",
    timestamp: "2026-07-15T11:28:00Z",
    label: "11:28 UTC",
    changes: 3,
    severity: "warning",
  },
  {
    id: "snap-000",
    timestamp: "2026-07-15T11:08:00Z",
    label: "11:08 UTC",
    changes: 0,
    severity: "clean",
  },
];

// ---------------------------------------------------------------------------
// Parse diff_summary lines into structured change objects
// ---------------------------------------------------------------------------
function parseDiffLine(line) {
  // Strip leading "- "
  const text = line.replace(/^- /, "").trim();

  // deployment/{name} (ns: {ns}) replicas: {old} -> {new}
  let m = text.match(/^deployment\/(\S+)\s+\(ns:\s*(\S+)\)\s+replicas:\s+(\d+)\s*->\s*(\d+)/);
  if (m) {
    return {
      kind: "deployment",
      name: m[1],
      ns: m[2],
      type: "scale",
      from: m[3],
      to: m[4],
      text,
      severity: parseInt(m[4]) > parseInt(m[3]) ? "info" : "warning",
    };
  }

  // pod/{name} (ns: {ns}) is new
  m = text.match(/^pod\/(\S+)\s+\(ns:\s*(\S+)\)\s+is new/);
  if (m) {
    return { kind: "pod", name: m[1], ns: m[2], type: "added", text, severity: "info" };
  }

  // pod/{name} (ns: {ns}) was removed
  m = text.match(/^pod\/(\S+)\s+\(ns:\s*(\S+)\)\s+was removed/);
  if (m) {
    return { kind: "pod", name: m[1], ns: m[2], type: "removed", text, severity: "warning" };
  }

  // pod/{name} restart count: {old} -> {new}
  m = text.match(/^pod\/(\S+)\s+restart count:\s+(\d+)\s*->\s+(\d+)/);
  if (m) {
    return {
      kind: "pod",
      name: m[1],
      ns: null,
      type: "restart",
      from: m[2],
      to: m[3],
      text,
      severity: parseInt(m[3]) >= 4 ? "critical" : "warning",
    };
  }

  // pod/{name} status: {old} -> {new}
  m = text.match(/^pod\/(\S+)\s+status:\s+(\S+)\s*->\s*(\S+)/);
  if (m) {
    const isBad = /crash|fail|error|oom/i.test(m[3]);
    return {
      kind: "pod",
      name: m[1],
      ns: null,
      type: "status",
      from: m[2],
      to: m[3],
      text,
      severity: isBad ? "critical" : "info",
    };
  }

  // service/{name} type: {old} -> {new}
  m = text.match(/^service\/(\S+)\s+type:\s+(\S+)\s*->\s*(\S+)/);
  if (m) {
    const dangerous = m[3] === "NodePort" || m[3] === "LoadBalancer";
    return {
      kind: "service",
      name: m[1],
      ns: null,
      type: "type-change",
      from: m[2],
      to: m[3],
      text,
      severity: dangerous ? "critical" : "info",
    };
  }

  // pvc/{name} status: {old} -> {new}
  m = text.match(/^pvc\/(\S+)\s+status:\s+(\S+)\s*->\s*(\S+)/);
  if (m) {
    return {
      kind: "pvc",
      name: m[1],
      ns: null,
      type: "pvc-status",
      from: m[2],
      to: m[3],
      text,
      severity: m[3] === "Lost" ? "critical" : "warning",
    };
  }

  // fallback
  return { kind: "unknown", name: text, ns: null, type: "other", text, severity: "info" };
}

function parseDiffSummary(summary) {
  return summary
    .split("\n")
    .filter((l) => l.trim())
    .map(parseDiffLine);
}

// Parse AI explanation into per-change blocks
function parseExplanation(text) {
  // Split on bold headings **...**
  const blocks = text.split(/\n\n(?=\*\*)/);
  return blocks.map((block) => {
    const headingMatch = block.match(/^\*\*(.+?)\*\*\n?([\s\S]*)/);
    if (headingMatch) {
      return { heading: headingMatch[1], body: headingMatch[2].trim() };
    }
    return { heading: null, body: block.trim() };
  });
}

// ---------------------------------------------------------------------------
// Severity config
// ---------------------------------------------------------------------------
const SEV = {
  critical: { color: "#ff6b6b", bg: "#ff6b6b14", border: "#ff6b6b30", label: "Critical" },
  warning: { color: "#f5a623", bg: "#f5a62314", border: "#f5a62330", label: "Warning" },
  info: { color: "#4f6df5", bg: "#4f6df514", border: "#4f6df530", label: "Info" },
  clean: { color: "#50e3c2", bg: "#50e3c214", border: "#50e3c230", label: "Clean" },
};

// ---------------------------------------------------------------------------
// Change type icon + label
// ---------------------------------------------------------------------------
function changeIcon(change) {
  const sz = 14;
  switch (change.type) {
    case "added":
      return <Plus size={sz} />;
    case "removed":
      return <Minus size={sz} />;
    case "restart":
      return <RotateCcw size={sz} />;
    case "status":
      return <AlertTriangle size={sz} />;
    case "scale":
      return <ArrowRight size={sz} />;
    case "type-change":
      return <Network size={sz} />;
    case "pvc-status":
      return <HardDrive size={sz} />;
    default:
      return <Server size={sz} />;
  }
}

function kindIcon(kind) {
  const sz = 13;
  switch (kind) {
    case "pod":
      return <Box size={sz} />;
    case "deployment":
      return <Server size={sz} />;
    case "service":
      return <Network size={sz} />;
    case "pvc":
      return <HardDrive size={sz} />;
    default:
      return <Server size={sz} />;
  }
}

// ---------------------------------------------------------------------------
// Change card
// ---------------------------------------------------------------------------
function ChangeCard({ change }) {
  const sev = SEV[change.severity] || SEV.info;
  return (
    <div
      className="flex items-start gap-3.5 rounded-2xl border px-4 py-3.5 transition hover:brightness-110"
      style={{ background: sev.bg, borderColor: sev.border }}
    >
      {/* Change type icon */}
      <div
        className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg"
        style={{ background: sev.color + "22", color: sev.color }}
      >
        {changeIcon(change)}
      </div>

      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          {/* Kind badge */}
          <span
            className="flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold"
            style={{ color: sev.color, background: sev.color + "22" }}
          >
            {kindIcon(change.kind)}
            {change.kind}
          </span>

          {/* Severity badge */}
          <span
            className="rounded-full px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide"
            style={{ color: sev.color, background: sev.color + "22" }}
          >
            {sev.label}
          </span>

          {/* namespace if present */}
          {change.ns && (
            <span className="rounded-full bg-[#1c2235] px-2 py-0.5 text-[11px] text-[#9099ab]">
              ns: {change.ns}
            </span>
          )}
        </div>

        {/* Resource name */}
        <p className="m-0 mt-1.5 text-[13.5px] font-semibold text-[#e7e9ee]">
          {change.kind}/{change.name}
        </p>

        {/* Change detail */}
        {change.from !== undefined && (
          <div className="mt-1 flex items-center gap-1.5 text-[12.5px] text-[#9099ab]">
            <span className="rounded bg-[#1c2235] px-1.5 py-0.5 font-mono text-[11.5px] text-[#e7e9ee]">
              {change.from}
            </span>
            <ArrowRight size={11} className="text-[#9099ab]" />
            <span
              className="rounded px-1.5 py-0.5 font-mono text-[11.5px] font-semibold"
              style={{ background: sev.color + "22", color: sev.color }}
            >
              {change.to}
            </span>
          </div>
        )}
        {change.from === undefined && (
          <p className="m-0 mt-1 text-[12.5px] text-[#9099ab] capitalize">
            {change.type.replace("-", " ")}
          </p>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// AI explanation block
// ---------------------------------------------------------------------------
function AiExplanation({ explanation }) {
  const [open, setOpen] = useState(true);
  const blocks = parseExplanation(explanation);

  return (
    <div className="rounded-2xl border border-[#4f6df5]/25 bg-[#4f6df5]/[0.06]">
      <button
        className="flex w-full items-center gap-2.5 px-5 py-4 transition hover:bg-white/[0.02]"
        onClick={() => setOpen((v) => !v)}
      >
        <Sparkles size={15} className="shrink-0 text-[#4f6df5]" />
        <span className="text-[13.5px] font-semibold text-[#e7e9ee]">AI Drift Analysis</span>
        <span className="ml-2 rounded-full bg-[#4f6df5]/20 px-2 py-0.5 text-[11px] text-[#4f6df5]">
          Groq · llama-3.3-70b
        </span>
        <span className="ml-auto text-[#9099ab]">
          {open ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
        </span>
      </button>

      {open && (
        <div className="border-t border-[#4f6df5]/15 px-5 py-4">
          <div className="flex flex-col gap-5">
            {blocks.map((block, i) => (
              <div key={i}>
                {block.heading && (
                  <p className="m-0 mb-1.5 text-[13px] font-bold text-[#e7e9ee]">
                    {block.heading}
                  </p>
                )}
                <p className="m-0 text-[13px] leading-relaxed text-[#9099ab]">{block.body}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Timeline sidebar
// ---------------------------------------------------------------------------
function TimelineItem({ snap, active, onClick }) {
  const sev = SEV[snap.severity] || SEV.clean;
  return (
    <button
      onClick={onClick}
      className={`flex w-full items-center gap-3 rounded-xl border px-3.5 py-3 text-left transition ${
        active ? "border-[#4f6df5]/40 bg-[#4f6df5]/10" : "border-[#1c2235] bg-[#0f1220] hover:bg-white/[0.03]"
      }`}
    >
      {/* dot */}
      <span
        className="mt-0.5 h-2.5 w-2.5 shrink-0 rounded-full"
        style={{ background: sev.color }}
      />
      <div className="min-w-0 flex-1">
        <div className="flex items-center justify-between gap-2">
          <span className="text-[12.5px] font-semibold text-[#e7e9ee]">{snap.label}</span>
          {snap.changes > 0 && (
            <span
              className="rounded-full px-1.5 py-0.5 text-[11px] font-bold"
              style={{ color: sev.color, background: sev.color + "22" }}
            >
              {snap.changes}
            </span>
          )}
        </div>
        <p className="m-0 mt-0.5 text-[11.5px] text-[#9099ab]">
          {snap.changes === 0 ? "No changes" : `${snap.changes} change${snap.changes !== 1 ? "s" : ""} detected`}
        </p>
      </div>
    </button>
  );
}

// ---------------------------------------------------------------------------
// Polling controls
// ---------------------------------------------------------------------------
function PollStatus({ lastPolled, polling, onPoll }) {
  return (
    <div className="flex items-center gap-3 rounded-2xl border border-[#1c2235] bg-[#0f1220] px-5 py-3.5">
      <div className="flex flex-1 items-center gap-2">
        <Clock size={14} className="text-[#9099ab]" />
        <span className="text-[12.5px] text-[#9099ab]">
          Last polled: <span className="font-semibold text-[#e7e9ee]">{lastPolled}</span>
        </span>
      </div>
      <div className="flex items-center gap-2">
        <span className="flex items-center gap-1.5 rounded-full bg-[#50e3c2]/10 px-2.5 py-1 text-[11.5px] font-semibold text-[#50e3c2]">
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[#50e3c2]" />
          Auto-polling every 20 min
        </span>
        <button
          onClick={onPoll}
          disabled={polling}
          className="flex items-center gap-1.5 rounded-xl border border-[#4f6df5]/30 bg-[#4f6df5]/10 px-3.5 py-2 text-[12.5px] font-semibold text-[#4f6df5] transition hover:bg-[#4f6df5]/20 disabled:cursor-not-allowed disabled:opacity-50"
        >
          <RefreshCw size={13} className={polling ? "animate-spin" : ""} />
          Poll Now
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Empty state
// ---------------------------------------------------------------------------
function NoDrift() {
  return (
    <div className="flex flex-col items-center justify-center gap-4 py-20 text-center">
      <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-[#50e3c2]/10">
        <CheckCircle2 size={26} className="text-[#50e3c2]" />
      </div>
      <div>
        <p className="m-0 text-[16px] font-bold text-[#e7e9ee]">No Drift Detected</p>
        <p className="m-0 mt-1 text-[13.5px] text-[#9099ab]">
          Your cluster looks identical to the previous snapshot.
        </p>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------
export default function DriftDetection() {
  const [polling, setPolling] = useState(false);
  const [lastPolled, setLastPolled] = useState("2 mins ago");
  const [activeSnap, setActiveSnap] = useState(MOCK_TIMELINE[0].id);
  const [result] = useState(MOCK_POLL_RESULT);

  const changes = parseDiffSummary(result.diff_summary);

  // Severity counts
  const criticalCount = changes.filter((c) => c.severity === "critical").length;
  const warningCount = changes.filter((c) => c.severity === "warning").length;
  const infoCount = changes.filter((c) => c.severity === "info").length;

  function handlePoll() {
    setPolling(true);
    setTimeout(() => {
      setPolling(false);
      setLastPolled("just now");
    }, 1800);
  }

  return (
    <div className="flex h-full min-h-0 flex-1 overflow-hidden bg-[#0d0f18]">
      {/* ── Left: timeline sidebar ── */}
      <div className="flex w-[220px] shrink-0 flex-col gap-3 border-r border-[#1c2235] bg-[#0a0c14] px-4 py-6 overflow-y-auto">
        <p className="m-0 mb-1 text-[11px] font-semibold uppercase tracking-wider text-[#9099ab]">
          Snapshot History
        </p>
        {MOCK_TIMELINE.map((snap) => (
          <TimelineItem
            key={snap.id}
            snap={snap}
            active={snap.id === activeSnap}
            onClick={() => setActiveSnap(snap.id)}
          />
        ))}
      </div>

      {/* ── Main content ── */}
      <div className="flex flex-1 min-w-0 flex-col overflow-y-auto">
        <div className="mx-auto w-full max-w-4xl px-8 py-8">

          {/* ── Header ── */}
          <div className="mb-6">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h1 className="m-0 flex items-center gap-2 text-[22px] font-bold text-[#e7e9ee]">
                  <GitCompareArrows size={22} className="text-[#4f6df5]" />
                  Drift Detection
                </h1>
                <p className="m-0 mt-1 text-[13.5px] text-[#9099ab]">
                  Comparing snapshot <span className="font-semibold text-[#e7e9ee]">snap-003</span> →{" "}
                  <span className="font-semibold text-[#e7e9ee]">snap-004</span> · 20 min interval
                </p>
              </div>

              {/* Severity summary pills */}
              <div className="flex shrink-0 items-center gap-2">
                {criticalCount > 0 && (
                  <span className="flex items-center gap-1.5 rounded-full bg-[#ff6b6b]/10 px-3 py-1.5 text-[12px] font-bold text-[#ff6b6b]">
                    <AlertTriangle size={12} />
                    {criticalCount} Critical
                  </span>
                )}
                {warningCount > 0 && (
                  <span className="flex items-center gap-1.5 rounded-full bg-[#f5a623]/10 px-3 py-1.5 text-[12px] font-bold text-[#f5a623]">
                    {warningCount} Warning
                  </span>
                )}
                {infoCount > 0 && (
                  <span className="flex items-center gap-1.5 rounded-full bg-[#4f6df5]/10 px-3 py-1.5 text-[12px] font-bold text-[#4f6df5]">
                    {infoCount} Info
                  </span>
                )}
              </div>
            </div>
          </div>

          {/* ── Poll status bar ── */}
          <div className="mb-6">
            <PollStatus lastPolled={lastPolled} polling={polling} onPoll={handlePoll} />
          </div>

          {result.changes_detected === 0 ? (
            <NoDrift />
          ) : (
            <div className="flex flex-col gap-6">

              {/* ── Change summary header ── */}
              <div className="flex items-center justify-between">
                <p className="m-0 text-[12px] font-semibold uppercase tracking-wider text-[#9099ab]">
                  {result.changes_detected} Changes Detected
                </p>
                {/* mini legend */}
                <div className="flex items-center gap-3 text-[11.5px] text-[#9099ab]">
                  <span className="flex items-center gap-1">
                    <span className="h-2 w-2 rounded-full bg-[#ff6b6b]" /> Critical
                  </span>
                  <span className="flex items-center gap-1">
                    <span className="h-2 w-2 rounded-full bg-[#f5a623]" /> Warning
                  </span>
                  <span className="flex items-center gap-1">
                    <span className="h-2 w-2 rounded-full bg-[#4f6df5]" /> Info
                  </span>
                </div>
              </div>

              {/* ── Change cards ── */}
              {/* Critical first */}
              {["critical", "warning", "info"].map((sev) => {
                const group = changes.filter((c) => c.severity === sev);
                if (!group.length) return null;
                const sevCfg = SEV[sev];
                return (
                  <div key={sev}>
                    <p
                      className="m-0 mb-3 text-[11.5px] font-semibold uppercase tracking-wider"
                      style={{ color: sevCfg.color }}
                    >
                      {sevCfg.label}
                    </p>
                    <div className="flex flex-col gap-3">
                      {group.map((change, i) => (
                        <ChangeCard key={i} change={change} />
                      ))}
                    </div>
                  </div>
                );
              })}

              {/* ── AI explanation ── */}
              <AiExplanation explanation={result.ai_explanation} />

              {/* ── Raw diff summary (collapsible) ── */}
              <RawDiff summary={result.diff_summary} />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Raw diff collapsible
// ---------------------------------------------------------------------------
function RawDiff({ summary }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-2xl border border-[#1c2235] bg-[#0f1220]">
      <button
        className="flex w-full items-center gap-2 px-5 py-3.5 transition hover:bg-white/[0.02]"
        onClick={() => setOpen((v) => !v)}
      >
        <span className="text-[12.5px] font-semibold text-[#9099ab]">Raw diff_summary</span>
        <span className="ml-auto text-[#9099ab]">
          {open ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </span>
      </button>
      {open && (
        <div className="border-t border-[#1c2235] px-5 py-4">
          <pre className="m-0 whitespace-pre-wrap font-mono text-[12px] leading-relaxed text-[#9099ab]">
            {summary}
          </pre>
        </div>
      )}
    </div>
  );
}
