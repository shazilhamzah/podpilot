/* Hallmark · component: Header · genre: modern-minimal
 * states: default · hover · focus · active · disabled
 * contrast: pass
 */
import {
  useState,
  useRef,
  useLayoutEffect,
  useEffect,
} from "react";

import {
  ChevronDown,
  MessageSquare,
  Wallet,
  GitCompareArrows,
  ShieldCheck,
  Plus,
  X,
  Loader2,
  Activity,
  Check,
  Server,
} from "lucide-react";

import PodPilotLogo from "./PodPilotLogo";
import { cachedFetch } from "../utils/fetchCache";

const NAV_ITEMS = [
  { label: "Chat", icon: MessageSquare },
  { label: "Cluster Resources", icon: Server },
  { label: "Cost Breakdown", icon: Wallet },
  { label: "Drift Detection", icon: GitCompareArrows },
  { label: "Security", icon: ShieldCheck },
];

export default function Header({
  activeTab,
  onTabChange,
  snapshots,
  selectedSnapshotId,
  setSelectedSnapshotId,
  onSnapshotCreated,
  hideSystemK8s,
  setHideSystemK8s,
  onImpactReport,
}) {
  const tabRefs = useRef({});
  const dropdownRef = useRef(null);

  const [indicator, setIndicator] = useState({ left: 0, width: 0, ready: false });

  const [snapshotAge, setSnapshotAge] = useState("Loading...");
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [snapshotName, setSnapshotName] = useState("");
  const [snapshotComments, setSnapshotComments] = useState("");
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setIsDropdownOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const selectedSnapshot = snapshots?.find((s) => s.id === selectedSnapshotId);
  const selectedSnapshotLabel = selectedSnapshot
    ? selectedSnapshot.name || `Snapshot at ${new Date(selectedSnapshot.captured_at).toLocaleDateString()}`
    : "Select Snapshot...";

  useLayoutEffect(() => {
    const measure = () => {
      const element = tabRefs.current[activeTab];
      if (element) {
        setIndicator({ left: element.offsetLeft, width: element.offsetWidth, ready: true });
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
        const response = await cachedFetch(url);
        const data = await response.json();
        if (!data.cached_at) {
          setSnapshotAge("Never");
          return;
        }
        const cachedDate = new Date(data.cached_at);
        const diffMins = Math.round((new Date() - cachedDate) / 60000);
        
        if (diffMins <= 0) setSnapshotAge("Just now");
        else if (diffMins < 60) setSnapshotAge(`${diffMins}m ago`);
        else if (diffMins < 1440) {
          const hrs = Math.round(diffMins / 60);
          setSnapshotAge(`${hrs}h ago`);
        } else {
          const days = Math.round(diffMins / 1440);
          setSnapshotAge(`${days}d ago`);
        }
      } catch {
        setSnapshotAge("Unknown");
      }
    };

    fetchSnapshotStatus();
    const interval = setInterval(fetchSnapshotStatus, 60000);
    return () => clearInterval(interval);
  }, [selectedSnapshotId]);

  const handleCreateSnapshot = async (event) => {
    event.preventDefault();
    setIsRefreshing(true);
    setSnapshotAge("Creating...");
    setIsModalOpen(false);
    setSelectedSnapshotId("");

    try {
      const backendUrl = import.meta.env.VITE_API_BASE_URL || `http://${window.location.hostname}:8000`;
      await fetch(`${backendUrl}/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: snapshotName.trim() || null,
          comments: snapshotComments.trim() || null,
        }),
      });

      setSnapshotAge("Just now");
      setSnapshotName("");
      setSnapshotComments("");
      if (onSnapshotCreated) onSnapshotCreated();
      setTimeout(() => window.location.reload(), 3000);
    } catch {
      setSnapshotAge("Error");
    } finally {
      setIsRefreshing(false);
    }
  };

  return (
    <>
      <header className="relative flex h-14 items-center justify-between border-b border-[#1c1f2f] bg-[#121421] px-6">
        {/* Brand */}
        <div className="flex items-center gap-3">
          <PodPilotLogo size={22} />
          <span className="text-[14px] font-medium tracking-tight text-[#e7e9ee]">
            Pod Pilot
          </span>
        </div>

        {/* Navigation tabs */}
        <nav
          className="hidden flex-1 justify-center items-center gap-1 md:flex"
          aria-label="Main navigation"
        >
          {NAV_ITEMS.map(({ label, icon: Icon }) => {
            const active = label === activeTab;
            return (
              <button
                type="button"
                key={label}
                ref={(el) => { tabRefs.current[label] = el; }}
                onClick={() => onTabChange(label)}
                aria-pressed={active}
                className={`relative flex items-center gap-2 rounded-md px-3 py-1.5 text-[13px] font-medium transition-colors duration-200 ${
                  active
                    ? "text-[#e7e9ee]"
                    : "text-[#9099ab] hover:bg-white/5 hover:text-[#e7e9ee]"
                }`}
              >
                <Icon size={14} className={active ? "text-[#4f6df5]" : "opacity-70"} />
                {label}
              </button>
            );
          })}
          <span
            className={`pointer-events-none absolute -bottom-[11px] h-[2px] rounded-t-sm bg-[#4f6df5] transition-[transform,width] duration-300 ease-[cubic-bezier(0.16,1,0.3,1)] ${indicator.ready ? "opacity-100" : "opacity-0"}`}
            style={{
              width: Math.max(indicator.width - 24, 0),
              transform: `translateX(${indicator.left + 12}px)`,
            }}
          />
        </nav>

        {/* Right-side controls */}
        <div className="flex items-center gap-3">
          <label className="flex cursor-pointer items-center gap-2 rounded-md border border-transparent px-2 py-1.5 transition-colors hover:bg-white/5">
            <span className="text-[12px] font-medium text-[#9099ab]">System</span>
            <div 
              className={`relative inline-flex h-4 w-7 items-center rounded-full transition-colors ${hideSystemK8s ? 'bg-[#1c2235] border border-[#2a2e40]' : 'bg-[#4f6df5]'}`}
              onClick={(e) => {
                e.preventDefault();
                setHideSystemK8s(!hideSystemK8s);
              }}
            >
              <span 
                className={`inline-block h-2.5 w-2.5 transform rounded-full bg-white transition-transform ${hideSystemK8s ? 'translate-x-[3px]' : 'translate-x-[15px]'}`} 
              />
            </div>
          </label>

          <div className="h-4 w-px bg-[#2a2e40]" aria-hidden="true" />

          <button
            type="button"
            onClick={onImpactReport}
            className="flex items-center gap-1.5 rounded-md px-3 py-1.5 text-[13px] font-medium text-[#e7e9ee] transition-colors hover:bg-white/5"
          >
            <Activity size={14} className="text-[#9099ab]" aria-hidden="true" />
            Report
          </button>

          {/* Consolidated Context / Snapshot Menu */}
          <div className="relative" ref={dropdownRef}>
            <button
              type="button"
              onClick={() => setIsDropdownOpen(!isDropdownOpen)}
              className="flex min-w-[200px] cursor-pointer items-center justify-between gap-3 rounded-md border border-[#2a2e40] bg-[#171c2a] px-3 py-1.5 text-[13px] font-medium text-[#e7e9ee] shadow-sm transition-colors hover:border-[#4f6df5]/50 focus:border-[#4f6df5] focus:outline-none focus:ring-1 focus:ring-[#4f6df5]/50"
            >
              <div className="flex items-center gap-2 truncate">
                <span className="truncate max-w-[120px]">{selectedSnapshotLabel}</span>
                <span className="text-[11px] font-normal text-[#9099ab]">· {snapshotAge}</span>
              </div>
              <ChevronDown size={14} className={`shrink-0 text-[#9099ab] transition-transform ${isDropdownOpen ? "rotate-180" : ""}`} />
            </button>

            {isDropdownOpen && (
              <div className="absolute right-0 z-50 mt-1.5 w-[280px] origin-top-right rounded-lg border border-[#2a2e40] bg-[#171c2a] py-1.5 shadow-xl outline-none">
                <div className="px-3 pb-2 pt-1">
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] font-medium uppercase tracking-wider text-[#9099ab]">Snapshots</span>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        setIsDropdownOpen(false);
                        setIsModalOpen(true);
                      }}
                      disabled={isRefreshing}
                      className="flex items-center gap-1 rounded text-[11px] font-medium text-[#4f6df5] hover:text-[#6f7bff] disabled:opacity-50"
                    >
                      {isRefreshing ? <Loader2 size={12} className="animate-spin" /> : <Plus size={12} />}
                      New
                    </button>
                  </div>
                </div>
                
                <div className="max-h-60 overflow-y-auto border-t border-[#2a2e40]/50 pt-1">
                  {!snapshots?.length ? (
                    <div className="px-3 py-2 text-[12px] text-[#9099ab]">Loading...</div>
                  ) : (
                    snapshots.map((snapshot, idx) => {
                      const isSelected = snapshot.id === selectedSnapshotId;
                      return (
                        <button
                          key={snapshot.id}
                          onClick={() => {
                            setSelectedSnapshotId(snapshot.id);
                            setIsDropdownOpen(false);
                          }}
                          className={`flex w-full items-start justify-between gap-2 px-3 py-2 text-left text-[13px] transition-colors hover:bg-white/5 ${isSelected ? "text-white" : "text-[#e7e9ee]"}`}
                        >
                          <div className="flex flex-col gap-0.5 overflow-hidden">
                            <span className="truncate font-medium">
                              {snapshot.name || "Snapshot"}
                              {idx === 0 && <span className="ml-2 rounded-sm bg-[#4f6df5]/20 px-1 text-[10px] text-[#4f6df5]">Latest</span>}
                            </span>
                            <span className="truncate text-[11px] text-[#9099ab]">{new Date(snapshot.captured_at).toLocaleString()}</span>
                          </div>
                          {isSelected && <Check size={14} className="mt-0.5 shrink-0 text-[#4f6df5]" />}
                        </button>
                      );
                    })
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      </header>

      {/* Create Snapshot Modal */}
      {isModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-[#0d0f18]/80 backdrop-blur-sm">
          <div className="w-full max-w-[400px] overflow-hidden rounded-xl border border-[#2a2e40] bg-[#171c2a] shadow-2xl">
            <div className="flex items-center justify-between border-b border-[#2a2e40] px-5 py-3.5">
              <h2 className="text-[15px] font-medium text-white">Create Snapshot</h2>
              <button
                onClick={() => setIsModalOpen(false)}
                className="rounded-md p-1 text-[#9099ab] transition-colors hover:bg-white/10 hover:text-white"
              >
                <X size={16} />
              </button>
            </div>

            <form onSubmit={handleCreateSnapshot} className="p-5">
              <div className="space-y-4">
                <div>
                  <label htmlFor="snapshotName" className="mb-1.5 block text-[13px] font-medium text-[#e7e9ee]">
                    Name <span className="font-normal text-[#9099ab]">(optional)</span>
                  </label>
                  <input
                    id="snapshotName"
                    type="text"
                    value={snapshotName}
                    onChange={(e) => setSnapshotName(e.target.value)}
                    placeholder="e.g. Pre-deployment state"
                    className="w-full rounded-md border border-[#2a2e40] bg-[#121421] px-3 py-2 text-[13px] text-white placeholder:text-[#5a6072] focus:border-[#4f6df5] focus:outline-none focus:ring-1 focus:ring-[#4f6df5]"
                  />
                </div>

                <div>
                  <label htmlFor="snapshotComments" className="mb-1.5 block text-[13px] font-medium text-[#e7e9ee]">
                    Notes <span className="font-normal text-[#9099ab]">(optional)</span>
                  </label>
                  <textarea
                    id="snapshotComments"
                    value={snapshotComments}
                    onChange={(e) => setSnapshotComments(e.target.value)}
                    placeholder="Context for this capture..."
                    rows={3}
                    className="w-full resize-none rounded-md border border-[#2a2e40] bg-[#121421] px-3 py-2 text-[13px] text-white placeholder:text-[#5a6072] focus:border-[#4f6df5] focus:outline-none focus:ring-1 focus:ring-[#4f6df5]"
                  />
                </div>
              </div>

              <div className="mt-6 flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setIsModalOpen(false)}
                  className="rounded-md px-3 py-1.5 text-[13px] font-medium text-[#9099ab] hover:bg-white/5 hover:text-white"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isRefreshing}
                  className="flex min-w-[80px] items-center justify-center gap-1.5 rounded-md bg-[#e7e9ee] px-3 py-1.5 text-[13px] font-semibold text-[#121421] transition-transform active:scale-[0.98] disabled:opacity-50"
                >
                  {isRefreshing ? <Loader2 size={14} className="animate-spin text-[#121421]" /> : "Create"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  );
}
