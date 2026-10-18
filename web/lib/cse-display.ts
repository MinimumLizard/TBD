export const HEADLINE_INDICES = ["ASI", "S&P SL20", "ASTRI", "S&P SL20 TRI"] as const;
export const MOVERS_MIN_TURNOVER = 1_000_000; // the old terminal's display floor for largest rises and falls (Rs)

/** A number with as many decimals as it needs, between `min` and four: 5 -> "5", 108.2352945 -> "108.2353". */
export function plainNumber(v: number, min = 0, locale = "en"): string {
  return new Intl.NumberFormat(locale, { minimumFractionDigits: min, maximumFractionDigits: 4 }).format(v);
}

/** The message (share.amounts.<key>) and values describing a corporate action's amount or ratio; null when the CSE's
 * record does not give it. */
export function actionAmount(a: {
  action_type: string;
  amount_per_share: number | null;
  ratio_new: number | null;
  ratio_held: number | null;
  factor: number | null;
  subscription_price: number | null;
}): { key: string; values: Record<string, string> } | null {
  if (a.action_type === "cash_dividend" && a.amount_per_share != null) {
    return { key: "dividend", values: { amount: plainNumber(a.amount_per_share, 2) } };
  }
  if (a.action_type === "subdivision" && a.factor != null) return { key: "split", values: { factor: plainNumber(a.factor) } };
  if (a.action_type === "scrip" && a.ratio_held != null) return { key: "scrip", values: { existing: plainNumber(a.ratio_held) } };
  if (a.action_type === "rights" && a.ratio_new != null && a.ratio_held != null) {
    const values = { new: plainNumber(a.ratio_new), existing: plainNumber(a.ratio_held) };
    return a.subscription_price != null
      ? { key: "rights", values: { ...values, price: plainNumber(a.subscription_price, 2) } }
      : { key: "rightsNoPrice", values };
  }
  return null;
}

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
