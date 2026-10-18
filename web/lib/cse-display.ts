export const HEADLINE_INDICES = ["ASI", "S&P SL20", "ASTRI", "S&P SL20 TRI"] as const;
export const MOVERS_MIN_TURNOVER = 1_000_000; // the old terminal's display floor for largest rises and falls (Rs)

export function isHeadline(code: string): code is (typeof HEADLINE_INDICES)[number] {
  return (HEADLINE_INDICES as readonly string[]).includes(code);
}

// Words a company name keeps in capitals when the CSE prints the whole name in capitals.
const KEEP_UPPER = new Set(["PLC", "LTD", "LTD.", "(PVT)", "PVT", "&", "II", "III", "IV", "HNB", "NDB", "DFCC", "CIC", "LOLC", "LB", "SLT", "CT", "HDFC", "SMB", "PMF", "AIA", "HVA", "ACL", "CCS"]);

/** "JOHN KEELLS HOLDINGS PLC" -> "John Keells Holdings PLC"; a name the CSE already prints in mixed case is kept as
 * published. Display only: the stored fact is unchanged. */
export function companyName(raw: string | null | undefined): string | null {
  if (!raw) return null;
  const name = raw.replace(/\s+/g, " ").replace(/^\s|\s$/g, "");
  if (name !== name.toUpperCase()) return name;
  return name
    .split(" ")
    .map((w) => (KEEP_UPPER.has(w) ? w : w.charAt(0) + w.slice(1).toLowerCase()))
    .join(" ")
    .replace(/\b(Of|And|The|For)\b/g, (m, _w, offset) => (offset === 0 ? m : m.toLowerCase()));
}
