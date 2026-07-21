import { useState, useEffect, useRef, useCallback } from "react";
import {
  Search,
  Server,
  Box,
  LayoutGrid,
  Database,
  Layers,
  Clock,
  Shield,
  HardDrive,
  Globe,
  Settings,
  AlertCircle,
  Activity,
  RefreshCw,
} from "lucide-react";

const RESOURCE_TYPES = [
  { id: "pods", label: "Pods", icon: Box },
  { id: "deployments", label: "Deployments", icon: LayoutGrid },
  { id: "replicasets", label: "ReplicaSets", icon: Layers },
  { id: "services", label: "Services", icon: Globe },
  { id: "nodes", label: "Nodes", icon: Server },
  { id: "pvcs", label: "PVCs", icon: HardDrive },
  { id: "statefulsets", label: "StatefulSets", icon: Database },
  { id: "daemonsets", label: "DaemonSets", icon: Settings },
  { id: "jobs", label: "Jobs", icon: Clock },
  { id: "cronjobs", label: "CronJobs", icon: Clock },
  { id: "ingresses", label: "Ingresses", icon: Globe },
  { id: "networkpolicies", label: "NetworkPolicies", icon: Shield },
  { id: "configmaps", label: "ConfigMaps", icon: Settings },
  { id: "secrets", label: "Secrets", icon: Shield },
  { id: "hpas", label: "HPAs", icon: Activity },
];

const SYSTEM_NAMESPACES = ["kube-system", "kube-public", "kube-node-lease"];
const LIVE_REFRESH_INTERVAL = 10000;

function formatRelativeTime(date) {
  if (!date) return "Never";
  const diff = Math.floor((Date.now() - date.getTime()) / 1000);
  if (diff < 5) return "Just now";
  if (diff < 60) return `${diff}s ago`;
  return `${Math.floor(diff / 60)}m ago`;
}

function UsageBar({ label, actual, capacity, unit }) {
  if (!capacity || capacity === 0) return null;
  const pct = Math.min((actual / capacity) * 100, 100);
  const color = pct > 80 ? "#ef4444" : pct > 50 ? "#f59e0b" : "#22c55e";
  const actualStr = unit === "cpu"
    ? `${(actual * 1000).toFixed(0)}m`
    : `${(actual * 1024).toFixed(0)}Mi`;
  const capStr = unit === "cpu"
    ? `${(capacity * 1000).toFixed(0)}m`
    : `${(capacity * 1024).toFixed(0)}Mi`;
  return (
    <div className="flex flex-col gap-1">
      <div className="flex justify-between text-[11px]">
        <span className="font-medium uppercase tracking-wider text-[#9099ab]">{label}</span>
        <span className="font-mono text-[#e7e9ee]">{actualStr} / {capStr}</span>
      </div>
      <div className="h-1.5 w-full rounded-full bg-[#2a2e40] overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${pct}%`, backgroundColor: color }}
        />
      </div>
    </div>
  );
}

