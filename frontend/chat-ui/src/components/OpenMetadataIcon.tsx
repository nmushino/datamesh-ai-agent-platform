export function OpenMetadataIcon({ size = 22 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 100 100"
      xmlns="http://www.w3.org/2000/svg"
      aria-label="OpenMetadata"
    >
      <defs>
        <linearGradient id="om-cylinder" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#b9a6f7" />
          <stop offset="45%" stopColor="#7c5cf0" />
          <stop offset="100%" stopColor="#3e2489" />
        </linearGradient>
        <linearGradient id="om-top" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#cfc1fb" />
          <stop offset="100%" stopColor="#a48ff2" />
        </linearGradient>
      </defs>

      {/* シリンダー本体 */}
      <path
        d="M10 24 a40 15 0 0 0 80 0 v52 a40 15 0 0 1 -80 0 Z"
        fill="url(#om-cylinder)"
      />
      {/* 上面 (開口部) */}
      <ellipse cx="50" cy="24" rx="40" ry="15" fill="url(#om-top)" />

      {/* 白い M マーク */}
      <path
        d="M28 68 V38 L50 58 L72 38 V68"
        fill="none"
        stroke="#ffffff"
        strokeWidth="9"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
