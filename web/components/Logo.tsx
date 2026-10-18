// The ZinvestIQ mark: a "Z" drawn as a rising line, with a gold point at the top. Colours come from the theme.
export default function Logo({ size = 28 }: { size?: number }) {
  return (
    <svg viewBox="0 0 32 32" width={size} height={size} aria-hidden="true" focusable="false">
      <rect width="32" height="32" rx="9" style={{ fill: "var(--navy)" }} />
      <path d="M9 10.5h12.5L9.5 22h13.5" fill="none" style={{ stroke: "#ffffff" }} strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="24" cy="9.5" r="2.6" style={{ fill: "var(--gold)" }} />
    </svg>
  );
}
