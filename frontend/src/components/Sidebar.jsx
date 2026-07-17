import { AlertCircle, AlertTriangle, Info, PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { useState, useEffect } from "react";
import { cachedFetch } from "../utils/fetchCache";

const CATEGORIES = ["Cost", "Reliability", "Performance", "Storage", "Security"];

const CATEGORY_ICONS = {
  Cost: "💰",
  Reliability: "🔄",
  Performance: "⚡",
  Storage: "💾",
  Security: "🛡️",
};

const SEVERITY_CONFIG = {
  critical: {
    icon: AlertCircle,
    label: "Critical",
    badgeText: "text-[#ff6b6b]",
    cardBorder: "border-[#ff6b6b]/25",
    cardBg: "bg-[#ff6b6b]/[0.06]",
  },
  warning: {
    icon: AlertTriangle,
    label: "Warning",
    badgeText: "text-[#f5a623]",
    cardBorder: "border-[#f5a623]/25",
    cardBg: "bg-[#f5a623]/[0.06]",
  },
  info: {
    icon: Info,
    label: "Info",
    badgeText: "text-[#4f6df5]",
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

function CategoryPill({ label, active, count, onClick }) {
  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-1.5 rounded-full px-3.5 py-1.5 text-[12.5px] font-medium transition-all ${active
          ? "bg-[#4f6df5] text-white shadow-[0_0_12px_rgba(79,109,245,0.35)]"
          : "bg-[#171C2A] text-[#9099ab] border border-[#1c1f2f] hover:text-[#e7e9ee] hover:border-[#2a2f45]"
        }`}
    >
      <span>{CATEGORY_ICONS[label]}</span>
      {label}
      {count >= 0 && (
        <span
          className={`ml-0.5 rounded-full px-1.5 py-0.5 text-[10px] font-bold leading-none ${active ? "bg-white/20 text-white" : count > 0 ? "bg-[#ff6b6b]/20 text-[#ff6b6b]" : "bg-[#2a2f45] text-[#9099ab]"
            }`}
        >
          {count}
        </span>
      )}
    </button>
  );
}

function AlertCard({ severity, title, detail }) {
  const cfg = SEVERITY_CONFIG[severity] || SEVERITY_CONFIG.info;
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

function LoadingPulse() {
  return (
    <div className="flex flex-col gap-3">
      {[1, 2].map((i) => (
        <div key={i} className="h-16 animate-pulse rounded-xl bg-[#171c2a]" />
      ))}
    </div>
  );
}

export default function Sidebar({ selectedSnapshotId, activeTab, hideSystemK8s }) {
  const [snapshot, setSnapshot] = useState(null);
  const [categoryData, setCategoryData] = useState({});  // { cost: {issues,summary}, ... }
  const [loading, setLoading] = useState(true);
  const [isOpen, setIsOpen] = useState(true);
  const [activeCategory, setActiveCategory] = useState("Cost");
  const [visibleLimit, setVisibleLimit] = useState(3);

  useEffect(() => {
    if (activeTab === "Chat") {
      setIsOpen(true);
    } else if (activeTab) {
      setIsOpen(false);
    }
  }, [activeTab]);

  useEffect(() => {
    const fetchSidebarData = async () => {
      setLoading(true);
      try {
        const backendUrl = import.meta.env.VITE_API_BASE_URL || `http://${window.location.hostname}:8000`;
        const query = selectedSnapshotId ? `?snapshot_id=${selectedSnapshotId}` : '';
        const catKeys = ["cost", "reliability", "performance", "storage", "security"];
        const [snapRes, ...catResponses] = await Promise.all([
          cachedFetch(`${backendUrl}/snapshot${query}`),
          ...catKeys.map(cat => cachedFetch(`${backendUrl}/${cat}${query}`))
        ]);
        if (snapRes.ok) setSnapshot(await snapRes.json());
        const newCatData = {};
        for (let i = 0; i < catKeys.length; i++) {
          if (catResponses[i].ok) {
            newCatData[catKeys[i]] = await catResponses[i].json();
          }
        }
        setCategoryData(newCatData);
      } catch (err) {
        console.error("Failed to fetch sidebar data:", err);
      } finally {
        setLoading(false);
      }
    };
    fetchSidebarData();
    const interval = setInterval(fetchSidebarData, 60000);
    return () => clearInterval(interval);
  }, [selectedSnapshotId]);

  const snapData = snapshot?.data || {};
  
  const SYSTEM_NAMESPACES = ['kube-system', 'kube-public', 'kube-node-lease'];
  
  const filteredPods = hideSystemK8s 
    ? (snapData.pods || []).filter(p => !SYSTEM_NAMESPACES.includes(p.namespace))
    : (snapData.pods || []);
    
  const totalPods = filteredPods.length;
  const totalNodes = (snapData.nodes || []).length;

  let estimatedCost = 0;
  let wastedCost = 0;
  
  if (hideSystemK8s) {
    filteredPods.forEach(p => {
      estimatedCost += ((p.cost_per_hour || 0) * 730);
      wastedCost += (p.wasted_cost_per_month || 0);
    });
  } else {
    const costSummary = snapData.cost_summary || {};
    estimatedCost = (costSummary.total_cost_per_hour || 0) * 730;
    wastedCost = costSummary.total_wasted_per_month || 0;
  }

  // Build a flat list of all issues from per-category endpoints, tagged with category
  const allAlerts = CATEGORIES.flatMap(cat => {
    const key = cat.toLowerCase();
    const issues = categoryData[key]?.issues || [];
    return issues.map(issue => ({ ...issue, category: key }));
  }).filter(a => !hideSystemK8s || !a.namespace || !SYSTEM_NAMESPACES.includes(a.namespace));
  
  const criticalIssuesCount = allAlerts.filter(a => a.severity === "critical").length;
  const categorySummaries = Object.fromEntries(
    CATEGORIES.map(cat => [cat.toLowerCase(), categoryData[cat.toLowerCase()]?.summary || ""])
  );

  // Count issues per category for badge display
  const countByCategory = (cat) => allAlerts.filter(a => a.category === cat.toLowerCase()).length;

  // Filtered alerts for the active category
  const activeCategoryKey = activeCategory.toLowerCase();
  const filteredAlerts = allAlerts.filter(a => a.category === activeCategoryKey);
  const displayedAlerts = filteredAlerts.slice(0, visibleLimit);

  const activeSummary = categorySummaries[activeCategoryKey];

  const fmt$ = (val) =>
    new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(val);

  const CLUSTER_STATS = [
    { label: "Total Nodes", value: totalNodes.toString(), tone: "neutral" },
    { label: "Total Pods", value: totalPods.toString(), tone: "neutral" },
    { label: "Estimated Monthly Cost", value: fmt$(estimatedCost), tone: "neutral" },
    { label: "Wasted Cost", value: fmt$(wastedCost), tone: wastedCost > 0 ? "warning" : "neutral" },
    { label: "Critical Issues", value: criticalIssuesCount.toString(), tone: criticalIssuesCount > 0 ? "critical" : "neutral" },
  ];

  if (!isOpen) {
    return (
      <aside className="flex h-full w-[60px] flex-col items-center border-r border-[#1c1f2f] bg-[#121421] py-6">
        <button
          onClick={() => setIsOpen(true)}
          className="rounded-lg p-2 text-[#9099ab] hover:bg-white/5 hover:text-[#e7e9ee] transition-colors"
          title="Open Sidebar"
        >
          <PanelLeftOpen size={20} />
        </button>
      </aside>
    );
  }

  return (
    <aside className="flex h-full w-[380px] flex-col gap-6 border-r border-[#1c1f2f] bg-[#121421] px-6 py-6 overflow-y-auto transition-all">

      {/* Cluster Health Stats */}
      <div>
        <div className="flex items-center justify-between">
          <p className="m-0 text-[12px] font-semibold tracking-wide text-[#9099ab]">
            CLUSTER HEALTH
          </p>
          <button
            onClick={() => setIsOpen(false)}
            className="rounded-lg p-1.5 text-[#9099ab] hover:bg-white/5 hover:text-[#e7e9ee] transition-colors -mr-2"
            title="Close Sidebar"
          >
            <PanelLeftClose size={16} />
          </button>
        </div>
        <div className="mt-4 flex flex-col gap-3">
          {loading ? (
            <LoadingPulse />
          ) : (
            CLUSTER_STATS.map((stat) => (
              <StatCard key={stat.label} {...stat} />
            ))
          )}
        </div>
      </div>

      {/* Analysis Categories */}
      <div>
        <p className="m-0 text-[12px] font-semibold tracking-wide text-[#9099ab]">TOP ISSUES</p>
        <div className="mt-3 flex flex-wrap gap-2">
          {CATEGORIES.map((label) => (
            <CategoryPill
              key={label}
              label={label}
              active={label === activeCategory}
              count={countByCategory(label)}
              onClick={() => {
                setActiveCategory(label);
                setVisibleLimit(3);
              }}
            />
          ))}
        </div>

        {/* Category summary blurb */}
        {activeSummary && (
          <div className="mt-3 rounded-xl border border-[#1c1f2f] bg-[#171c2a] px-4 py-3">
            <p className="m-0 text-[12px] text-[#9099ab]">
              {CATEGORY_ICONS[activeCategory]}{" "}
              <span className="font-semibold text-[#e7e9ee]">{activeCategory}</span>
            </p>
            <p className="m-0 mt-1.5 text-[12.5px] leading-relaxed text-[#9099ab]">
              {activeSummary}
            </p>
          </div>
        )}
      </div>

      {/* Proactive Alerts filtered by category */}
      <div>
        <div className="flex items-center justify-between">
          <p className="m-0 text-[12px] font-semibold tracking-wide text-[#9099ab]">
            {activeCategory.toUpperCase()} ALERTS
          </p>
          {displayedAlerts.length > 0 && (
            <span className="text-[11px] text-[#9099ab]">
              {displayedAlerts.filter(a => a.severity === "critical").length} critical
            </span>
          )}
        </div>
        <div className="mt-3 flex flex-col gap-3">
          {loading ? (
            <LoadingPulse />
          ) : displayedAlerts.length === 0 ? (
            <div className="rounded-xl border border-[#1c1f2f] bg-[#171c2a] px-4 py-5 text-center">
              <p className="m-0 text-[13px] text-[#50e3c2]">
                {`✓ No ${activeCategory} issues detected`}
              </p>
            </div>
          ) : (
            displayedAlerts.map((alert, idx) => (
              <AlertCard
                key={idx}
                severity={alert.severity}
                title={alert.title}
                detail={alert.description}
              />
            ))
          )}
          {filteredAlerts.length > visibleLimit && (
            <button
              onClick={() => setVisibleLimit(prev => prev + 3)}
              className="mt-1 w-full rounded-md border border-[#1c1f2f] bg-[#1a1d29] py-2 text-[12px] font-medium text-[#9099ab] hover:bg-white/5 hover:text-[#e7e9ee] transition-colors"
            >
              Load More
            </button>
          )}
        </div>
      </div>

    </aside>
  );
}