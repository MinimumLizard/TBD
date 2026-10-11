export const HEADLINE_INDICES = ["ASI", "S&P SL20", "ASTRI", "S&P SL20 TRI"] as const;
export const MOVERS_MIN_TURNOVER = 1_000_000; // the old terminal's display floor for largest rises and falls (Rs)

export function isHeadline(code: string): code is (typeof HEADLINE_INDICES)[number] {
  return (HEADLINE_INDICES as readonly string[]).includes(code);
}
