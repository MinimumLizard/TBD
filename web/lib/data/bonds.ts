// Bond pages' data. Each function authorises one model and reads only through lib/db.ts.
import "server-only";

import type { Viewer } from "../entitlements";
import { readOutput } from "../db";
import { type Result, cappedDate, withModel } from "./common";

export interface BondRef {
  isin: string;
  coupon_pct: number | null;
  maturity_date: string | null;
  series_label: string | null;
  notes: string | null;
}
export interface Quote {
  obs_date: string;
  isin: string;
  bid_yield: number | null;
  offer_yield: number | null;
  mid_yield: number | null;
  bid_price: number | null;
  offer_price: number | null;
  resolved_by: string;
}
export interface CurveFit {
  obs_date: string;
  beta0: number;
  beta1: number;
  beta2: number;
  lambda_years: number;
  n_quotes: number;
  rmse_bp: number;
  n_trades: number;
  trade_rmse_bp: number | null;
  trade_bias_bp: number | null;
}
export interface CurvePoint {
  obs_date: string;
  isin: string;
  source: "quote" | "trade";
  tau_years: number;
  observed_yield: number;
  fitted_yield: number;
  residual_bp: number;
  weight: number | null;
}
export interface Liquidity {
  obs_date: string;
  isin: string;
  turnover_lkr: number;
  n_trades: number;
  days_traded: number;
  is_benchmark: boolean;
  last_auction: string | null;
  days_since_auction: number | null;
  post_auction: boolean;
  bid_to_cover: number | null;
  tier: "core" | "active" | "wider";
  last_trade_date: string | null;
  last_trade_yield: number | null;
  trades_through: string;
}
export interface ResidualZ {
  obs_date: string;
  isin: string;
  residual_bp: number;
  mean_bp: number;
  sd_bp: number;
  deviation_bp: number;
  zscore: number;
  n_window: number;
}
export interface PairZ {
  obs_date: string;
  isin_a: string;
  isin_b: string;
  tau_a: number;
  tau_b: number;
  spread_bp: number;
  mean_bp: number;
  sd_bp: number;
  deviation_bp: number;
  zscore: number;
  n_window: number;
}
export interface Gap {
  obs_date: string;
  gap_bp: number;
  n: number;
  window_days: number;
}
export interface Funding {
  obs_date: string;
  bill_pct: number;
  rate_pct: number;
  spread_bp: number;
  bill_as_of: string;
  stale_days: number;
  n_bills: number;
}
export interface Carry {
  obs_date: string;
  isin: string;
  entry_gap_bp: number;
  entry_yield: number;
  price: number;
  duration: number;
  carry_bp: number;
  roll_bp: number;
  total_bp: number;
  per_duration_bp: number;
  convexity: number | null;
}

async function latestDate(granted: Parameters<typeof readOutput>[0], table: string, onOrBefore?: string): Promise<string | null> {
  const rows = await readOutput<{ obs_date: string }>(granted, table, {
    columns: ["obs_date"],
    where: onOrBefore ? "obs_date <= ?" : undefined,
    params: onOrBefore ? [onOrBefore] : [],
    orderBy: "obs_date desc",
    limit: 1,
  });
  return rows[0]?.obs_date ?? null;
}

export async function bondReference(viewer: Viewer): Promise<Result<Map<string, BondRef>>> {
  return withModel(viewer, "bond_identity", async (g) => {
    const rows = await readOutput<BondRef>(g, "models.bond_reference", {
      columns: ["isin", "coupon_pct", "maturity_date", "series_label", "notes"],
    });
    return new Map(rows.map((r) => [r.isin, r]));
  });
}

export async function bondQuotes(viewer: Viewer, date?: string): Promise<Result<{ date: string | null; quotes: Quote[] }>> {
  return withModel(viewer, "bond_identity", async (g) => {
    const day = await latestDate(g, "models.bond_quotes", cappedDate(g, date));
    const quotes = day ? await readOutput<Quote>(g, "models.bond_quotes", { where: "obs_date = ?", params: [day], orderBy: "isin" }) : [];
    return { date: day, quotes };
  });
}

export async function bondQuoteHistory(viewer: Viewer, isin: string): Promise<Result<Quote[]>> {
  return withModel(viewer, "bond_identity", (g) =>
    readOutput<Quote>(g, "models.bond_quotes", { where: "isin = ?", params: [isin], orderBy: "obs_date" }),
  );
}

