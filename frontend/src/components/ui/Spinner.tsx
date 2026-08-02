export function Spinner({ size = 20 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      style={{ animation: "argus-spin 0.7s linear infinite" }}
      aria-label="Loading"
      role="status"
    >
      <circle cx="12" cy="12" r="9" stroke="var(--surface-border)" strokeWidth="3" />
      <path d="M21 12a9 9 0 0 0-9-9" stroke="var(--accent-primary)" strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
}
