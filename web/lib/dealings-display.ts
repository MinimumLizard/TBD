// Helpers for the directors' dealings pages that read no data.

export const WINDOWS = [30, 90, 365] as const;
export type FlowWindow = (typeof WINDOWS)[number];

/** A window from a query string ("30", "90", "365"); anything else is 30 days. */
export function flowWindow(value: string | null | undefined): FlowWindow {
  const n = Number(value);
  return (WINDOWS as readonly number[]).includes(n) ? (n as FlowWindow) : 30;
}

/** The company's code from a share ("AAA.N0000" -> "AAA"): dealing notices name the company, not a share class. */
export function companyCode(symbol: string): string {
  return symbol.split(".")[0];
}
