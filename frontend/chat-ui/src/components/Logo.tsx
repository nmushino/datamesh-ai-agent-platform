export function Logo({ size = 40 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 100 100"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-label="Data Integration Modernization logo"
    >
      <g stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" fill="none">
        <polygon points="50,4 68,14 68,34 50,44 32,34 32,14" />
        <polygon points="50,44 68,34 86,44 86,64 68,74 50,64" />
        <polygon points="50,44 32,34 14,44 14,64 32,74 50,64" />
        <polygon points="50,64 68,74 68,94 50,96 32,94 32,74" />
        <line x1="50" y1="4" x2="50" y2="44" />
        <line x1="50" y1="44" x2="50" y2="64" />
        <line x1="50" y1="64" x2="50" y2="96" />
        <line x1="32" y1="14" x2="14" y2="44" />
        <line x1="68" y1="14" x2="86" y2="44" />
        <line x1="32" y1="74" x2="14" y2="64" />
        <line x1="68" y1="74" x2="86" y2="64" />
        <line x1="32" y1="34" x2="14" y2="44" />
        <line x1="68" y1="34" x2="86" y2="44" />
        <line x1="32" y1="34" x2="32" y2="74" />
        <line x1="68" y1="34" x2="68" y2="74" />
        <line x1="14" y1="44" x2="14" y2="64" />
        <line x1="86" y1="44" x2="86" y2="64" />
        <line x1="32" y1="94" x2="14" y2="64" />
        <line x1="68" y1="94" x2="86" y2="64" />
      </g>
    </svg>
  );
}
