// The day's overview, read once and shared by the markets page and the tailored home pages (lib/homes.ts). Every
// figure comes through the data layer, so each is tier-checked there.
import "server-only";

import { bondCurve, bondCurveHistory } from "./data/bonds";
import { indexHistory, marketTape } from "./data/cse";
import type { Viewer } from "./entitlements";
import { nelsonSiegel } from "./charts";
import { marketSummary } from "./summary";

type Fit = { beta0: number; beta1: number; beta2: number; lambda_years: number };
export const curveYield = (fit: Fit, years: number) => nelsonSiegel(years, fit.beta0, fit.beta1, fit.beta2, fit.lambda_years);

export async function loadOverview(viewer: Viewer) {
  const [tape, aspi, sp, curve, fits] = await Promise.all([
    marketTape(viewer),
    indexHistory(viewer, "ASI"),
    indexHistory(viewer, "S&P SL20"),
    bondCurve(viewer),
    bondCurveHistory(viewer),
  ]);
  const session = tape.data?.session ?? null;
  const index = (code: string) => tape.data?.indices.find((i) => i.index_code === code) ?? null;
  const aspiNow = index("ASI");
  const fit = curve.data?.fit ?? null;
  const fitHistory = fits.data ?? [];
  const summary = marketSummary({
    aspi: aspiNow ? { value: aspiNow.value, pct: aspiNow.pct } : null,
    breadth: session ? { up: session.equities_up ?? 0, down: session.equities_down ?? 0, flat: session.equities_flat ?? 0 } : null,
    turnover: session ? { value: session.turnover, avg20: session.turnover_avg20 } : null,
    foreignNet: session?.foreign_net ?? null,
    curve: fit ? { y1: curveYield(fit, 1), y5: curveYield(fit, 5), y10: curveYield(fit, 10) } : null,
  });
  return {
    tape, aspi, sp, curve, session, aspiNow, spNow: index("S&P SL20"), fit, fitHistory, summary,
    prevFit: fitHistory.length > 1 ? fitHistory[fitHistory.length - 2] : null,
  };
}

export type Overview = Awaited<ReturnType<typeof loadOverview>>;
