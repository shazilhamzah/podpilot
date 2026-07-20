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
  Sparkles,
  Check,
} from "lucide-react";

import PodPilotLogo from "./PodPilotLogo";
import { cachedFetch } from "../utils/fetchCache";

const NAV_ITEMS = [
  { label: "Chat", icon: MessageSquare },
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

  const [indicator, setIndicator] = useState({
    left: 0,
    width: 0,
    ready: false,
  });

  const [snapshotAge, setSnapshotAge] = useState("Loading...");
  const [isRefreshing, setIsRefreshing] = useState(false);

  // Modal state
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [snapshotName, setSnapshotName] = useState("");
  const [snapshotComments, setSnapshotComments] = useState("");

  // Custom dropdown state
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(event.target)
      ) {
        setIsDropdownOpen(false);
      }
    };

    document.addEventListener("mousedown", handleClickOutside);

    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, []);

  const selectedSnapshot =
    snapshots?.find((snapshot) => snapshot.id === selectedSnapshotId);

  const selectedSnapshotLabel = selectedSnapshot
    ? selectedSnapshot.name ||
    `Snapshot at ${new Date(
      selectedSnapshot.captured_at,
    ).toLocaleDateString()}`
    : "Select Snapshot...";

  // Measure the active navigation tab.
  useLayoutEffect(() => {
    const measure = () => {
      const element = tabRefs.current[activeTab];

      if (element) {
        setIndicator({
          left: element.offsetLeft,
          width: element.offsetWidth,
          ready: true,
        });
      }
    };

    measure();
    window.addEventListener("resize", measure);

    return () => {
      window.removeEventListener("resize", measure);
    };
  }, [activeTab]);

  useEffect(() => {
    const fetchSnapshotStatus = async () => {
      setSnapshotAge("Loading...");

      try {
        const backendUrl =
          import.meta.env.VITE_API_BASE_URL ||
          `http://${window.location.hostname}:8000`;

        const url = selectedSnapshotId
          ? `${backendUrl}/snapshot?snapshot_id=${selectedSnapshotId}`
          : `${backendUrl}/snapshot`;

        const response = await cachedFetch(url);
        const data = await response.json();

        if (!data.cached_at) {
          setSnapshotAge("Never");
          return;
        }

        const cachedDate = new Date(data.cached_at);
        const differenceInMinutes = Math.round(
          (new Date() - cachedDate) / 60000,
        );

        if (differenceInMinutes <= 0) {
          setSnapshotAge("Just now");
        } else if (differenceInMinutes < 60) {
          setSnapshotAge(`${differenceInMinutes} mins ago`);
        } else if (differenceInMinutes < 1440) {
          const hours = Math.round(differenceInMinutes / 60);

          setSnapshotAge(
            `${hours} ${hours === 1 ? "hr" : "hrs"} ago`,
          );
        } else {
          const days = Math.round(differenceInMinutes / 1440);

          setSnapshotAge(
            `${days} ${days === 1 ? "day" : "days"} ago`,
          );
        }
      } catch {
        setSnapshotAge("Unknown");
      }
    };

    fetchSnapshotStatus();

    const interval = setInterval(fetchSnapshotStatus, 60000);

    return () => {
      clearInterval(interval);
    };
  }, [selectedSnapshotId]);

  const handleCreateSnapshot = async (event) => {
    event.preventDefault();

    setIsRefreshing(true);
    setSnapshotAge("Creating...");
    setIsModalOpen(false);
    setSelectedSnapshotId("");

    try {
      const backendUrl =
        import.meta.env.VITE_API_BASE_URL ||
        `http://${window.location.hostname}:8000`;

      await fetch(`${backendUrl}/refresh`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          name: snapshotName.trim() || null,
          comments: snapshotComments.trim() || null,
        }),
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
    } catch {
      setSnapshotAge("Error");
    } finally {
      setIsRefreshing(false);
    }
  };

  return (
    <>
      <header className="relative flex items-center gap-7 border-b border-[#1c1f2f] bg-[#171c2a] px-7 py-3.5">
        <div className="pointer-events-none absolute inset-0 overflow-hidden">
          <div
            className="absolute -left-24 -top-40 h-64 w-96 rotate-[-20deg] bg-[#171C2A] via-[#4f6df5]/40 to-transparent opacity-70 blur-2xl"
            aria-hidden="true"
          />
        </div>

        {/* Brand */}
        <div className="relative z-10 flex items-center gap-2">
          <PodPilotLogo size={30} />

          <span className="text-[15.5px] font-semibold tracking-tight text-[#e7e9ee]">
            Pod Pilot
          </span>
        </div>

        {/* Navigation tabs */}
        <nav
          className="relative z-10 ml-2 hidden items-center gap-1 md:flex"
          aria-label="Main navigation"
        >
          {NAV_ITEMS.map(({ label, icon: Icon }) => {
            const active = label === activeTab;

            return (
              <button
                type="button"
                key={label}
                ref={(element) => {
                  tabRefs.current[label] = element;
                }}
                onClick={() => onTabChange(label)}
                aria-pressed={active}
                className={`relative flex items-center gap-1.5 rounded-lg px-3 py-2 text-[13.5px] font-medium transition-colors duration-200 ${active
                  ? "text-[#4f6df5]"
                  : "text-[#9099ab] hover:bg-white/5 hover:text-[#e7e9ee]"
                  }`}
              >
                <Icon size={15} />
                {label}
              </button>
            );
          })}

          <span
            className={`pointer-events-none absolute -bottom-[13px] h-0.5 rounded-full bg-[#4f6df5] transition-[transform,width] duration-300 ease-out ${indicator.ready ? "opacity-100" : "opacity-0"
              }`}
            style={{
              width: Math.max(indicator.width - 24, 0),
              transform: `translateX(${indicator.left + 12}px)`,
            }}
          />
        </nav>

        {/* Right-side controls */}
        <div className="relative z-10 ml-auto flex items-center gap-4">
          {/* Hide System K8s Toggle */}
          <label className="flex items-center gap-2 cursor-pointer mr-2">
            <span className="text-[11.5px] font-semibold uppercase tracking-wider text-[#9099ab]">
              Hide System
            </span>
            <div 
              className={`relative inline-flex h-[20px] w-[36px] items-center rounded-full transition-colors ${hideSystemK8s ? 'bg-[#4f6df5]' : 'bg-[#1c2235] border border-[#2a2e40]'}`}
              onClick={(e) => {
                e.preventDefault();
                setHideSystemK8s(!hideSystemK8s);
              }}
            >
              <span 
                className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform ${hideSystemK8s ? 'translate-x-[18px]' : 'translate-x-[4px]'}`} 
              />
            </div>
          </label>

          {/* Separate Impact Report button */}
          <button
            type="button"
            onClick={onImpactReport}
            className="flex h-9 shrink-0 items-center gap-2 rounded-lg bg-gradient-to-r from-[#6f7bff] to-[#3546c4] px-3.5 text-[13.5px] font-semibold text-white shadow-[0_2px_8px_rgba(79,109,245,0.25)] transition-all hover:brightness-110 hover:shadow-[0_4px_12px_rgba(79,109,245,0.4)] active:translate-y-px"
          >
            <Sparkles size={16} aria-hidden="true" />
            Impact Report
          </button>

          {/* Snapshot selector */}
          <div
            className="mr-3 flex items-center gap-2"
            ref={dropdownRef}
          >
            <span className="text-[11.5px] font-semibold uppercase tracking-wider text-[#9099ab]">
              Context:
            </span>

            <div className="relative">
              <button
                type="button"
                onClick={() => setIsDropdownOpen((open) => !open)}
                aria-haspopup="listbox"
                aria-expanded={isDropdownOpen}
                className="flex min-w-[190px] cursor-pointer items-center justify-between gap-2 rounded-lg border border-[#1c1f2f] bg-[#0d0f18] px-3 py-1.5 text-[13px] font-medium text-[#e7e9ee] shadow-sm outline-none transition-all hover:border-[#2a2f45] hover:bg-[#121421] focus:border-[#4f6df5] focus:ring-1 focus:ring-[#4f6df5]/50"
              >
                <span className="max-w-[140px] truncate">
                  {selectedSnapshotLabel}
                </span>

                <ChevronDown
                  size={14}
                  className={`text-[#9099ab] transition-transform duration-200 ${isDropdownOpen ? "rotate-180" : ""
                    }`}
                />
              </button>

              {isDropdownOpen && (
                <div
                  role="listbox"
                  className="absolute right-0 z-50 mt-1.5 max-h-72 w-80 overflow-y-auto rounded-lg border border-[#2a2e40] bg-[#171c2a] py-1 shadow-xl"
                >
                  {!snapshots || snapshots.length === 0 ? (
                    <div className="px-3.5 py-2 text-[13px] text-[#9099ab]">
                      Loading snapshots...
                    </div>
                  ) : (
                    snapshots.map((snapshot, index) => {
                      const isSelected =
                        snapshot.id === selectedSnapshotId;

                      const date = new Date(
                        snapshot.captured_at,
                      ).toLocaleString();

                      return (
                        <button
                          type="button"
                          role="option"
                          aria-selected={isSelected}
                          key={snapshot.id}
                          onClick={() => {
                            setSelectedSnapshotId(snapshot.id);
                            setIsDropdownOpen(false);
                          }}
                          className={`flex w-full cursor-pointer items-start justify-between gap-2 border-b border-[#2a2e40]/30 px-3.5 py-2.5 text-left transition-colors last:border-b-0 hover:bg-[#4f6df5]/10 hover:text-white ${isSelected
                            ? "bg-[#4f6df5]/15 text-white"
                            : "text-[#e7e9ee]"
                            }`}
                        >
                          <div className="min-w-0 flex-1">
                            <div className="flex flex-wrap items-center gap-1.5">
                              <span className="max-w-[180px] truncate text-[13px] font-semibold">
                                {snapshot.name || "Snapshot"}
                              </span>

                              {index === 0 && (
                                <span className="rounded bg-[#4f6df5]/20 px-1.5 py-0.5 text-[9.5px] font-semibold text-[#6f7bff]">
                                  Latest
                                </span>
                              )}
                            </div>

                            <span className="mt-0.5 block text-[11px] text-[#9099ab]">
                              {date}
                            </span>

                            {snapshot.comments && (
                              <span className="mt-1 block line-clamp-2 text-[11.5px] italic text-[#9099ab]/80">
                                &ldquo;{snapshot.comments}&rdquo;
                              </span>
                            )}
                          </div>

                          {isSelected && (
                            <Check
                              size={14}
                              className="mt-1 shrink-0 text-[#4f6df5]"
                            />
                          )}
                        </button>
                      );
                    })
                  )}
                </div>
              )}
            </div>
          </div>

          {/* Snapshot age */}
          <div className="text-right leading-tight">
            <p className="m-0 text-[12px] text-[#9099ab]">
              Snapshot taken
            </p>

            <p className="m-0 text-[14px] font-semibold text-[#e7e9ee]">
              {snapshotAge}
            </p>
          </div>

          {/* Create snapshot button */}
          <button
            type="button"
            onClick={() => setIsModalOpen(true)}
            disabled={isRefreshing}
            aria-label="Create snapshot"
            className={`flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-r from-[#6f7bff] to-[#3546c4] text-white shadow-[0_2px_8px_rgba(79,109,245,0.25)] transition-all hover:brightness-110 hover:shadow-[0_4px_12px_rgba(79,109,245,0.4)] ${isRefreshing
              ? "cursor-not-allowed opacity-50"
              : "active:scale-95"
              }`}
          >
            {isRefreshing ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <Plus size={14} />
            )}
          </button>
        </div>
      </header>

      {/* Create Snapshot modal */}
      {isModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-xl border border-[#2a2e40] bg-[#171c2a] shadow-2xl">
            <div className="flex items-center justify-between border-b border-[#2a2e40] px-6 py-4">
              <h2 className="text-lg font-semibold text-white">
                Create Snapshot
              </h2>

              <button
                type="button"
                onClick={() => setIsModalOpen(false)}
                aria-label="Close create snapshot modal"
                className="rounded-lg p-1.5 text-[#9099ab] transition hover:bg-white/10 hover:text-white"
              >
                <X size={20} />
              </button>
            </div>

            <form onSubmit={handleCreateSnapshot} className="p-6">
              <div className="space-y-4">
                <div>
                  <label
                    htmlFor="snapshotName"
                    className="mb-1.5 block text-sm font-medium text-[#9099ab]"
                  >
                    Snapshot Name{" "}
                    <span className="text-xs font-normal opacity-70">
                      (Optional)
                    </span>
                  </label>

                  <input
                    id="snapshotName"
                    type="text"
                    value={snapshotName}
                    onChange={(event) =>
                      setSnapshotName(event.target.value)
                    }
                    placeholder="e.g. Pre-deployment check"
                    className="w-full rounded-lg border border-[#2a2e40] bg-[#0e111a] px-4 py-2.5 text-white placeholder-[#5a6072] outline-none transition focus:border-[#4f6df5] focus:ring-1 focus:ring-[#4f6df5]"
                  />
                </div>

                <div>
                  <label
                    htmlFor="snapshotComments"
                    className="mb-1.5 block text-sm font-medium text-[#9099ab]"
                  >
                    Comments{" "}
                    <span className="text-xs font-normal opacity-70">
                      (Optional)
                    </span>
                  </label>

                  <textarea
                    id="snapshotComments"
                    value={snapshotComments}
                    onChange={(event) =>
                      setSnapshotComments(event.target.value)
                    }
                    placeholder="Add notes about this cluster state..."
                    rows={4}
                    className="w-full resize-none rounded-lg border border-[#2a2e40] bg-[#0e111a] px-4 py-2.5 text-white placeholder-[#5a6072] outline-none transition focus:border-[#4f6df5] focus:ring-1 focus:ring-[#4f6df5]"
                  />
                </div>
              </div>

              <div className="mt-8 flex justify-end gap-3">
                <button
                  type="button"
                  onClick={() => setIsModalOpen(false)}
                  className="rounded-lg px-4 py-2 text-sm font-medium text-[#9099ab] transition hover:bg-white/5 hover:text-white"
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