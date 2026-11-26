// The cheat-code mark: a small lightning bolt, drawn in the current colour.
export default function Bolt({ size = 14 }: { size?: number }) {
  return (
    <svg className="bolt" width={size} height={size} viewBox="0 0 24 24" aria-hidden="true">
      <path d="M13.5 2 4.5 13.5H11L9.5 22l10-12.5H13L13.5 2Z" fill="currentColor" />
    </svg>
  );
}
