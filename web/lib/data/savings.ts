// The savings education page's data (lk_savings_compare). Each function authorises the model and reads only through
// lib/db.ts.
import "server-only";

import type { Viewer } from "../entitlements";
import { readOutput } from "../db";
import { addMonths, dataThrough } from "../savings-calc";
import { type Result, withModel } from "./common";

const MODEL = "lk_savings_compare";

export interface SavingsRate {
  month: string;
  fd_rate_pct: number | null;
  fd_series: string | null;
  bill_published_pct: number | null;
  bill_rate_pct: number | null;
  cpi: number | null;
  cpi_base: string | null;
  inflation_yoy: number | null;
  fd_tax_pct: number;
}
export type Instrument = "fd" | "tbill";
export type Basis = "nominal" | "nominal_after_tax" | "real" | "real_after_tax";
export interface SavingsGrowth {
  start_month: string;
  horizon_years: number;
  instrument: Instrument;
  basis: Basis;
  end_month: string;
  value: number;
  annual_rate: number;
  fd_series: string | null;
}
export interface SavingsSummary {
  horizon_years: number;
  instrument: Instrument;
  basis: Basis;
  n_periods: number;
  first_start: string;
  last_start: string;
  n_ahead: number | null;
  n_above_start: number;
  median_value: number;
  best_value: number;
  best_start: string;
  worst_value: number;
  worst_start: string;
  median_annual: number;
  best_annual: number;
  worst_annual: number;
}
export interface SavingsOverview {
  rates: SavingsRate[];
  through: string | null; // the last month with the deposit rate, the bill yield and the CCPI all published
  summary: SavingsSummary[];
  pathStart: string | null; // the start of the latest ten-year period
  path: SavingsGrowth[]; // every horizon from pathStart
}

const GROWTH_COLUMNS = ["start_month", "horizon_years", "instrument", "basis", "end_month", "value", "annual_rate", "fd_series"];

/** Everything the page shows apart from the calculator: the monthly rates, the summary and the latest ten years. */
export async function savingsOverview(viewer: Viewer): Promise<Result<SavingsOverview>> {
  return withModel(viewer, MODEL, async (g) => {
    const [rates, summary] = await Promise.all([
      readOutput<SavingsRate>(g, "models.savings_rates", { orderBy: "month" }),
      readOutput<SavingsSummary>(g, "models.savings_summary", { orderBy: "horizon_years, instrument, basis" }),
    ]);
    const through = dataThrough(rates);
    const pathStart = through ? addMonths(through, -120) : null;
    const path = pathStart
      ? await readOutput<SavingsGrowth>(g, "models.savings_growth", {
          columns: GROWTH_COLUMNS, where: "start_month = ?", params: [pathStart], orderBy: "horizon_years, instrument, basis",
        })
      : [];
    return { rates, through, summary, pathStart: path.length ? pathStart : null, path };
  });
}

/** One start month and number of years, for the calculator: every instrument and basis. */
export async function savingsGrowth(viewer: Viewer, start: string, years: number): Promise<Result<SavingsGrowth[]>> {
  return withModel(viewer, MODEL, (g) =>
    readOutput<SavingsGrowth>(g, "models.savings_growth", {
      columns: GROWTH_COLUMNS, where: "start_month = ? and horizon_years = ?", params: [start, years], orderBy: "instrument, basis",
    }),
  );
}
