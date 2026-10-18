// Today's markets in a few plain sentences, built from the day's published figures. Each line is a message key and
// its values, so the wording lives in messages/ (and passes the copy lint) and only describes what happened.
import { lkr, num, percent, ratio } from "./format";

export interface SummaryLine {
  key: string;
  values: Record<string, string>;
}

export interface SummaryInput {
  aspi?: { value: number; pct: number | null } | null;
  breadth?: { up: number; down: number; flat: number } | null;
  turnover?: { value: number | null; avg20: number | null } | null;
  foreignNet?: number | null;
  curve?: { y1: number; y5: number; y10: number } | null;
}

export function marketSummary(s: SummaryInput): SummaryLine[] {
  const out: SummaryLine[] = [];
  if (s.aspi) {
    const p = s.aspi.pct ?? 0;
    const dir = p > 0.00005 ? "aspiUp" : p < -0.00005 ? "aspiDown" : "aspiFlat";
    out.push({ key: `home.summary.${dir}`, values: { pct: `${num(Math.abs(p) * 100, 2)}%`, value: num(s.aspi.value) } });
  }
  if (s.breadth && s.breadth.up + s.breadth.down + s.breadth.flat > 0) {
    out.push({ key: "home.summary.breadth", values: { up: String(s.breadth.up), down: String(s.breadth.down), flat: String(s.breadth.flat) } });
  }
  if (s.turnover?.value) {
    if (s.turnover.avg20) {
      out.push({ key: "home.summary.turnoverAvg", values: { value: lkr(s.turnover.value), ratio: ratio(s.turnover.value / s.turnover.avg20) } });
    } else {
      out.push({ key: "home.summary.turnover", values: { value: lkr(s.turnover.value) } });
    }
  }
  if (s.foreignNet != null && s.foreignNet !== 0) {
    out.push({ key: s.foreignNet > 0 ? "home.summary.foreignIn" : "home.summary.foreignOut", values: { value: lkr(Math.abs(s.foreignNet)) } });
  }
  if (s.curve) {
    out.push({ key: "home.summary.bonds", values: { y1: percent(s.curve.y1, 2), y5: percent(s.curve.y5, 2), y10: percent(s.curve.y10, 2) } });
  }
  return out;
}