export async function bondCurve(viewer: Viewer, date?: string): Promise<Result<{ fit: CurveFit | null; points: CurvePoint[] }>> {
  return withModel(viewer, "bond_ns_curve", async (g) => {
    const day = await latestDate(g, "models.bond_curve_fit", cappedDate(g, date));
    if (!day) return { fit: null, points: [] };
    const [fit] = await readOutput<CurveFit>(g, "models.bond_curve_fit", { where: "obs_date = ?", params: [day] });
    const points = await readOutput<CurvePoint>(g, "models.bond_curve_point", { where: "obs_date = ?", params: [day], orderBy: "tau_years" });
    return { fit: fit ?? null, points };
  });
}

export async function bondCurveHistory(viewer: Viewer): Promise<Result<CurveFit[]>> {
  return withModel(viewer, "bond_ns_curve", (g) => readOutput<CurveFit>(g, "models.bond_curve_fit", { orderBy: "obs_date" }));
}

export async function bondResidualHistory(viewer: Viewer, isin: string): Promise<Result<CurvePoint[]>> {
  return withModel(viewer, "bond_ns_curve", (g) =>
    readOutput<CurvePoint>(g, "models.bond_curve_point", { where: "isin = ? and source = 'quote'", params: [isin], orderBy: "obs_date" }),
  );
}

export async function bondLiquidity(viewer: Viewer, date?: string): Promise<Result<{ date: string | null; rows: Liquidity[] }>> {
  return withModel(viewer, "bond_liquidity", async (g) => {
    const day = await latestDate(g, "models.bond_liquidity", cappedDate(g, date));
    const rows = day ? await readOutput<Liquidity>(g, "models.bond_liquidity", { where: "obs_date = ?", params: [day], orderBy: "isin" }) : [];
    return { date: day, rows };
  });
}

export async function bondZscores(viewer: Viewer, date?: string): Promise<Result<{ date: string | null; bonds: ResidualZ[]; pairs: PairZ[] }>> {
  return withModel(viewer, "bond_rv_zscores", async (g) => {
    const day = await latestDate(g, "models.bond_residual_zscore", cappedDate(g, date));
    if (!day) return { date: null, bonds: [], pairs: [] };
    const bonds = await readOutput<ResidualZ>(g, "models.bond_residual_zscore", { where: "obs_date = ?", params: [day], orderBy: "isin" });
    const pairs = await readOutput<PairZ>(g, "models.bond_pair_zscore", { where: "obs_date = ?", params: [day], orderBy: "isin_a, isin_b" });
    return { date: day, bonds, pairs };
  });
}

export async function executionGap(viewer: Viewer): Promise<Result<Gap[]>> {
  return withModel(viewer, "bond_execution_gap", (g) => readOutput<Gap>(g, "models.bond_execution_gap", { orderBy: "obs_date" }));
}

export async function bondCarry(viewer: Viewer, date?: string): Promise<Result<{ date: string | null; funding: Funding | null; rows: Carry[] }>> {
  return withModel(viewer, "bond_carry", async (g) => {
    const day = await latestDate(g, "models.bond_carry", cappedDate(g, date));
    if (!day) return { date: null, funding: null, rows: [] };
    const [funding] = await readOutput<Funding>(g, "models.bond_funding", { where: "obs_date = ?", params: [day] });
    const rows = await readOutput<Carry>(g, "models.bond_carry", { where: "obs_date = ?", params: [day], orderBy: "isin" });
    return { date: day, funding: funding ?? null, rows };
  });
}

// One bond's own analysis, each part under its own model's tier rule.

export async function bondTradeHistory(viewer: Viewer, isin: string): Promise<Result<CurvePoint[]>> {
  return withModel(viewer, "bond_ns_curve", (g) =>
    readOutput<CurvePoint>(g, "models.bond_curve_point", { where: "isin = ? and source = 'trade'", params: [isin], orderBy: "obs_date" }),
  );
}

export async function bondZHistory(viewer: Viewer, isin: string): Promise<Result<ResidualZ[]>> {
  return withModel(viewer, "bond_rv_zscores", (g) =>
    readOutput<ResidualZ>(g, "models.bond_residual_zscore", { where: "isin = ?", params: [isin], orderBy: "obs_date" }),
  );
}

export async function bondCarryHistory(viewer: Viewer, isin: string): Promise<Result<Carry[]>> {
  return withModel(viewer, "bond_carry", (g) =>
    readOutput<Carry>(g, "models.bond_carry", { where: "isin = ?", params: [isin], orderBy: "obs_date" }),
  );
}
