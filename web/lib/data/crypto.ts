// Crypto pages' data. Each function authorises one model and reads only through lib/db.ts.
import "server-only";

import type { Viewer } from "../entitlements";
import { readOutput } from "../db";
import { addDays } from "../time";
import { type Result, cappedDate, withModel } from "./common";

export interface MarketDay {
  pair: string;
  day: string;
  close: number;
  ret_1d: number | null;
  ret_7d: number | null;
  ret_30d: number | null;
  ret_1y: number | null;
  ath_close: number;
  ath_day: string;
  drawdown: number;
  days_since_ath: number;
  vol_30d: number | null;
  vol_90d: number | null;
}

export interface CycleDay {
  pair: string;
  day: string;
  close: number;
  sma_50: number | null;
  sma_200: number | null;
  mayer: number | null;
  sma_200w: number | null;
  sma_200w_chg_4w: number | null;
  sma_20w: number | null;
  ema_21w: number | null;
  dist_20w: number | null;
  pi_sma_111: number | null;
  pi_sma_350x2: number | null;
  pi_ema_150: number | null;
  pi_sma_471x0745: number | null;
  last_halving: string | null;
  days_since_halving: number | null;
  roi_since_halving: number | null;
  ret_mtd: number | null;
}

export interface CycleEvent {
  pair: string;
  day: string;
  kind: "pi_top_cross" | "pi_bottom_cross";
  close: number;
}

export interface CycleAnchor {
  pair: string;
  day: string;
  kind: "halving" | "cycle_peak" | "cycle_low";
  epoch: number;
  anchor_day: string;
  anchor_close: number;
  roi: number;
  days_since: number;
  change_from_prior: number | null;
  days_from_prior: number | null;
  provisional: boolean;
}

export interface CycleMonth {
  pair: string;
  month: string;
  day: string;
  close: number;
  ret_month: number | null;
}

export interface TrendDay {
  pair: string;
  day: string;
  fit: "log_regression" | "power_law";
  intercept: number;
  slope: number;
  n_obs: number;
  resid_sd: number;
  close: number;
  fitted: number;
  lower_1: number;
  upper_1: number;
  lower_2: number;
  upper_2: number;
  position: number;
}

type Grant = Parameters<typeof readOutput>[0];

async function latestDay(granted: Grant, table: string, pair: string | null, onOrBefore?: string): Promise<string | null> {
  const where = [pair ? "pair = ?" : null, onOrBefore ? "day <= ?" : null].filter(Boolean).join(" and ");
  const rows = await readOutput<{ day: string }>(granted, table, {
    columns: ["day"],
    where: where || undefined,
    params: [...(pair ? [pair] : []), ...(onOrBefore ? [onOrBefore] : [])],
    orderBy: "day desc",
    limit: 1,
  });
  return rows[0]?.day ?? null;
}

/** Every pair's latest day (on or before `date`), and its last 90 closes for a trend line. */
export async function cryptoOverview(viewer: Viewer, date?: string): Promise<Result<{ day: string | null; latest: MarketDay[]; recent: Record<string, number[]> }>> {
  return withModel(viewer, "crypto_market", async (g) => {
    const day = await latestDay(g, "models.crypto_market_daily", null, cappedDate(g, date));
    if (!day) return { day: null, latest: [], recent: {} };
    const rows = await readOutput<MarketDay>(g, "models.crypto_market_daily", {
      where: "day > ? and day <= ?", params: [addDays(day, -90), day], orderBy: "pair, day",
    });
    const recent: Record<string, number[]> = {};
    const last: Record<string, MarketDay> = {};
    for (const r of rows) {
      (recent[r.pair] ??= []).push(r.close);
      last[r.pair] = r;
    }
    return { day, latest: Object.values(last), recent };
  });
}

/** One pair's whole history of prices, returns, drawdowns and volatility. */
export async function cryptoHistory(viewer: Viewer, pair: string): Promise<Result<MarketDay[]>> {
  return withModel(viewer, "crypto_market", (g) =>
    readOutput<MarketDay>(g, "models.crypto_market_daily", { where: "pair = ?", params: [pair], orderBy: "day" }),
  );
}

/** One pair's cycle measures: the daily history (or only the latest day), crossing days, the cycle table as known on
 * the latest day, and the completed months. */
export async function cryptoCycle(viewer: Viewer, pair: string, opts: { date?: string; history?: boolean } = {}): Promise<Result<{
  day: string | null; daily: CycleDay[]; events: CycleEvent[]; anchors: CycleAnchor[]; months: CycleMonth[];
}>> {
  return withModel(viewer, "crypto_cycle", async (g) => {
    const day = await latestDay(g, "models.crypto_cycle_daily", pair, cappedDate(g, opts.date));
    if (!day) return { day: null, daily: [], events: [], anchors: [], months: [] };
    const [daily, events, anchors, months] = await Promise.all([
      readOutput<CycleDay>(g, "models.crypto_cycle_daily", opts.history === false
        ? { where: "pair = ? and day = ?", params: [pair, day] }
        : { where: "pair = ? and day <= ?", params: [pair, day], orderBy: "day" }),
      readOutput<CycleEvent>(g, "models.crypto_cycle_event", { where: "pair = ? and day <= ?", params: [pair, day], orderBy: "day" }),
      readOutput<CycleAnchor>(g, "models.crypto_cycle_anchor", { where: "pair = ? and day = ?", params: [pair, day], orderBy: "epoch, anchor_day" }),
      readOutput<CycleMonth>(g, "models.crypto_cycle_monthly", { where: "pair = ? and day <= ?", params: [pair, day], orderBy: "month" }),
    ]);
    return { day, daily, events, anchors, months };
  });
}

/** Bitcoin's two trend fits, every day to the latest (or only the latest day). */
export async function cryptoTrend(viewer: Viewer, pair: string, opts: { date?: string; history?: boolean } = {}): Promise<Result<{ day: string | null; rows: TrendDay[] }>> {
  return withModel(viewer, "crypto_trend_bands", async (g) => {
    const day = await latestDay(g, "models.crypto_trend_band", pair, cappedDate(g, opts.date));
    if (!day) return { day: null, rows: [] };
    const rows = await readOutput<TrendDay>(g, "models.crypto_trend_band", opts.history === false
      ? { where: "pair = ? and day = ?", params: [pair, day], orderBy: "fit" }
      : { where: "pair = ? and day <= ?", params: [pair, day], orderBy: "fit, day" });
    return { day, rows };
  });
}
