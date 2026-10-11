// Dates on this site are Sri Lanka dates (Asia/Colombo, UTC+5:30), as ISO strings (YYYY-MM-DD).

export function todaySLT(now: Date = new Date()): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Colombo" }).format(now);
}

export function addDays(iso: string, days: number): string {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

/** A real calendar date in a sensible range (Date.parse alone accepts 2026-02-30). */
export function isIsoDate(value: unknown): value is string {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const d = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(d.getTime()) && d.toISOString().slice(0, 10) === value && value >= "2000-01-01" && value <= "2099-12-31";
}
