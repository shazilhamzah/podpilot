// Pod Pilot logo mark: a winged capsule — "pod" (the capsule) piloted through
// flight (the swept wings + tail fin). Same gradient-square app-icon
// treatment as the reference: fully-filled rounded square, single white
// glyph centered, no outline/border needed since the fill itself reads
// clearly on dark backgrounds.

export default function PodPilotLogo({ size = 30, rounded = "rounded-lg" }) {
  return (
    <span
      className={`flex shrink-0 items-center justify-center ${rounded} shadow-[0_4px_14px_rgba(79,109,245,0.35)]`}
      style={{ width: size, height: size }}
    >
      <svg viewBox="0 0 40 40" className="h-full w-full">
        <defs>
          <linearGradient id="pod-pilot-bg" x1="4" y1="2" x2="36" y2="38" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#6f7bff" />
            <stop offset="100%" stopColor="#3546c4" />
          </linearGradient>
        </defs>
        <rect x="1" y="1" width="38" height="38" rx="10" fill="url(#pod-pilot-bg)" />
        {/* swept wings */}
        <path d="M15 21 L5 27.5 L15.5 25.5 Z" fill="#ffffff" fillOpacity="0.92" />
        <path d="M25 21 L35 27.5 L24.5 25.5 Z" fill="#ffffff" fillOpacity="0.92" />
        {/* tail fin */}
        <path d="M17.3 27 L20 32.5 L22.7 27 Z" fill="#ffffff" fillOpacity="0.92" />
        {/* capsule body */}
        <rect x="14.5" y="8" width="11" height="20" rx="5.5" fill="#ffffff" />
        {/* porthole */}
        <circle cx="20" cy="14.5" r="2.4" fill="#3546c4" />
      </svg>
    </span>
  );
}