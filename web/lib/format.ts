// Number and date formatting, per locale. A minus sign is U+2212, and a missing value is an em dash.
const MINUS = "−";
export const NONE = "—";

function finite(v: number | null | undefined): v is number {
  return typeof v === "number" && Number.isFinite(v);
}

export function num(v: number | null | undefined, dp = 2, locale = "en"): string {
  if (!finite(v)) return NONE;
  return new Intl.NumberFormat(locale, { minimumFractionDigits: dp, maximumFractionDigits: dp }).format(v).replace("-", MINUS);
}

export function signed(v: number | null | undefined, dp = 2, locale = "en"): string {
  if (!finite(v)) return NONE;
  const body = new Intl.NumberFormat(locale, { minimumFractionDigits: dp, maximumFractionDigits: dp }).format(Math.abs(v));
  return (v > 0 ? "+" : v < 0 ? MINUS : "±") + body;
}

/** A fraction as a signed percentage: 0.0123 -> "+1.23%". */
export function pct(fraction: number | null | undefined, dp = 2, locale = "en"): string {
  return finite(fraction) ? `${signed(fraction * 100, dp, locale)}%` : NONE;
}

/** A plain percentage value (already in percent): 9.85 -> "9.85%". */
export function percent(v: number | null | undefined, dp = 2, locale = "en"): string {
  return finite(v) ? `${num(v, dp, locale)}%` : NONE;
}

export function int(v: number | null | undefined, locale = "en"): string {
  return finite(v) ? new Intl.NumberFormat(locale, { maximumFractionDigits: 0 }).format(v).replace("-", MINUS) : NONE;
}

/** Rupees as Rs mn / Rs bn. */
export function lkr(v: number | null | undefined, locale = "en"): string {
  if (!finite(v)) return NONE;
  const sign = v < 0 ? MINUS : "";
  const a = Math.abs(v);
  if (a >= 1e9) return `${sign}Rs ${num(a / 1e9, 2, locale)} bn`;
  if (a > 0 && a < 5e3) return `${sign}< Rs 0.01 mn`; // would otherwise print as a misleading "Rs 0.00 mn"
  return `${sign}Rs ${num(a / 1e6, a >= 1e7 ? 1 : 2, locale)} mn`;
}

export function ratio(v: number | null | undefined, locale = "en"): string {
  return finite(v) ? `${num(v, 2, locale)}×` : NONE;
}

export function date(iso: string | null | undefined, locale = "en"): string {
  if (!iso) return NONE;
  return new Intl.DateTimeFormat(locale, { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" }).format(
    new Date(`${iso}T00:00:00Z`),
  );
}

export function tone(v: number | null | undefined): "up" | "down" | "flat" {
  if (!finite(v) || v === 0) return "flat";
  return v > 0 ? "up" : "down";
}
