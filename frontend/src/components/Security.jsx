import { useState, useEffect } from "react";
import { cachedFetch } from "../utils/fetchCache";
import {
  ShieldCheck,
  ShieldAlert,
  ShieldX,
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Network,
  Box,
  Lock,
  Tag,
  Users,
  Eye,
  ExternalLink,
  Bot,
  Terminal
} from "lucide-react";

// ---------------------------------------------------------------------------
const CATEGORIES = ["All", "Network", "Pod Security", "RBAC", "Image Security", "security", "Other"];

const CATEGORY_ICONS = {
  Network: Network,
  "Pod Security": Box,
  RBAC: Users,
  "Image Security": Tag,
  "security": ShieldAlert,
  "Other": AlertCircle,
};

// ---------------------------------------------------------------------------
// Severity config
// ---------------------------------------------------------------------------
const SEV = {
  critical: {
    color: "#ff6b6b",
    bg: "#ff6b6b0d",
    border: "#ff6b6b28",
    label: "Critical",
    Icon: ShieldX,
  },
  warning: {
    color: "#f5a623",
    bg: "#f5a6230d",
    border: "#f5a62328",
    label: "Warning",
    Icon: ShieldAlert,
  },
  info: {
    color: "#4f6df5",
    bg: "#4f6df50d",
    border: "#4f6df528",
    label: "Info",
    Icon: Eye,
  },
  passed: {
    color: "#50e3c2",
    bg: "#50e3c20d",
    border: "#50e3c228",
    label: "Passed",
    Icon: ShieldCheck,
  },
};

// ---------------------------------------------------------------------------
// Security score ring (pure SVG)
// ---------------------------------------------------------------------------
function ScoreRing({ score, total, passed, warnings, criticals }) {
  const pct = score / 100;
  const R = 52;
  const CIRC = 2 * Math.PI * R;
  const filledDash = pct * CIRC;
  const color = score >= 80 ? "#50e3c2" : score >= 55 ? "#f5a623" : "#ff6b6b";
  const label = score >= 80 ? "Good" : score >= 55 ? "Fair" : "Poor";

  return (
    <div className="flex items-center gap-8">
      {/* Ring */}
      <div className="relative flex items-center justify-center" style={{ width: 136, height: 136 }}>
        <svg viewBox="0 0 136 136" width={136} height={136} className="rotate-[-90deg]">
          <circle cx={68} cy={68} r={R} fill="none" stroke="#1c2235" strokeWidth={16} />
          <circle
            cx={68} cy={68} r={R}
            fill="none"
            stroke={color}
            strokeWidth={16}
            strokeLinecap="round"
            strokeDasharray={`${filledDash} ${CIRC}`}
            style={{ filter: `drop-shadow(0 0 8px ${color}55)` }}
          />
        </svg>
        <div className="absolute flex flex-col items-center leading-none">
          <span className="text-[28px] font-bold" style={{ color }}>{score}</span>
          <span className="mt-0.5 text-[11px] font-semibold" style={{ color }}>{label}</span>
        </div>
      </div>

      {/* Stats */}
      <div className="flex flex-col gap-3">
        <div>
          <p className="m-0 text-[11px] text-[#9099ab]">Security Score</p>
          <p className="m-0 text-[13px] font-semibold text-[#e7e9ee]">out of 100</p>
        </div>
        <div className="flex flex-col gap-2">
          <StatRow color="#ff6b6b" label="Critical" value={criticals} />
          <StatRow color="#f5a623" label="Warning" value={warnings} />
          <StatRow color="#50e3c2" label="Passed" value={passed} />
          <StatRow color="#9099ab" label="Total checks" value={total} />
        </div>
      </div>
    </div>
  );
}

function StatRow({ color, label, value }) {
  return (
    <div className="flex items-center gap-2">
      <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: color }} />
      <span className="text-[12px] text-[#9099ab]">{label}</span>
      <span className="ml-1 text-[13px] font-bold" style={{ color }}>{value}</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Check card (expandable)