export default function ClusterResources({ selectedSnapshotId, hideSystemK8s }) {
  const [snapshotData, setSnapshotData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState("pods");
  const [searchQuery, setSearchQuery] = useState("");
  const [lastUpdated, setLastUpdated] = useState(null);
  const [relativeTime, setRelativeTime] = useState("Never");
  const [countdown, setCountdown] = useState(LIVE_REFRESH_INTERVAL / 1000);
  const intervalRef = useRef(null);
  const countdownRef = useRef(null);

  const isLive = !selectedSnapshotId;

  const fetchData = useCallback(async (isBackground = false) => {
    if (isBackground) setRefreshing(true);
    else setLoading(true);
    setError(null);
    try {
      const backendUrl = import.meta.env.VITE_API_BASE_URL || `http://${window.location.hostname}:8000`;
      const url = selectedSnapshotId
        ? `${backendUrl}/snapshot?snapshot_id=${selectedSnapshotId}`
        : `${backendUrl}/snapshot`;
      const res = await fetch(url, { cache: "no-store" });
      if (!res.ok) throw new Error("Failed to fetch snapshot data");
      const data = await res.json();
      setSnapshotData(data.data || {});
      setLastUpdated(new Date());
      setCountdown(LIVE_REFRESH_INTERVAL / 1000);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [selectedSnapshotId]);

  useEffect(() => {
    fetchData(false);
    if (isLive) {
      intervalRef.current = setInterval(() => fetchData(true), LIVE_REFRESH_INTERVAL);
      countdownRef.current = setInterval(() => {
        setCountdown(prev => (prev <= 1 ? LIVE_REFRESH_INTERVAL / 1000 : prev - 1));
      }, 1000);
    }
    return () => {
      clearInterval(intervalRef.current);
      clearInterval(countdownRef.current);
    };
  }, [fetchData, isLive]);

  useEffect(() => {
    const tick = setInterval(() => setRelativeTime(formatRelativeTime(lastUpdated)), 1000);
    return () => clearInterval(tick);
  }, [lastUpdated]);

  // Auto-jump to the first tab that has matches if the current tab has none
  useEffect(() => {
    if (!snapshotData || !searchQuery) return;
    const q = searchQuery.toLowerCase();

    const getMatchCount = (tabId) => {
      let items = snapshotData[tabId] || [];
      if (hideSystemK8s) {
        items = items.filter(item => !item.namespace || !SYSTEM_NAMESPACES.includes(item.namespace));
      }
      return items.filter(item => JSON.stringify(item).toLowerCase().includes(q)).length;
    };

    if (getMatchCount(activeTab) === 0) {
      for (const type of RESOURCE_TYPES) {
        if (type.id !== activeTab && getMatchCount(type.id) > 0) {
          setActiveTab(type.id);
          break;
        }
      }
    }
  }, [searchQuery, snapshotData, hideSystemK8s, activeTab]);

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center bg-[#0d0f18] text-[#9099ab]">
        <div className="flex flex-col items-center gap-3">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-[#4f6df5] border-t-transparent"></div>
          <p>Loading cluster resources...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex h-full items-center justify-center bg-[#0d0f18]">
        <div className="flex flex-col items-center gap-3 rounded-xl border border-[#ff6b6b]/20 bg-[#ff6b6b]/10 p-6 text-[#ff6b6b]">
          <AlertCircle size={32} />
          <p className="font-semibold">Error Loading Resources</p>
          <p className="text-sm opacity-80">{error}</p>
        </div>
      </div>
    );
  }

  const rawItems = snapshotData?.[activeTab] || [];
  let filteredItems = rawItems;
  if (hideSystemK8s) {
    filteredItems = filteredItems.filter(item => {
      if (item.namespace) return !SYSTEM_NAMESPACES.includes(item.namespace);
      return true;
    });
  }
  if (searchQuery) {
    const q = searchQuery.toLowerCase();
    filteredItems = filteredItems.filter(item =>
      JSON.stringify(item).toLowerCase().includes(q)
    );
  }

  const renderCardContent = (item) => {
    const isPod = activeTab === "pods";
    const isNode = activeTab === "nodes";

    if (isPod) {
      return (
        <div className="col-span-2 flex flex-col gap-3">
          <UsageBar label="CPU Usage" actual={item.cpu_actual} capacity={item.cpu_requested} unit="cpu" />
          <UsageBar label="Memory Usage" actual={item.mem_actual_gb} capacity={item.mem_requested_gb} unit="mem" />
          <div className="grid grid-cols-2 gap-3 pt-1 border-t border-[#1c1f2f]">
            {Object.entries(item)
              .filter(([k]) => !["name","namespace","status","cpu_requested","mem_requested_gb","cpu_actual","mem_actual_gb"].includes(k))
              .map(([key, value]) => {
                let d = value;
                if (typeof d === "boolean") d = d ? "Yes" : "No";
                else if (Array.isArray(d)) d = d.length > 0 ? d.join(", ") : "None";
                else if (typeof d === "object" && d !== null) d = JSON.stringify(d);
                else if (d === null || d === undefined) d = "N/A";
                return (
                  <div key={key} className="flex flex-col gap-1">
                    <span className="text-[11px] font-medium uppercase tracking-wider text-[#9099ab]">{key.replace(/_/g, " ")}</span>
                    <span className="truncate text-[13px] text-[#e7e9ee] font-mono">{String(d)}</span>
                  </div>
                );
              })}
          </div>
        </div>
      );
    }

    if (isNode) {
      return (
        <div className="col-span-2 flex flex-col gap-3">
          <UsageBar label="CPU Usage" actual={item.cpu_usage} capacity={item.cpu_capacity} unit="cpu" />
          <UsageBar label="Memory Usage" actual={item.mem_usage_gb} capacity={item.mem_capacity_gb} unit="mem" />
          <div className="grid grid-cols-2 gap-3 pt-1 border-t border-[#1c1f2f]">
            {Object.entries(item)
              .filter(([k]) => !["name","namespace","status","cpu_capacity","mem_capacity_gb","cpu_usage","mem_usage_gb"].includes(k))
              .map(([key, value]) => (
                <div key={key} className="flex flex-col gap-1">
                  <span className="text-[11px] font-medium uppercase tracking-wider text-[#9099ab]">{key.replace(/_/g, " ")}</span>
                  <span className="truncate text-[13px] text-[#e7e9ee] font-mono">{String(value ?? "N/A")}</span>
                </div>
              ))}
          </div>
        </div>
      );
    }

    return Object.entries(item)
      .filter(([key]) => !["name", "namespace", "status"].includes(key))
      .map(([key, value]) => {
        let d = value;
        if (typeof d === "boolean") d = d ? "Yes" : "No";
        else if (Array.isArray(d)) d = d.length > 0 ? d.join(", ") : "None";
        else if (typeof d === "object" && d !== null) d = JSON.stringify(d);
        else if (d === null || d === undefined) d = "N/A";
        return (
          <div key={key} className="flex flex-col gap-1">
            <span className="text-[11px] font-medium uppercase tracking-wider text-[#9099ab]">{key.replace(/_/g, " ")}</span>
            <span className="truncate text-[13px] text-[#e7e9ee] font-mono">{String(d)}</span>
          </div>
        );
      });
  };

  return (
    <div className="flex h-full flex-col bg-[#0d0f18] min-h-0">
      <div className="border-b border-[#1c1f2f] bg-[#121421] p-6 shrink-0">
        <div className="flex flex-col gap-6">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-xl font-bold text-white flex items-center gap-2">
                <Layers className="text-[#4f6df5]" />
                Cluster Resources
              </h1>
              <p className="mt-1 text-sm text-[#9099ab]">
                Explore all workloads, configuration, and infrastructure in your cluster.
              </p>
            </div>

            <div className="flex items-center gap-4">
              {isLive && (
                <div className="flex items-center gap-3 rounded-lg border border-[#1c1f2f] bg-[#0e111a] px-4 py-2">
                  <div className="flex items-center gap-2">
                    <span className="relative flex h-2 w-2">
                      <span className={`absolute inline-flex h-full w-full rounded-full opacity-75 animate-ping ${refreshing ? "bg-[#4f6df5]" : "bg-emerald-400"}`}></span>
                      <span className={`relative inline-flex h-2 w-2 rounded-full ${refreshing ? "bg-[#4f6df5]" : "bg-emerald-400"}`}></span>
                    </span>
                    <span className={`text-xs font-semibold ${refreshing ? "text-[#4f6df5]" : "text-emerald-400"}`}>
                      {refreshing ? "Refreshing..." : "Live"}
                    </span>
                  </div>
                  <div className="h-3 w-px bg-[#2a2e40]" />
                  <div className="flex items-center gap-1.5 text-[#9099ab]">
                    <Clock size={12} />
                    <span className="text-xs">{relativeTime}</span>
                  </div>
                  <div className="h-3 w-px bg-[#2a2e40]" />
                  <div className={`flex items-center gap-1.5 ${countdown <= 3 ? "text-[#4f6df5]" : "text-[#9099ab]"}`}>
                    <RefreshCw size={12} />
                    <span className="text-xs font-mono">{countdown}s</span>
                  </div>
                  <button
                    onClick={() => fetchData(true)}
                    className="ml-1 rounded p-1 text-[#9099ab] hover:bg-[#1c1f2f] hover:text-white transition-colors"
                    title="Refresh now"
                  >
                    <RefreshCw size={13} className={refreshing ? "animate-spin" : ""} />
                  </button>
                </div>
              )}

              <div className="relative w-72">
                <div className="absolute inset-y-0 left-0 flex items-center pl-3 pointer-events-none">
                  <Search size={16} className="text-[#5a6072]" />
                </div>
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Search resources..."
                  className="w-full rounded-lg border border-[#2a2e40] bg-[#0e111a] py-2 pl-9 pr-4 text-sm text-white placeholder-[#5a6072] outline-none transition focus:border-[#4f6df5] focus:ring-1 focus:ring-[#4f6df5]"
                />
              </div>
            </div>
          </div>

          <div className="flex gap-2 overflow-x-auto pb-2 custom-scrollbar shrink-0">
            {RESOURCE_TYPES.map(type => {
              const active = activeTab === type.id;
              let typeItems = snapshotData?.[type.id] || [];
              if (hideSystemK8s) {
                typeItems = typeItems.filter(item => {
                  if (item.namespace) return !SYSTEM_NAMESPACES.includes(item.namespace);
                  return true;
                });
              }
              if (searchQuery) {
                const q = searchQuery.toLowerCase();
                typeItems = typeItems.filter(item => JSON.stringify(item).toLowerCase().includes(q));
              }
              const count = typeItems.length;
              const Icon = type.icon;
              return (
                <button
                  key={type.id}
                  onClick={() => setActiveTab(type.id)}
                  className={`flex shrink-0 items-center gap-2 rounded-lg border px-4 py-2 transition-all ${
                    active
                      ? "border-[#4f6df5]/50 bg-[#4f6df5]/10 text-white"
                      : "border-[#1c1f2f] bg-[#171c2a] text-[#9099ab] hover:border-[#2a2e40] hover:bg-[#1a1f2e] hover:text-[#e7e9ee]"
                  }`}
                >
                  <Icon size={16} className={active ? "text-[#4f6df5]" : ""} />
                  <span className="text-sm font-semibold">{type.label}</span>
                  <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                    active ? "bg-[#4f6df5] text-white" : "bg-[#2a2e40] text-[#9099ab]"
                  }`}>
                    {count}
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      </div>

      <div className={`flex-1 overflow-y-auto p-6 min-h-0 transition-opacity duration-300 ${refreshing ? "opacity-75" : "opacity-100"}`}>
        {filteredItems.length === 0 ? (
          <div className="flex h-64 flex-col items-center justify-center text-center">
            <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-[#171c2a] text-[#4f6df5]">
              {(() => {
                const ActiveIcon = RESOURCE_TYPES.find(t => t.id === activeTab)?.icon || Box;
                return <ActiveIcon size={32} />;
              })()}
            </div>
            <h3 className="text-lg font-semibold text-white">No {activeTab} found</h3>
            <p className="mt-2 max-w-sm text-sm text-[#9099ab]">
              {searchQuery
                ? `No results matching "${searchQuery}" in ${activeTab}.`
                : `There are currently no ${activeTab} in the selected snapshot or they are filtered out.`}
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3 pb-8">
            {filteredItems.map((item, index) => (
              <div
                key={`${item.namespace || "cluster"}-${item.name}-${index}`}
                className="group flex flex-col rounded-xl border border-[#1c1f2f] bg-[#171c2a] overflow-hidden transition-all hover:border-[#2a2e40] hover:shadow-lg hover:shadow-black/20"
              >
                <div className="border-b border-[#1c1f2f] bg-[#1a1f2e] p-4 group-hover:bg-[#1e2436] transition-colors">
                  <div className="flex items-start justify-between gap-4">
                    <div className="min-w-0 flex-1">
                      <h3 className="truncate text-base font-bold text-white" title={item.name}>{item.name}</h3>
                      {item.namespace && (
                        <div className="mt-1 flex items-center gap-1.5">
                          <span className="rounded bg-[#2a2e40] px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-[#9099ab]">NS</span>
                          <span className="truncate text-[12px] text-[#9099ab]" title={item.namespace}>{item.namespace}</span>
                        </div>
                      )}
                    </div>
                    {item.status && (
                      <span className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-semibold ${
                        item.status.toLowerCase() === "running" || item.status.toLowerCase() === "bound" || item.status.toLowerCase() === "active"
                          ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                          : item.status.toLowerCase() === "failed" || item.status.toLowerCase() === "error"
                          ? "bg-red-500/10 text-red-400 border border-red-500/20"
                          : item.status.toLowerCase() === "pending"
                          ? "bg-amber-500/10 text-amber-400 border border-amber-500/20"
                          : "bg-[#2a2e40] text-[#9099ab] border border-[#3a3f55]"
                      }`}>
                        {item.status}
                      </span>
                    )}
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-4 p-4">
                  {renderCardContent(item)}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <style dangerouslySetInnerHTML={{__html: `
        .custom-scrollbar::-webkit-scrollbar { height: 6px; width: 6px; }
        .custom-scrollbar::-webkit-scrollbar-track { background: transparent; }
        .custom-scrollbar::-webkit-scrollbar-thumb { background-color: #2a2e40; border-radius: 20px; }
        .custom-scrollbar:hover::-webkit-scrollbar-thumb { background-color: #3a3f55; }
      `}} />
    </div>
  );
}
