export function BrandLogo({ collapsed = false }: { collapsed?: boolean }) {
  return (
    <div className="flex items-center gap-2.5 select-none">
      {/* Icon mark */}
      <svg width="32" height="32" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <linearGradient id="logoGrad" x1="4" y1="2" x2="28" y2="30" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#2dd4bf" />
            <stop offset="100%" stopColor="#0d9488" />
          </linearGradient>
        </defs>
        {/* Hexagon background */}
        <path
          d="M16 2L28.124 9V23L16 30L3.876 23V9L16 2Z"
          fill="url(#logoGrad)"
        />
        {/* Head silhouette */}
        <ellipse cx="16" cy="13.5" rx="5.5" ry="6" fill="rgba(255,255,255,0.25)" />
        {/* Brain circuit lines */}
        <circle cx="16" cy="13" r="3.5" fill="none" stroke="white" strokeWidth="1.2" strokeOpacity="0.9" />
        <line x1="16" y1="9.5" x2="16" y2="7" stroke="white" strokeWidth="1" strokeOpacity="0.7" strokeLinecap="round" />
        <line x1="19.3" y1="11" x2="21.5" y2="9.5" stroke="white" strokeWidth="1" strokeOpacity="0.7" strokeLinecap="round" />
        <line x1="19.3" y1="15" x2="21.5" y2="16.5" stroke="white" strokeWidth="1" strokeOpacity="0.7" strokeLinecap="round" />
        <line x1="12.7" y1="11" x2="10.5" y2="9.5" stroke="white" strokeWidth="1" strokeOpacity="0.7" strokeLinecap="round" />
        <line x1="12.7" y1="15" x2="10.5" y2="16.5" stroke="white" strokeWidth="1" strokeOpacity="0.7" strokeLinecap="round" />
        {/* Node dots */}
        <circle cx="16" cy="7" r="1.2" fill="white" fillOpacity="0.9" />
        <circle cx="21.5" cy="9.5" r="1.2" fill="white" fillOpacity="0.9" />
        <circle cx="21.5" cy="16.5" r="1.2" fill="white" fillOpacity="0.9" />
        <circle cx="10.5" cy="9.5" r="1.2" fill="white" fillOpacity="0.9" />
        <circle cx="10.5" cy="16.5" r="1.2" fill="white" fillOpacity="0.9" />
        {/* Neck / connector */}
        <rect x="14.2" y="18.8" width="3.6" height="3" rx="1.8" fill="white" fillOpacity="0.7" />
        {/* Shoulder bar */}
        <rect x="10" y="22.5" width="12" height="2" rx="1" fill="white" fillOpacity="0.5" />
      </svg>

      {/* Wordmark */}
      {!collapsed && (
        <div className="flex flex-col leading-none">
          <span
            className="text-white tracking-wide"
            style={{ fontSize: "15px", fontWeight: 700, letterSpacing: "0.08em" }}
          >
            神志思训
          </span>
          <span
            className="text-teal-300 tracking-widest"
            style={{ fontSize: "8px", fontWeight: 400, letterSpacing: "0.18em", marginTop: "2px" }}
          >
            AI · MIND · TRAINING
          </span>
        </div>
      )}
    </div>
  );
}
