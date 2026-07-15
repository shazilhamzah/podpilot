import { useState, useRef, useLayoutEffect } from "react";
import {MessageSquare, Wallet, GitCompareArrows, ShieldCheck, RefreshCw } from "lucide-react";
import PodPilotLogo from "./Logo";

const NAV_ITEMS = [
  { label: "Chat", icon: MessageSquare },
  { label: "Cost Breakdown", icon: Wallet },
  { label: "Drift Detection", icon: GitCompareArrows },
  { label: "Security", icon: ShieldCheck },
];

// Hardcoded for now — wire up to real snapshot state later.
const LAST_SNAPSHOT_LABEL = "Last snapshot";
const LAST_SNAPSHOT_VALUE = "2 mins ago";

export default function Header({ activeTab, onTabChange }) {
  const tabRefs = useRef({});
  const [indicator, setIndicator] = useState({ left: 0, width: 0, ready: false });

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

  return (
    <header className="relative flex items-center gap-7 overflow-hidden border-b border-[#1c1f2f] bg-[#171c2a] px-7 py-3.5">
      <div
        className="pointer-events-none absolute -left-24 -top-40 h-64 w-96 rotate-[-20deg] bg-[#171C2A] via-[#4f6df5]/40 to-transparent opacity-70 blur-2xl"
        aria-hidden="true"
      />

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
      <div className="relative z-10 ml-auto flex items-center gap-3">
        <div className="text-right leading-tight">
          <p className="m-0 text-[12px] text-[#9099ab]">{LAST_SNAPSHOT_LABEL}</p>
          <p className="m-0 text-[14px] font-semibold text-[#e7e9ee]">{LAST_SNAPSHOT_VALUE}</p>
        </div>
        <button
          className="flex h-9 w-9 items-center justify-center rounded-full border border-[#e7e9ee]/70 text-[#e7e9ee] transition hover:border-white hover:bg-white/5 active:translate-y-px"
          aria-label="Refresh snapshot"
        >
          <RefreshCw size={16} />
        </button>
      </div>
    </header>
  );
}