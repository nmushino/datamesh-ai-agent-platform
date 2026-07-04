export function DatameshHubIcon({ size = 22 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 100 100"
      xmlns="http://www.w3.org/2000/svg"
      aria-label="Datamesh Hub"
    >
      <circle cx="50" cy="50" r="50" fill="#0a0a0a" />
      <polygon
        points="50,24 65,38 50,52 35,38"
        fill="none"
        stroke="#e8352a"
        strokeWidth="3.5"
        strokeLinejoin="round"
      />
      <polyline
        points="31,57 50,68 69,57"
        fill="none"
        stroke="#ffffff"
        strokeWidth="3.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <polyline
        points="31,70 50,81 69,70"
        fill="none"
        stroke="#ffffff"
        strokeWidth="3.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
