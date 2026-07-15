import { useState } from "react";
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
} from "lucide-react";

// ---------------------------------------------------------------------------
// Mock data — mirrors what the backend security analyser would return
// ---------------------------------------------------------------------------
const SECURITY_CHECKS = [
  // ── Network ───────────────────────────────────────────────────────────────
  {
    id: "open-nodeports",
    category: "Network",
    severity: "critical",
    title: "Open NodePorts Detected",
    description:
      "Services exposed via NodePort bind directly to the host network and bypass Kubernetes network policies. External traffic can reach these ports without going through an Ingress controller.",
    remediation:
      "Switch to ClusterIP + Ingress with TLS termination. If NodePort is required, restrict access with firewall rules at the infrastructure level.",
    resources: ["service/frontend — port 32001", "service/debug-api — port 31234"],
    passed: false,
  },
  {
    id: "network-policies",
    category: "Network",
    severity: "warning",
    title: "Namespaces Missing Network Policies",
    description:
      "Namespaces without a NetworkPolicy allow unrestricted pod-to-pod traffic cluster-wide. A compromised pod can freely communicate with any other pod.",
    remediation:
      "Apply a default-deny-all NetworkPolicy to each namespace, then add explicit allow rules only for required traffic flows.",
    resources: ["namespace/default", "namespace/legacy"],
    passed: false,
  },
  {
    id: "ingress-tls",
    category: "Network",
    severity: "info",
    title: "Ingress Routes Without TLS",
    description:
      "One ingress rule is serving traffic over plain HTTP. Data in transit is unencrypted and vulnerable to interception.",
    remediation:
      "Add a tls block to your Ingress spec and provision a certificate via cert-manager or your cloud provider's managed certificate service.",
    resources: ["ingress/legacy-api-ingress — host: api.internal"],
    passed: false,
  },

  // ── Pod Security ──────────────────────────────────────────────────────────
  {
    id: "root-containers",
    category: "Pod Security",
    severity: "critical",
    title: "Containers Running as Root",
    description:
      "Containers running as UID 0 have elevated privileges inside the container. If breached, an attacker has root access to the container filesystem and may be able to escape to the host.",
    remediation:
      "Set securityContext.runAsNonRoot: true and securityContext.runAsUser: <non-zero-uid> in your pod spec. Rebuild images to use a non-root user.",
    resources: ["pod/logging-agent (ns: kube-system)", "pod/syslog-collector (ns: monitoring)"],
    passed: false,
  },
  {
    id: "privileged-containers",
    category: "Pod Security",
    severity: "critical",
    title: "Privileged Containers",
    description:
      "No privileged containers found. Privileged mode grants a container nearly all capabilities of the host kernel — this check is clean.",
    remediation: "Continue enforcing allowPrivilegeEscalation: false in pod security standards.",
    resources: [],
    passed: true,
  },
  {
    id: "resource-limits",
    category: "Pod Security",
    severity: "warning",
    title: "Pods Missing Resource Limits",
    description:
      "Pods without CPU/memory limits can consume unbounded resources, causing noisy-neighbour problems and potential node OOM kills.",
    remediation:
      "Add resources.limits.cpu and resources.limits.memory to every container. Consider enforcing this with a LimitRange in each namespace.",
    resources: [
      "pod/nginx-ingress (ns: production)",
      "pod/redis-cache (ns: production)",
      "pod/worker-3 (ns: jobs)",
    ],
    passed: false,
  },
  {
    id: "readonly-fs",
    category: "Pod Security",
    severity: "info",
    title: "Writable Root Filesystems",
    description:
      "Containers with a writable root filesystem allow attackers to modify binaries or drop persistence payloads if the container is breached.",
    remediation:
      "Set securityContext.readOnlyRootFilesystem: true and mount writable volumes only for paths that genuinely need write access (e.g. /tmp).",
    resources: ["pod/ml-training-pod (ns: ml-workloads)", "pod/batch-worker (ns: jobs)"],
    passed: false,
  },

  // ── RBAC ──────────────────────────────────────────────────────────────────
  {
    id: "service-accounts",
    category: "RBAC",
    severity: "warning",
    title: "Overpermissioned Service Accounts",
    description:
      "These service accounts have ClusterRole bindings granting cluster-wide permissions beyond what their workloads require (principle of least privilege violation).",
    remediation:
      "Audit the roles bound to each service account with kubectl auth can-i --list. Replace ClusterRoleBindings with namespace-scoped RoleBindings where possible.",
    resources: ["sa/default (ns: production)", "sa/app-service (ns: jobs)"],
    passed: false,
  },
  {
    id: "rbac-wildcard",
    category: "RBAC",
    severity: "critical",
    title: "Wildcard RBAC Permissions",
    description:
      'A ClusterRole grants verb "*" on resource "*", effectively giving any bound subject full administrative access to the cluster.',
    remediation:
      "Replace wildcard rules with explicit verb + resource combinations. Use kubectl auth reconcile to apply a least-privilege replacement.",
    resources: ["clusterrole/legacy-admin"],
    passed: false,
  },
  {
    id: "default-sa",
    category: "RBAC",
    severity: "info",
    title: "Automounted Default Service Account Token",
    description:
      "Pods that don't opt out of the default service account token mount expose a valid API token inside every container, even if the workload never calls the Kubernetes API.",
    remediation:
      "Set automountServiceAccountToken: false on pod specs or on the default ServiceAccount in each namespace.",
    resources: ["pod/nginx-ingress (ns: production)", "pod/redis-cache (ns: production)"],
    passed: false,
  },

  // ── Image Security ────────────────────────────────────────────────────────
  {
    id: "unpinned-tags",
    category: "Image Security",
    severity: "critical",
    title: "Unpinned Image Tags",
    description:
      'Images tagged :latest or other mutable tags can silently change between pulls, making deployments non-reproducible and potentially introducing malicious code.',
    remediation:
      "Pin all image references to a specific immutable digest (e.g. image@sha256:…) or a semver tag that your registry treats as immutable.",
    resources: [
      "deployment/web-app — image: nginx:latest",
      "deployment/worker — image: python:main",
    ],
    passed: false,
  },
  {
    id: "image-pull-policy",
    category: "Image Security",
    severity: "info",
    title: "Missing imagePullPolicy: Always",
    description:
      "Without imagePullPolicy: Always, Kubernetes may run a cached (potentially outdated or patched) image rather than pulling the latest secure version from the registry.",
    remediation: "Set imagePullPolicy: Always for all containers that use mutable tags.",
    resources: ["deployment/batch-worker (ns: jobs)"],
    passed: false,
  },
  {
    id: "image-scan",
    category: "Image Security",
    severity: "info",
    title: "Image Vulnerability Scanning",
    description:
      "No image vulnerability scanner (Trivy, Grype, Snyk) is detected in the CI pipeline or as an admission webhook. CVEs in base images go undetected.",
    remediation:
      "Integrate a scanner into your CI pipeline and optionally deploy an admission controller (e.g. Trivy Operator) to block images with high/critical CVEs.",
    resources: [],
    passed: false,
    note: "Integration check only — no affected resources",
  },
];

