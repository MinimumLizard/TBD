// CSE pages' data. Each function authorises one model and reads only through lib/db.ts.
import "server-only";

import type { Viewer } from "../entitlements";
import { readOutput } from "../db";
import { type Result, cappedDate, withModel } from "./common";

export interface MarketSession {
  session_date: string;
  turnover: number | null;
  turnover_avg20: number | null;
  volume: number | null;
  volume_avg20: number | null;
  trades: number | null;
  trades_avg20: number | null;
  sessions_needed: number | null;
  foreign_buy: number | null;
  foreign_sell: number | null;
  foreign_net: number | null;
  per: number | null;
  pbv: number | null;
  dy: number | null;
  market_cap: number | null;
  listed: number | null;
  traded_all: number | null;
  equities_up: number;
  equities_down: number;
  equities_flat: number;
  equities_traded: number;
}
export interface IndexSession {
  session_date: string;
  index_code: string;
  value: number;
  change: number | null;
  pct: number | null;
}
export interface ShareSession {
  session_date: string;
  symbol: string;
  traded: boolean;
  close: number | null;
  change: number | null;
  pct: number | null;
  turnover: number | null;
  volume: number | null;
  market_cap: number | null;
  low_52w: number | null;
  high_52w: number | null;
  range_pos: number | null;
  range_flag: boolean;
  vol_ratio: number | null;
  vol_avg20: number | null;
  rel_1w: number | null;
  rel_1m: number | null;
  rel_3m: number | null;
  ret_1w: number | null;
  ret_1m: number | null;
  ret_3m: number | null;
  flag_1w: string | null;
  flag_1m: string | null;
  flag_3m: string | null;
  beta: number | null;
}

async function latestSession(granted: Parameters<typeof readOutput>[0], table: string, onOrBefore?: string): Promise<string | null> {
  const rows = await readOutput<{ session_date: string }>(granted, table, {
    columns: ["session_date"],
    where: onOrBefore ? "session_date <= ?" : undefined,
    params: onOrBefore ? [onOrBefore] : [],
    orderBy: "session_date desc",
    limit: 1,
  });
  return rows[0]?.session_date ?? null;
}

export async function marketTape(viewer: Viewer, date?: string): Promise<Result<{ session: MarketSession | null; indices: IndexSession[] }>> {
  return withModel(viewer, "cse_market_tape", async (g) => {
    const day = await latestSession(g, "models.cse_market_session", cappedDate(g, date));
    if (!day) return { session: null, indices: [] };
    const [session] = await readOutput<MarketSession>(g, "models.cse_market_session", { where: "session_date = ?", params: [day] });
    const indices = await readOutput<IndexSession>(g, "models.cse_index_session", { where: "session_date = ?", params: [day], orderBy: "index_code" });
    return { session: session ?? null, indices };
  });
}

export async function indexHistory(viewer: Viewer, indexCode: string): Promise<Result<IndexSession[]>> {
  return withModel(viewer, "cse_market_tape", (g) =>
    readOutput<IndexSession>(g, "models.cse_index_session", { where: "index_code = ?", params: [indexCode], orderBy: "session_date" }),
  );
}

export async function shares(viewer: Viewer, date?: string): Promise<Result<{ date: string | null; rows: ShareSession[] }>> {
  return withModel(viewer, "cse_security_metrics", async (g) => {
    const day = await latestSession(g, "models.cse_security_session", cappedDate(g, date));
    const rows = day ? await readOutput<ShareSession>(g, "models.cse_security_session", { where: "session_date = ?", params: [day], orderBy: "symbol" }) : [];
    return { date: day, rows };
  });
}

export async function shareHistory(viewer: Viewer, symbol: string): Promise<Result<ShareSession[]>> {
  return withModel(viewer, "cse_security_metrics", (g) =>
    readOutput<ShareSession>(g, "models.cse_security_session", { where: "symbol = ?", params: [symbol], orderBy: "session_date" }),
  );
}