// ---------------------------------------------------------------------------
function CheckCard({ check, selectedSnapshotId }) {
  const [open, setOpen] = useState(false);
  const [solution, setSolution] = useState(null);
  const [loadingSolution, setLoadingSolution] = useState(false);
  
  const rawSev = check.passed ? "passed" : (check.severity || "info").toLowerCase();
  const sev = SEV[rawSev] || SEV.info;
  const SevIcon = sev.Icon;

  const handleGetSolution = async () => {
    setLoadingSolution(true);
    setSolution(null);
    try {
      const backendUrl = import.meta.env.VITE_API_BASE_URL || `http://${window.location.hostname}:8000`;
      const res = await fetch(`${backendUrl}/solution`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: check.title,
          description: check.description,
          remediation: check.remediation,
          resources: check.resources
        })
      });
      if (!res.ok) throw new Error("Failed to fetch solution");
      const data = await res.json();
      setSolution(data.answer);
    } catch (err) {
      console.error(err);
      setSolution("Failed to fetch solution. Please try again later.");
    } finally {
      setLoadingSolution(false);
    }
  };

  return (
    <div
      className="overflow-hidden rounded-2xl border transition-all duration-200"
      style={{ background: sev.bg, borderColor: sev.border }}
    >
      {/* Header row */}
      <button
        className="flex w-full items-start gap-3.5 px-5 py-4 text-left transition hover:brightness-110"
        onClick={() => setOpen((v) => !v)}
      >
        {/* Icon */}
        <div
          className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-xl"
          style={{ background: sev.color + "22", color: sev.color }}
        >
          <SevIcon size={16} />
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span
              className="rounded-full px-2 py-0.5 text-[11px] font-bold uppercase tracking-wide"
              style={{ color: sev.color, background: sev.color + "22" }}
            >
              {sev.label}
            </span>
            {check.resources.length > 0 && (
              <span className="rounded-full bg-[#1c2235] px-2 py-0.5 text-[11px] text-[#9099ab]">
                {check.resources.length} resource{check.resources.length !== 1 ? "s" : ""}
              </span>
            )}
          </div>
          <p className="m-0 mt-1.5 text-[14px] font-semibold text-[#e7e9ee]">{check.title}</p>
          <p className="m-0 mt-1 text-[12.5px] leading-snug text-[#9099ab] line-clamp-2">
            {check.description}
          </p>
        </div>

        <span className="mt-1 ml-2 shrink-0 text-[#9099ab]">
          {open ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
        </span>
      </button>

      {/* Expanded detail */}
      {open && (
        <div className="border-t px-5 pb-5 pt-4" style={{ borderColor: sev.border }}>
          <div className="flex flex-col gap-4">
            {/* Full description */}
            <div>
              <p className="m-0 mb-1.5 text-[11.5px] font-semibold uppercase tracking-wider text-[#9099ab]">
                Details
              </p>
              <p className="m-0 text-[13px] leading-relaxed text-[#c8ccd6]">{check.description}</p>
            </div>

            {/* Affected resources */}
            {check.resources.length > 0 && (
              <div>
                <p className="m-0 mb-2 text-[11.5px] font-semibold uppercase tracking-wider text-[#9099ab]">
                  Affected Resources
                </p>
                <ul className="m-0 flex flex-col gap-1.5 pl-0 list-none">
                  {check.resources.map((r) => (
                    <li
                      key={r}
                      className="flex items-center gap-2 rounded-lg px-3 py-2 font-mono text-[12px]"
                      style={{ background: sev.color + "12", color: sev.color }}
                    >
                      <AlertCircle size={11} className="shrink-0" />
                      {r}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {check.note && (
              <p className="m-0 text-[12px] italic text-[#9099ab]">{check.note}</p>
            )}

            {/* Remediation */}
            <div
              className="rounded-xl border px-4 py-3"
              style={{ borderColor: "#50e3c228", background: "#50e3c208" }}
            >
              <div className="flex items-start justify-between">
                <div>
                  <p className="m-0 mb-1 flex items-center gap-1.5 text-[11.5px] font-semibold uppercase tracking-wider text-[#50e3c2]">
                    <CheckCircle2 size={12} />
                    Remediation
                  </p>
                  <p className="m-0 text-[12.5px] leading-relaxed text-[#9099ab]">
                    {check.remediation}
                  </p>
                </div>
                {!solution && (
                  <button
                    onClick={handleGetSolution}
                    disabled={loadingSolution}
                    className="flex shrink-0 items-center gap-1.5 rounded-lg bg-[#50e3c215] px-3 py-1.5 text-[12px] font-medium text-[#50e3c2] transition hover:bg-[#50e3c225] disabled:opacity-50"
                  >
                    {loadingSolution ? (
                      <span className="flex items-center gap-1.5">
                        <div className="h-3 w-3 animate-spin rounded-full border-2 border-current border-t-transparent"></div>
                        Thinking...
                      </span>
                    ) : (
                      <>
                        <Bot size={14} />
                        Get AI Solution
                      </>
                    )}
                  </button>
                )}
              </div>

              {solution && (
                <div className="mt-4 rounded-lg bg-[#0d0f18] border border-[#1c2235] p-3">
                  <div className="mb-2 flex items-center justify-between">
                    <p className="m-0 flex items-center gap-1.5 text-[11.5px] font-semibold uppercase tracking-wider text-[#4f6df5]">
                      <Terminal size={12} />
                      AI Solution
                    </p>
                    <button
                      onClick={handleGetSolution}
                      disabled={loadingSolution}
                      className="text-[11px] text-[#9099ab] hover:text-[#e7e9ee] transition"
                    >
                      {loadingSolution ? "Refreshing..." : "Refresh"}
                    </button>
                  </div>
                  <div className="text-[12.5px] leading-relaxed text-[#e7e9ee] whitespace-pre-wrap font-mono">
                    {solution}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Severity section
// ---------------------------------------------------------------------------
function SeveritySection({ severity, checks, selectedSnapshotId }) {
  const sevKey = severity.toLowerCase();
  const sevCfg = SEV[sevKey] || SEV.info;
  const Icon = sevCfg.Icon;
  const count = checks.length;

  return (
    <div>
      {/* Section heading */}
      <div className="mb-3 flex items-center gap-2.5">
        <div 
          className="flex h-7 w-7 items-center justify-center rounded-lg"
          style={{ background: sevCfg.bg }}
        >
          <Icon size={14} style={{ color: sevCfg.color }} />
        </div>
        <p className="m-0 text-[13.5px] font-bold text-[#e7e9ee] capitalize">{severity}</p>
        <div className="flex items-center gap-1.5 ml-1">
          <span 
            className="rounded-full px-2 py-0.5 text-[11px] font-bold"
            style={{ background: sevCfg.bg, color: sevCfg.color }}
          >
            {count} issue{count !== 1 ? 's' : ''}
          </span>
        </div>
      </div>

      <div className="flex flex-col gap-3">
        {checks.map((c) => <CheckCard key={c.id} check={c} selectedSnapshotId={selectedSnapshotId} />)}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Resource section
// ---------------------------------------------------------------------------
function ResourceSection({ resource, checks, selectedSnapshotId }) {
  const count = checks.length;
  const hasCritical = checks.some((c) => c.severity.toLowerCase() === "critical");
  const hasWarning = checks.some((c) => c.severity.toLowerCase() === "warning");
  const maxSev = hasCritical ? "critical" : hasWarning ? "warning" : "info";
  const sevCfg = SEV[maxSev] || SEV.info;
  const Icon = Box; // using Box icon for resource

  return (
    <div>
      {/* Section heading */}
      <div className="mb-3 flex items-center gap-2.5">
        <div 
          className="flex h-7 w-7 items-center justify-center rounded-lg"
          style={{ background: sevCfg.bg }}
        >
          <Icon size={14} style={{ color: sevCfg.color }} />
        </div>
        <p className="m-0 text-[13.5px] font-bold text-[#e7e9ee] font-mono break-all">{resource}</p>
        <div className="flex items-center gap-1.5 ml-1">
          <span 
            className="rounded-full px-2 py-0.5 text-[11px] font-bold"
            style={{ background: sevCfg.bg, color: sevCfg.color }}
          >
            {count} issue{count !== 1 ? 's' : ''}
          </span>
        </div>
      </div>

      <div className="flex flex-col gap-3">
        {checks.map((c) => <CheckCard key={c.id} check={c} selectedSnapshotId={selectedSnapshotId} />)}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------
export default function Security({ selectedSnapshotId, snapshots }) {
  const [viewMode, setViewMode] = useState("severity");
  const [activeSeverity, setActiveSeverity] = useState("All");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [issues, setIssues] = useState([]);

  useEffect(() => {
    async function fetchSecurity() {
      setLoading(true);
      setError(null);
      try {
        const backendUrl = import.meta.env.VITE_API_BASE_URL || `http://${window.location.hostname}:8000`;
        const url = selectedSnapshotId 
          ? `${backendUrl}/security?snapshot_id=${selectedSnapshotId}`
          : `${backendUrl}/security`;
        
        const res = await cachedFetch(url);
        if (!res.ok) throw new Error("Failed to fetch security analysis");
        
        const data = await res.json();
        
        // Map backend issues to frontend expected structure
        const mappedIssues = (data.issues || []).map((issue, index) => ({
          id: `issue-${index}`,
          category: issue.category || "Other",
          severity: issue.severity || "info",
          title: issue.title || "Security finding",
          description: issue.description || "No description provided.",
          remediation: issue.remediation || "Investigate the affected resource.",
          resources: issue.affected_resource ? [issue.affected_resource] : [],
          passed: false
        }));
        
        setIssues(mappedIssues);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    }
    fetchSecurity();
  }, [selectedSnapshotId]);

  const currentSnap = snapshots?.find(s => s.id === selectedSnapshotId);
  const isCacheMiss = currentSnap && !currentSnap.cached_analyses?.includes("security");

  if (loading) {
    return (
      <div className="flex h-full flex-1 flex-col items-center justify-center bg-[#0d0f18]">
        <div className="flex items-center gap-2 text-[#4f6df5] mb-4">
          <div className="h-2 w-2 animate-bounce rounded-full bg-current" style={{ animationDelay: "0ms" }}></div>
          <div className="h-2 w-2 animate-bounce rounded-full bg-current" style={{ animationDelay: "150ms" }}></div>
          <div className="h-2 w-2 animate-bounce rounded-full bg-current" style={{ animationDelay: "300ms" }}></div>
        </div>
        <p className="text-[#9099ab] text-sm animate-pulse max-w-sm text-center">
          {isCacheMiss ? (
            <span>
              Analyzing snapshot for the first time...<br/>
              Running security vulnerability scans.
            </span>
          ) : (
            <span>Scanning cluster for security vulnerabilities...</span>
          )}
          <br/><br/>
          (Note: If this is the first scan, it may take 1-2 minutes to download the latest vulnerability database. Please don't navigate away.)
        </p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex h-full flex-1 items-center justify-center bg-[#0d0f18] text-red-400">
        <AlertTriangle className="mr-2" /> Error: {error}
      </div>
    );
  }

  // Derive filtered checks
  const filtered =
    activeSeverity === "All"
      ? issues
      : issues.filter((c) => c.severity.toLowerCase() === activeSeverity.toLowerCase());

  // Stats
  const totalChecks = issues.length;
  const passedChecks = 0; // Backend only returns failed checks
  const criticalChecks = issues.filter((c) => !c.passed && c.severity === "critical").length;
  const warningChecks = issues.filter((c) => !c.passed && c.severity === "warning").length;
  const infoChecks = issues.filter((c) => !c.passed && c.severity === "info").length;
  
  // Dynamic Score logic: Base 100, heavily penalize vulnerabilities
  const score = totalChecks === 0 ? 100 : Math.max(
    0,
    Math.round(100 - criticalChecks * 15 - warningChecks * 7 - infoChecks * 3)
  );

  // Group filtered checks by severity
  const availableSeverities = ["critical", "warning", "info"].filter(
    sev => issues.some(i => i.severity.toLowerCase() === sev)
  );
  
  const groupedSeverities =
    activeSeverity === "All"
      ? availableSeverities
          .map((sev) => ({
            sev,
            checks: filtered.filter((c) => c.severity.toLowerCase() === sev),
          }))
          .filter((g) => g.checks.length > 0)
      : [{ sev: activeSeverity.toLowerCase(), checks: filtered }];

  // Group by resource
  const resourceMap = {};
  filtered.forEach(issue => {
    const resList = issue.resources && issue.resources.length > 0 ? issue.resources : ["Unknown Resource"];
    resList.forEach(res => {
      if (!resourceMap[res]) resourceMap[res] = [];
      resourceMap[res].push(issue);
    });
  });
  
  const groupedResources = Object.entries(resourceMap).map(([resource, checks]) => ({
    resource,
    checks
  }));

  // Sort resources by max severity then by issue count
  groupedResources.sort((a, b) => {
    const aCrit = a.checks.some(c => c.severity.toLowerCase() === "critical") ? 1 : 0;
    const bCrit = b.checks.some(c => c.severity.toLowerCase() === "critical") ? 1 : 0;
    if (aCrit !== bCrit) return bCrit - aCrit;
    
    const aWarn = a.checks.some(c => c.severity.toLowerCase() === "warning") ? 1 : 0;
    const bWarn = b.checks.some(c => c.severity.toLowerCase() === "warning") ? 1 : 0;
    if (aWarn !== bWarn) return bWarn - aWarn;

    return b.checks.length - a.checks.length;
  });

  return (
    <div className="flex h-full min-h-0 flex-1 flex-col overflow-y-auto bg-[#0d0f18]">
      <div className="mx-auto w-full max-w-5xl px-8 py-8">

        <div className="mb-7">
          <h1 className="m-0 text-[22px] font-bold text-[#e7e9ee]">Security</h1>
          <p className="m-0 mt-1 text-[13.5px] text-[#9099ab]">
            {totalChecks === 0 ? "No active issues found" : `${totalChecks} issues across ${availableSeverities.length} severities`} · live cluster snapshot
          </p>
        </div>

        {/* ── Top: score + summary bar ── */}
        <div className="mb-8 flex flex-col gap-5 lg:flex-row lg:items-stretch">
          {/* Score card */}
          <div className="flex shrink-0 items-center rounded-2xl border border-[#1c2235] bg-[#0f1220] px-7 py-5">
            <ScoreRing
              score={score}
              total={totalChecks}
              passed={passedChecks}
              warnings={warningChecks}
              criticals={criticalChecks}
            />
          </div>

          {/* Severity summary grid */}
          <div className="grid flex-1 grid-cols-3 gap-3">
            {availableSeverities.map((sevName) => {
              const sevChecks = issues.filter((c) => c.severity.toLowerCase() === sevName.toLowerCase());
              const count = sevChecks.length;
              const sevKey = sevName.toLowerCase();
              const sevCfg = SEV[sevKey] || SEV.info;
              const Icon = sevCfg.Icon;
              
              return (
                <button
                  key={sevName}
                  onClick={() => setActiveSeverity(sevName === activeSeverity ? "All" : sevName)}
                  className="flex items-start gap-3 rounded-2xl border px-4 py-3.5 text-left transition hover:brightness-110"
                  style={{
                    background: sevCfg.bg,
                    borderColor: activeSeverity === sevName ? sevCfg.color + "55" : sevCfg.border,
                    boxShadow: activeSeverity === sevName ? `0 0 0 1px ${sevCfg.color}33` : "none",
                  }}
                >
                  <div
                    className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg"
                    style={{ background: sevCfg.color + "22", color: sevCfg.color }}
                  >
                    <Icon size={14} />
                  </div>
                  <div>
                    <p className="m-0 text-[13px] font-semibold text-[#e7e9ee] capitalize">{sevName}</p>
                    <div className="mt-1 flex flex-wrap gap-1.5">
                      <span className="text-[11px] font-bold" style={{ color: sevCfg.color }}>
                        {count} issue{count !== 1 ? 's' : ''}
                      </span>
                    </div>
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        {/* ── View Mode & Severity filter tabs ── */}
        <div className="mb-6 flex flex-col gap-4">
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
              <span className="text-[12px] font-semibold text-[#9099ab] uppercase tracking-wider">Group By:</span>
              <div className="flex rounded-lg border border-[#1c2235] bg-[#0f1220] p-1">
                <button
                  onClick={() => setViewMode("severity")}
                  className={`rounded-md px-4 py-1.5 text-[12px] font-medium transition-all ${
                    viewMode === "severity"
                      ? "bg-[#2a2f45] text-[#e7e9ee] shadow-sm"
                      : "text-[#9099ab] hover:text-[#e7e9ee]"
                  }`}
                >
                  Severity
                </button>
                <button
                  onClick={() => setViewMode("resource")}
                  className={`rounded-md px-4 py-1.5 text-[12px] font-medium transition-all ${
                    viewMode === "resource"
                      ? "bg-[#2a2f45] text-[#e7e9ee] shadow-sm"
                      : "text-[#9099ab] hover:text-[#e7e9ee]"
                  }`}
                >
                  Resource
                </button>
              </div>
            </div>
            
            <div className="h-6 w-px bg-[#1c2235]"></div>
            
            <div className="flex flex-wrap items-center gap-2">
              {["All", ...availableSeverities].map((sevName) => {
                const active = sevName === activeSeverity;
                return (
                  <button
                    key={sevName}
                    onClick={() => setActiveSeverity(sevName)}
                    className="rounded-full border px-3.5 py-1.5 text-[12.5px] font-medium transition-all capitalize"
                    style={
                      active
                        ? {
                            background: "#4f6df5",
                            borderColor: "#4f6df5",
                            color: "#fff",
                            boxShadow: "0 0 14px #4f6df544",
                          }
                        : {
                            background: "#0f1220",
                            borderColor: "#1c2235",
                            color: "#9099ab",
                          }
                    }
                  >
                    {sevName}
                  </button>
                );
              })}
              
              {/* Count badge */}
              <span className="ml-3 text-[12px] text-[#9099ab]">
                {filtered.length} check{filtered.length !== 1 ? "s" : ""} shown
              </span>
            </div>
          </div>
        </div>

        {/* ── Check sections ── */}
        <div className="flex flex-col gap-8">
          {viewMode === "severity" ? (
            groupedSeverities.map(({ sev, checks }) => (
              <SeveritySection key={sev} severity={sev} checks={checks} selectedSnapshotId={selectedSnapshotId} />
            ))
          ) : (
            groupedResources.map(({ resource, checks }) => (
              <ResourceSection key={resource} resource={resource} checks={checks} selectedSnapshotId={selectedSnapshotId} />
            ))
          )}
        </div>

        {/* ── Footer note ── */}
        <p className="mt-8 text-center text-[11.5px] leading-relaxed text-[#9099ab]">
          Checks are heuristic-based on live cluster snapshot · for CVE scanning integrate{" "}
          <span className="text-[#4f6df5]">Trivy Operator</span> or{" "}
          <span className="text-[#4f6df5]">Snyk</span>
        </p>
      </div>
    </div>
  );
}
