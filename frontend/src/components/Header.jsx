import { useState, useRef, useLayoutEffect, useEffect } from "react";
import { ChevronDown, MessageSquare, Wallet, GitCompareArrows, ShieldCheck, RefreshCw } from "lucide-react";

const NAV_ITEMS = [
  { label: "Chat", icon: MessageSquare },
  { label: "Cost Breakdown", icon: Wallet },
  { label: "Drift Detection", icon: GitCompareArrows },
  { label: "Security", icon: ShieldCheck },
];

export default function Header({ activeTab, onTabChange }) {
  const tabRefs = useRef({});
  const [indicator, setIndicator] = useState({ left: 0, width: 0, ready: false });
  const [snapshotAge, setSnapshotAge] = useState("Loading...");
  const [isRefreshing, setIsRefreshing] = useState(false);

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
      try {
        const backendUrl = import.meta.env.VITE_API_BASE_URL || `http://${window.location.hostname}:8000`;
        const res = await fetch(`${backendUrl}/snapshot`);
        const data = await res.json();
        if (data.cached_at) {
          const cachedDate = new Date(data.cached_at);
          const mins = Math.round((new Date() - cachedDate) / 60000);
          setSnapshotAge(mins === 0 ? "Just now" : `${mins} mins ago`);
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
  }, []);

  const handleRefresh = async () => {
    setIsRefreshing(true);
    setSnapshotAge("Refreshing...");
    try {
      const backendUrl = import.meta.env.VITE_API_BASE_URL || `http://${window.location.hostname}:8000`;
      await fetch(`${backendUrl}/refresh`, { method: "POST" });
      setSnapshotAge("Just now");
    } catch (err) {
      setSnapshotAge("Error");
    } finally {
      setIsRefreshing(false);
    }
  };

  return (
    <header className="relative flex items-center gap-7 overflow-hidden border-b border-[#1c1f2f] bg-[#171c2a] px-7 py-3.5">
      <div
        className="pointer-events-none absolute -left-24 -top-40 h-64 w-96 rotate-[-20deg] bg-[#171C2A] via-[#4f6df5]/40 to-transparent opacity-70 blur-2xl"
        aria-hidden="true"
      />

      {/* Brand */}
      <div className="relative z-10 flex items-center gap-2">
        <span className="flex h-[30px] w-[30px] items-center justify-center rounded-lg bg-[#171C2A] text-white shadow-[0_0_0_1px_rgba(79,109,245,0.35),0_4px_14px_rgba(79,109,245,0.25)]">
          <svg viewBox="0 0 24 24" fill="none" className="h-[18px] w-[18px]">
            <path
              d="M12 2 3 7v6c0 5 3.8 8.7 9 9-5.2-.3 9-4 9-9V7l-9-5Z"
              stroke="currentColor"
              strokeWidth="1.6"
              strokeLinejoin="round"
            />
            <path
              d="M8.5 12.2 11 14.6l4.5-5"
              stroke="currentColor"
              strokeWidth="1.6"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </span>
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
      <div className="relative z-10 ml-auto flex items-center gap-3">
        <div className="text-right leading-tight">
          <p className="m-0 text-[12px] text-[#9099ab]">Last snapshot</p>
          <p className="m-0 text-[14px] font-semibold text-[#e7e9ee]">{snapshotAge}</p>
        </div>
        <button
          onClick={handleRefresh}
          disabled={isRefreshing}
          className={`flex h-9 w-9 items-center justify-center rounded-full border border-[#e7e9ee]/70 text-[#e7e9ee] transition hover:border-white hover:bg-white/5 ${
            isRefreshing ? "opacity-50 cursor-not-allowed" : "active:translate-y-px"
          }`}
          aria-label="Refresh snapshot"
        >
          <RefreshCw size={16} className={isRefreshing ? "animate-spin" : ""} />
        </button>
      </div>
    </header>
  );
}