const CATEGORIES = ["All", "Network", "Pod Security", "RBAC", "Image Security"];

const CATEGORY_ICONS = {
  Network: Network,
  "Pod Security": Box,
  RBAC: Users,
  "Image Security": Tag,
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
function CheckCard({ check }) {
  const [open, setOpen] = useState(false);
  const sevKey = check.passed ? "passed" : check.severity;
  const sev = SEV[sevKey];
  const SevIcon = sev.Icon;

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
              <p className="m-0 mb-1 flex items-center gap-1.5 text-[11.5px] font-semibold uppercase tracking-wider text-[#50e3c2]">
                <CheckCircle2 size={12} />
                Remediation
              </p>
              <p className="m-0 text-[12.5px] leading-relaxed text-[#9099ab]">
                {check.remediation}
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Category section
// ---------------------------------------------------------------------------
function CategorySection({ category, checks }) {
  const Icon = CATEGORY_ICONS[category] || Lock;
  const critCount = checks.filter((c) => !c.passed && c.severity === "critical").length;
  const warnCount = checks.filter((c) => !c.passed && c.severity === "warning").length;
  const passCount = checks.filter((c) => c.passed).length;

  return (
    <div>
      {/* Section heading */}
      <div className="mb-3 flex items-center gap-2.5">
        <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-[#4f6df5]/15">
          <Icon size={14} className="text-[#4f6df5]" />
        </div>
        <p className="m-0 text-[13.5px] font-bold text-[#e7e9ee]">{category}</p>
        <div className="flex items-center gap-1.5 ml-1">
          {critCount > 0 && (
            <span className="rounded-full bg-[#ff6b6b]/15 px-2 py-0.5 text-[11px] font-bold text-[#ff6b6b]">
              {critCount} critical
            </span>
          )}
          {warnCount > 0 && (
            <span className="rounded-full bg-[#f5a623]/15 px-2 py-0.5 text-[11px] font-bold text-[#f5a623]">
              {warnCount} warning
            </span>
          )}
          {passCount > 0 && (
            <span className="rounded-full bg-[#50e3c2]/15 px-2 py-0.5 text-[11px] font-bold text-[#50e3c2]">
              {passCount} passed
            </span>
          )}
        </div>
      </div>

      <div className="flex flex-col gap-3">
        {/* Critical first */}
        {["critical", "warning", "info"].map((sev) =>
          checks
            .filter((c) => !c.passed && c.severity === sev)
            .map((c) => <CheckCard key={c.id} check={c} />)
        )}
        {/* Passed at bottom */}
        {checks.filter((c) => c.passed).map((c) => (
          <CheckCard key={c.id} check={c} />
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------
export default function Security() {
  const [activeCategory, setActiveCategory] = useState("All");

  // Derive filtered checks
  const filtered =
    activeCategory === "All"
      ? SECURITY_CHECKS
      : SECURITY_CHECKS.filter((c) => c.category === activeCategory);

  // Stats
  const totalChecks = SECURITY_CHECKS.length;
  const passedChecks = SECURITY_CHECKS.filter((c) => c.passed).length;
  const criticalChecks = SECURITY_CHECKS.filter((c) => !c.passed && c.severity === "critical").length;
  const warningChecks = SECURITY_CHECKS.filter((c) => !c.passed && c.severity === "warning").length;
  // Score: start at 100, -15 per critical, -7 per warning, -3 per info
  const infoChecks = SECURITY_CHECKS.filter((c) => !c.passed && c.severity === "info").length;
  const score = Math.max(
    0,
    Math.round(100 - criticalChecks * 15 - warningChecks * 7 - infoChecks * 3)
  );

  // Group filtered checks by category (preserve category order)
  const categoryOrder = ["Network", "Pod Security", "RBAC", "Image Security"];
  const groupedCategories =
    activeCategory === "All"
      ? categoryOrder
          .map((cat) => ({
            cat,
            checks: filtered.filter((c) => c.category === cat),
          }))
          .filter((g) => g.checks.length > 0)
      : [{ cat: activeCategory, checks: filtered }];

  return (
    <div className="flex h-full min-h-0 flex-1 flex-col overflow-y-auto bg-[#0d0f18]">
      <div className="mx-auto w-full max-w-5xl px-8 py-8">

        {/* ── Page title ── */}
        <div className="mb-7">
          <h1 className="m-0 text-[22px] font-bold text-[#e7e9ee]">Security</h1>
          <p className="m-0 mt-1 text-[13.5px] text-[#9099ab]">
            {totalChecks} checks across {categoryOrder.length} categories · live cluster snapshot
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

          {/* Category summary grid */}
          <div className="grid flex-1 grid-cols-2 gap-3">
            {categoryOrder.map((cat) => {
              const catChecks = SECURITY_CHECKS.filter((c) => c.category === cat);
              const crit = catChecks.filter((c) => !c.passed && c.severity === "critical").length;
              const warn = catChecks.filter((c) => !c.passed && c.severity === "warning").length;
              const pass = catChecks.filter((c) => c.passed).length;
              const Icon = CATEGORY_ICONS[cat] || Lock;
              const worst = crit > 0 ? "critical" : warn > 0 ? "warning" : "passed";
              const sevCfg = SEV[worst];
              return (
                <button
                  key={cat}
                  onClick={() => setActiveCategory(cat === activeCategory ? "All" : cat)}
                  className="flex items-start gap-3 rounded-2xl border px-4 py-3.5 text-left transition hover:brightness-110"
                  style={{
                    background: sevCfg.bg,
                    borderColor: activeCategory === cat ? sevCfg.color + "55" : sevCfg.border,
                    boxShadow: activeCategory === cat ? `0 0 0 1px ${sevCfg.color}33` : "none",
                  }}
                >
                  <div
                    className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg"
                    style={{ background: sevCfg.color + "22", color: sevCfg.color }}
                  >
                    <Icon size={14} />
                  </div>
                  <div>
                    <p className="m-0 text-[13px] font-semibold text-[#e7e9ee]">{cat}</p>
                    <div className="mt-1 flex flex-wrap gap-1.5">
                      {crit > 0 && (
                        <span className="text-[11px] font-bold text-[#ff6b6b]">{crit} critical</span>
                      )}
                      {warn > 0 && (
                        <span className="text-[11px] font-bold text-[#f5a623]">{warn} warning</span>
                      )}
                      {pass > 0 && (
                        <span className="text-[11px] font-bold text-[#50e3c2]">{pass} passed</span>
                      )}
                    </div>
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        {/* ── Category filter tabs ── */}
        <div className="mb-6 flex flex-wrap items-center gap-2">
          {CATEGORIES.map((cat) => {
            const active = cat === activeCategory;
            return (
              <button
                key={cat}
                onClick={() => setActiveCategory(cat)}
                className="rounded-full border px-3.5 py-1.5 text-[12.5px] font-medium transition-all"
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
                {cat}
              </button>
            );
          })}

          {/* Count badge */}
          <span className="ml-auto text-[12px] text-[#9099ab]">
            {filtered.length} check{filtered.length !== 1 ? "s" : ""} shown
          </span>
        </div>

        {/* ── Check sections ── */}
        <div className="flex flex-col gap-8">
          {groupedCategories.map(({ cat, checks }) => (
            <CategorySection key={cat} category={cat} checks={checks} />
          ))}
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
