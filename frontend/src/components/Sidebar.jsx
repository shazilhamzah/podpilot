import { AlertCircle, AlertTriangle, Info } from "lucide-react";

// Hardcoded for now — wire up to real cluster snapshot state later.
const CLUSTER_STATS = [
  { label: "Total Pods", value: "12", tone: "neutral" },
  { label: "Estimated Monthly Cost", value: "$142.50", tone: "neutral" },
  { label: "Wasted Cost", value: "$38.20", tone: "warning" },
  { label: "Critical Issues", value: "2", tone: "critical" },
];

const CATEGORIES = ["Cost", "Reliability", "Performance", "Storage", "Security"];
const ACTIVE_CATEGORY = "Cost";

const ALERTS = [
  {
    severity: "critical",
    title: "Open NodePort Detected",
    detail: "service/frontend exposed on port 32001",
  },
  {
    severity: "warning",
    title: "3 Pods Missing Resource Limits",
    detail: "nginx, redis, worker have no CPU/memory limits set",
  },
  {
    severity: "info",
    title: "Idle Replica Detected",
    detail: "deployment/batch-worker has 0/4 replicas ready",
  },
];

const SEVERITY_CONFIG = {
  critical: {
    icon: AlertCircle,
    label: "Critical",
    badgeText: "text-[#ff6b6b]",
    badgeBg: "bg-[#ff6b6b]/10",
    cardBorder: "border-[#ff6b6b]/25",
    cardBg: "bg-[#ff6b6b]/[0.06]",
  },
  warning: {
    icon: AlertTriangle,
    label: "Warning",
    badgeText: "text-[#f5a623]",
    badgeBg: "bg-[#f5a623]/10",
    cardBorder: "border-[#f5a623]/25",
    cardBg: "bg-[#f5a623]/[0.06]",
  },
  info: {
    icon: Info,
    label: "Info",
    badgeText: "text-[#4f6df5]",
    badgeBg: "bg-[#4f6df5]/10",
    cardBorder: "border-[#4f6df5]/25",
    cardBg: "bg-[#4f6df5]/[0.06]",
  },
};

const STAT_CARD_STYLES = {
  neutral: "bg-[#171c2a] border-[#2d2e40]",
  warning: "bg-[#2a2113] border-[#f5a623]/25",
  critical: "bg-[#2a1518] border-[#ff6b6b]/25",
};

const STAT_VALUE_STYLES = {
  neutral: "text-[#e7e9ee]",
  warning: "text-[#f5a623]",
  critical: "text-[#ff6b6b]",
};

function StatCard({ label, value, tone }) {
  return (
    <div className={`rounded-xl border px-4 py-3.5 ${STAT_CARD_STYLES[tone]}`}>
      <p className="m-0 text-[12px] text-[#9099ab]">{label}</p>
      <p className={`m-0 mt-1 text-[22px] font-semibold leading-none ${STAT_VALUE_STYLES[tone]}`}>
        {value}
      </p>
    </div>
  );
}

function CategoryPill({ label, active }) {
  return (
    <button
      className={`rounded-full px-3.5 py-1.5 text-[12.5px] font-medium transition-colors ${
        active
          ? "bg-[#4f6df5] text-white"
          : "bg-[#171C2A] text-[#9099ab] border border-[#1c1f2f] hover:text-[#e7e9ee] hover:border-[#2a2f45]"
      }`}
    >
      {label}
    </button>
  );
}

function AlertCard({ severity, title, detail }) {
  const cfg = SEVERITY_CONFIG[severity];
  const Icon = cfg.icon;
  return (
    <div className={`rounded-xl border px-4 py-3.5 ${cfg.cardBorder} ${cfg.cardBg}`}>
      <div className="flex items-center gap-1.5">
        <Icon size={13} className={cfg.badgeText} />
        <span className={`text-[11.5px] font-semibold ${cfg.badgeText}`}>{cfg.label}</span>
      </div>
      <p className="m-0 mt-2 text-[13.5px] font-semibold text-[#e7e9ee]">{title}</p>
      <p className="m-0 mt-1 text-[12.5px] leading-snug text-[#9099ab]">{detail}</p>
    </div>
  );
}

export default function Sidebar() {
  return (
    <aside className="flex h-full w-[380px] flex-col gap-6 border-r border-[#1c1f2f] bg-[#121421] px-6 py-6 overflow-y-auto">
      <div>
        <p className="m-0 text-[12px] font-semibold tracking-wide text-[#9099ab]">
          CLUSTER HEALTH
        </p>
        <div className="mt-4 flex flex-col gap-3">
          {CLUSTER_STATS.map((stat) => (
            <StatCard key={stat.label} {...stat} />
          ))}
        </div>
      </div>

      <div>
        <p className="m-0 text-[14px] font-semibold text-[#e7e9ee]">Analysis Categories</p>
        <div className="mt-3 flex flex-wrap gap-2">
          {CATEGORIES.map((label) => (
            <CategoryPill key={label} label={label} active={label === ACTIVE_CATEGORY} />
          ))}
        </div>
      </div>

      <div>
        <p className="m-0 text-[14px] font-semibold text-[#e7e9ee]">Proactive Alerts</p>
        <div className="mt-3 flex flex-col gap-3">
          {ALERTS.map((alert) => (
            <AlertCard key={alert.title} {...alert} />
          ))}
        </div>
      </div>
    </aside>
  );
}