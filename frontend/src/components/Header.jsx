import { useState, useRef, useLayoutEffect, useEffect } from "react";
import { ChevronDown, MessageSquare, Wallet, GitCompareArrows, ShieldCheck, Plus, X, Loader2 } from "lucide-react";
import PodPilotLogo from "./PodPilotLogo";
import { cachedFetch } from "../utils/fetchCache";

const NAV_ITEMS = [
  { label: "Chat", icon: MessageSquare },
  { label: "Cost Breakdown", icon: Wallet },
  { label: "Drift Detection", icon: GitCompareArrows },
  { label: "Security", icon: ShieldCheck },
];

export default function Header({ activeTab, onTabChange, snapshots, selectedSnapshotId, setSelectedSnapshotId, onSnapshotCreated }) {
  const tabRefs = useRef({});
  const [indicator, setIndicator] = useState({ left: 0, width: 0, ready: false });
  const [snapshotAge, setSnapshotAge] = useState("Loading...");
  const [isRefreshing, setIsRefreshing] = useState(false);
  
  // Modal state
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [snapshotName, setSnapshotName] = useState("");
  const [snapshotComments, setSnapshotComments] = useState("");

  // Measure the active tab's position/width whenever it changes (or on mount/resize)
  // so the sliding indicator can be positioned with real pixel values.
  useLayoutEffect(() => {
    const measure = () => {
      const el = tabRefs.current[activeTab];
      if (el) {
        setIndicator({ left: el.offsetLeft, width: el.offsetWidth, ready: true });
      }
    };
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, [activeTab]);

  useEffect(() => {
    const fetchSnapshotStatus = async () => {
      setSnapshotAge("Loading...");
      try {
        const backendUrl = import.meta.env.VITE_API_BASE_URL || `http://${window.location.hostname}:8000`;
        const url = selectedSnapshotId ? `${backendUrl}/snapshot?snapshot_id=${selectedSnapshotId}` : `${backendUrl}/snapshot`;
        const res = await cachedFetch(url);
        const data = await res.json();
        if (data.cached_at) {
          const cachedDate = new Date(data.cached_at);
          const diffMins = Math.round((new Date() - cachedDate) / 60000);
          if (diffMins <= 0) {
            setSnapshotAge("Just now");
          } else if (diffMins < 60) {
            setSnapshotAge(`${diffMins} mins ago`);
          } else if (diffMins < 1440) {
            const hrs = Math.round(diffMins / 60);
            setSnapshotAge(`${hrs} ${hrs === 1 ? 'hr' : 'hrs'} ago`);
          } else {
            const days = Math.round(diffMins / 1440);
            setSnapshotAge(`${days} ${days === 1 ? 'day' : 'days'} ago`);
          }
        } else {
          setSnapshotAge("Never");
        }
      } catch (err) {
        setSnapshotAge("Unknown");
      }
    };
    fetchSnapshotStatus();
    const interval = setInterval(fetchSnapshotStatus, 60000);
    return () => clearInterval(interval);
  }, [selectedSnapshotId]);

  const handleCreateSnapshot = async (e) => {
    e.preventDefault();
    setIsRefreshing(true);
    setSnapshotAge("Creating...");
    setIsModalOpen(false);
    setSelectedSnapshotId(""); // Clear the selection to show the new loading UI
    
    try {
      const backendUrl = import.meta.env.VITE_API_BASE_URL || `http://${window.location.hostname}:8000`;
      await fetch(`${backendUrl}/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: snapshotName.trim() || null,
          comments: snapshotComments.trim() || null
        })
      });
      setSnapshotAge("Just now");
      setSnapshotName("");
      setSnapshotComments("");
      if (onSnapshotCreated) {
        onSnapshotCreated();
      }
      setTimeout(() => {
        window.location.reload();
      }, 3000);
    } catch (err) {
      setSnapshotAge("Error");
    } finally {
      setIsRefreshing(false);
    }
  };

  return (
    <>
      <header className="relative flex items-center gap-7 overflow-hidden border-b border-[#1c1f2f] bg-[#171c2a] px-7 py-3.5">
        <div
          className="pointer-events-none absolute -left-24 -top-40 h-64 w-96 rotate-[-20deg] bg-[#171C2A] via-[#4f6df5]/40 to-transparent opacity-70 blur-2xl"
          aria-hidden="true"
        />

        {/* Brand */}
        <div className="relative z-10 flex items-center gap-2">
          <PodPilotLogo size={30} />
          <span className="font-semibold tracking-tight text-[15.5px] text-[#e7e9ee]">
            Pod Pilot
          </span>
        </div>

        {/* Nav tabs */}
        <nav className="relative z-10 ml-2 hidden items-center gap-1 md:flex">
          {NAV_ITEMS.map(({ label, icon: Icon }) => {
            const active = label === activeTab;
            return (
              <a
                key={label}
                ref={(el) => {
                  tabRefs.current[label] = el;
                }}
                href="#"
                onClick={(e) => {
                  e.preventDefault();
                  onTabChange(label);
                }}
                className={`relative flex items-center gap-1.5 rounded-lg px-3 py-2 text-[13.5px] font-medium transition-colors duration-200 ${
                  active
                    ? "text-[#4f6df5]"
                    : "text-[#9099ab] hover:bg-white/5 hover:text-[#e7e9ee]"
                }`}
              >
                <Icon size={15} />
                {label}
              </a>
            );
          })}

          {/* Single sliding indicator, positioned via measured left/width and animated with transform */}
          <span
            className={`pointer-events-none absolute -bottom-[13px] h-0.5 rounded-full bg-[#4f6df5] transition-[transform,width] duration-300 ease-out ${
              indicator.ready ? "opacity-100" : "opacity-0"
            }`}
            style={{
              width: Math.max(indicator.width - 24, 0),
              transform: `translateX(${indicator.left + 12}px)`,
            }}
          />
        </nav>

        {/* Right side: last snapshot readout + refresh action */}
        <div className="relative z-10 ml-auto flex items-center gap-4">
          <div className="flex items-center gap-2 mr-3">
            <span className="text-[11.5px] font-semibold tracking-wider text-[#9099ab] uppercase">Context:</span>
            <div className="relative">
              <select
                value={selectedSnapshotId}
                onChange={(e) => setSelectedSnapshotId(e.target.value)}
                className="appearance-none cursor-pointer rounded-lg border border-[#1c1f2f] bg-[#0d0f18] pl-3 pr-8 py-1.5 text-[13px] font-medium text-[#e7e9ee] shadow-sm outline-none transition-all hover:border-[#2a2f45] hover:bg-[#121421] focus:border-[#4f6df5] focus:ring-1 focus:ring-[#4f6df5]/50"
              >
                {!selectedSnapshotId && (
                  <option value="" disabled>Loading snapshots...</option>
                )}
                {snapshots && snapshots.map((s, idx) => (
                  <option key={s.id} value={s.id}>
                    {s.name || `Snapshot at ${new Date(s.captured_at).toLocaleString()}`}
                    {idx === 0 ? " (Latest)" : ""}
                    {s.comments ? ` (${s.comments})` : ""}
                  </option>
                ))}
              </select>
              <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center pr-2.5 text-[#9099ab]">
                <ChevronDown size={14} />
              </div>
            </div>
          </div>
          <div className="text-right leading-tight">
            <p className="m-0 text-[12px] text-[#9099ab]">Snapshot taken</p>
            <p className="m-0 text-[14px] font-semibold text-[#e7e9ee]">{snapshotAge}</p>
          </div>
          <button
            onClick={() => setIsModalOpen(true)}
            disabled={isRefreshing}
            className={`flex items-center gap-1.5 h-8 px-3.5 rounded-full bg-gradient-to-r from-[#6f7bff] to-[#3546c4] text-white shadow-[0_2px_8px_rgba(79,109,245,0.25)] transition-all hover:shadow-[0_4px_12px_rgba(79,109,245,0.4)] hover:brightness-110 ${
              isRefreshing ? "opacity-50 cursor-not-allowed" : "active:scale-95"
            }`}
          >
            {isRefreshing ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <Plus size={14} />
            )}
            <span className="text-[12.5px] font-semibold tracking-wide">Create Snapshot</span>
          </button>
        </div>
      </header>

      {/* Create Snapshot Modal */}
      {isModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-xl border border-[#2a2e40] bg-[#171c2a] shadow-2xl">
            <div className="flex items-center justify-between border-b border-[#2a2e40] px-6 py-4">
              <h2 className="text-lg font-semibold text-white">Create Snapshot</h2>
              <button
                onClick={() => setIsModalOpen(false)}
                className="rounded-lg p-1.5 text-[#9099ab] hover:bg-white/10 hover:text-white transition"
              >
                <X size={20} />
              </button>
            </div>
            
            <form onSubmit={handleCreateSnapshot} className="p-6">
              <div className="space-y-4">
                <div>
                  <label htmlFor="snapshotName" className="mb-1.5 block text-sm font-medium text-[#9099ab]">
                    Snapshot Name <span className="text-xs font-normal opacity-70">(Optional)</span>
                  </label>
                  <input
                    id="snapshotName"
                    type="text"
                    value={snapshotName}
                    onChange={(e) => setSnapshotName(e.target.value)}
                    placeholder="e.g. Pre-deployment check"
                    className="w-full rounded-lg border border-[#2a2e40] bg-[#0e111a] px-4 py-2.5 text-white placeholder-[#5a6072] outline-none focus:border-[#4f6df5] focus:ring-1 focus:ring-[#4f6df5] transition"
                  />
                </div>
                
                <div>
                  <label htmlFor="snapshotComments" className="mb-1.5 block text-sm font-medium text-[#9099ab]">
                    Comments <span className="text-xs font-normal opacity-70">(Optional)</span>
                  </label>
                  <textarea
                    id="snapshotComments"
                    value={snapshotComments}
                    onChange={(e) => setSnapshotComments(e.target.value)}
                    placeholder="Add notes about this cluster state..."
                    rows={4}
                    className="w-full resize-none rounded-lg border border-[#2a2e40] bg-[#0e111a] px-4 py-2.5 text-white placeholder-[#5a6072] outline-none focus:border-[#4f6df5] focus:ring-1 focus:ring-[#4f6df5] transition"
                  />
                </div>
              </div>

              <div className="mt-8 flex justify-end gap-3">
                <button
                  type="button"
                  onClick={() => setIsModalOpen(false)}
                  className="rounded-lg px-4 py-2 text-sm font-medium text-[#9099ab] hover:bg-white/5 hover:text-white transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isRefreshing}
                  className="flex items-center justify-center gap-2 rounded-lg bg-[#4f6df5] px-5 py-2 text-sm font-semibold text-white shadow-lg transition hover:bg-[#4f6df5]/90 hover:shadow-[#4f6df5]/20 active:translate-y-px disabled:opacity-50"
                >
                  {isRefreshing ? (
                    <>
                      <Loader2 size={16} className="animate-spin" />
                      Creating...
                    </>
                  ) : (
                    "Create Snapshot"
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  );
}