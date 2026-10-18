// The savings calculator's pure parts: month arithmetic and reading the form (a plain GET form, so it works without
// JavaScript). No data access here.

/** "2026-08-01" plus n months, as the first of the month. */
export function addMonths(iso: string, n: number): string {
  const [y, m] = iso.slice(0, 7).split("-").map(Number);
  const k = y * 12 + (m - 1) + n;
  const year = Math.floor(k / 12);
  const month = (k % 12) + 1;
  return `${String(year).padStart(4, "0")}-${String(month).padStart(2, "0")}-01`;
}

/** The last month with the deposit rate, the bill yield and the CCPI all published (as the model defines it). */
export function dataThrough(rates: { month: string; fd_rate_pct: number | null; bill_rate_pct: number | null; cpi: number | null }[]): string | null {
  let last: string | null = null;
  for (const r of rates) if (r.fd_rate_pct != null && r.bill_rate_pct != null && r.cpi != null && (!last || r.month > last)) last = r.month;
  return last;
}

export const YEARS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10] as const;
export const MAX_AMOUNT = 1_000_000_000;

export interface CalcInput {
  amount: number;
  start: string; // YYYY-MM-01
  years: number;
  invalid: boolean; // something was given but could not be read: the defaults are used for it
}

function whole(raw: string | undefined, min: number, max: number): number | null {
  if (raw === undefined || raw === "") return null;
  const cleaned = raw.replace(/[,\s]/g, "");
  if (!/^\d{1,10}$/.test(cleaned)) return NaN;
  const n = Number(cleaned);
  return n >= min && n <= max ? n : NaN;
}

/** Read ?amount=&sy=&sm=&years= against the data's range, falling back to the defaults for anything unreadable. The
 * default is the latest five-year period. A start outside the data is kept, so the page can say why it has no figure. */
export function readCalc(params: Record<string, string | string[] | undefined>, first: string, through: string): CalcInput {
  const one = (k: string) => (Array.isArray(params[k]) ? (params[k] as string[])[0] : (params[k] as string | undefined));
  const amount = whole(one("amount"), 1, MAX_AMOUNT);
  const years = whole(one("years"), 1, 10);
  const firstYear = Number(first.slice(0, 4));
  const lastYear = Number(through.slice(0, 4));
  const sy = whole(one("sy"), firstYear, lastYear);
  const sm = whole(one("sm"), 1, 12);
  const invalid = [amount, years, sy, sm].some((v) => Number.isNaN(v));
  const y = years && !Number.isNaN(years) ? years : 5;
  const fallback = addMonths(through, -12 * y);
  const startYear = sy && !Number.isNaN(sy) ? sy : Number(fallback.slice(0, 4));
  const startMonth = sm && !Number.isNaN(sm) ? sm : Number(fallback.slice(5, 7));
  return {
    amount: amount && !Number.isNaN(amount) ? amount : 100_000,
    start: `${startYear}-${String(startMonth).padStart(2, "0")}-01`,
    years: y,
    invalid,
  };
}
