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

/** Market sessions after `after` (exclusive), oldest first: a week's turnover and foreign flows. */
export async function marketSessionsSince(viewer: Viewer, after: string): Promise<Result<MarketSession[]>> {
  return withModel(viewer, "cse_market_tape", (g) =>
    readOutput<MarketSession>(g, "models.cse_market_session", { where: "session_date > ?", params: [after], orderBy: "session_date" }),
  );
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

export interface SecurityRef {
  symbol: string;
  name: string | null;
  sector_label: string | null;
  last_session: string | null;
}

/** Each share's company name and the CSE's sector label (display facts published by cse_security_metrics). */
export async function securityNames(viewer: Viewer): Promise<Result<Map<string, SecurityRef>>> {
  return withModel(viewer, "cse_security_metrics", async (g) => {
    const rows = await readOutput<SecurityRef>(g, "models.cse_security_reference", { orderBy: "symbol" });
    return new Map(rows.map((r) => [r.symbol, r]));
  });
}

export interface CorporateAction {
  action_id: string;
  symbol: string;
  action_type: string; // cash_dividend | subdivision | scrip | rights
  ex_date: string | null;
  amount_per_share: number | null;
  ratio_new: number | null;
  ratio_held: number | null;
  factor: number | null;
  subscription_price: number | null;
  source_url: string;
  announced_date: string | null;
  confirmed: boolean; // true: in use for total returns; false: awaiting confirmation, not used
}

const ACTION_COLUMNS = ["action_id", "symbol", "action_type", "ex_date", "amount_per_share", "ratio_new", "ratio_held",
  "factor", "subscription_price", "source_url", "announced_date"];

/** A share's corporate actions: those in use (confirmed, with the owner's corrections applied) and those awaiting
 * confirmation, newest first. Rejected, superseded and replaced rows are not shown. */
export async function corporateActions(viewer: Viewer, symbol: string): Promise<Result<CorporateAction[]>> {
  return withModel(viewer, "cse_corporate_actions", async (g) => {
    const [used, awaiting] = await Promise.all([
      readOutput<Omit<CorporateAction, "confirmed">>(g, "models.cse_corporate_action_used", { columns: ACTION_COLUMNS, where: "symbol = ?", params: [symbol] }),
      readOutput<Omit<CorporateAction, "confirmed">>(g, "models.cse_corporate_action", {
        columns: ACTION_COLUMNS, where: "symbol = ? and use_status = ?", params: [symbol, "awaiting_confirmation"],
      }),
    ]);
    const rows = [...used.map((r) => ({ ...r, confirmed: true })), ...awaiting.map((r) => ({ ...r, confirmed: false }))];
    const key = (r: CorporateAction) => r.ex_date ?? r.announced_date ?? "";
    return rows.sort((a, b) => key(b).localeCompare(key(a)) || a.action_id.localeCompare(b.action_id));
  });
}

export interface TotalReturnSession {
  session_date: string;
  close: number;
  price_return: number | null;
  total_return: number | null;
  tri: number;
  tr_1w: number | null;
  tr_1m: number | null;
  tr_3m: number | null;
  events: string;
}

/** A share's total return for every session it traded in, oldest first. */
export async function totalReturns(viewer: Viewer, symbol: string): Promise<Result<TotalReturnSession[]>> {
  return withModel(viewer, "cse_total_returns", (g) =>
    readOutput<TotalReturnSession>(g, "models.cse_total_return", {
      columns: ["session_date", "close", "price_return", "total_return", "tri", "tr_1w", "tr_1m", "tr_3m", "events"],
      where: "symbol = ?", params: [symbol], orderBy: "session_date",
    }),
  );
}

export interface CompanyFigures {
  session_date: string;
  code: string;
  price: number | null;
  price_date: string | null;
  shares: number | null;
  fye: string;
  nav: number | null;
  nav_period: string | null;
  pb: number | null;
  ttm_profit: number | null;
  ttm_eps: number | null;
  ttm_to: string | null;
  ttm_note: string;
  pe: number | null;
  roe: number | null;
  div_ttm: number | null;
  dy: number | null;
  report_period: string | null;
  report_url: string | null;
}

const FIGURE_COLUMNS = ["session_date", "code", "price", "price_date", "shares", "fye", "nav", "nav_period", "pb",
  "ttm_profit", "ttm_eps", "ttm_to", "ttm_note", "pe", "roe", "div_ttm", "dy", "report_period", "report_url"];

/** A company's figures at the latest session (company code, e.g. JKH). */
export async function companyFigures(viewer: Viewer, code: string): Promise<Result<CompanyFigures | null>> {
  return withModel(viewer, "cse_fundamentals", async (g) => {
    const rows = await readOutput<CompanyFigures>(g, "models.cse_fundamentals", {
      columns: FIGURE_COLUMNS, where: "code = ?", params: [code], orderBy: "session_date desc", limit: 1,
    });
    return rows[0] ?? null;
  });
}

export type CompanyRatios = Pick<CompanyFigures, "pe" | "pb" | "dy" | "ttm_eps">;

/** Every company's P/E, P/B and dividend yield at the latest session, by company code. */
export async function ratiosByCompany(viewer: Viewer): Promise<Result<{ date: string | null; byCode: Map<string, CompanyRatios> }>> {
  return withModel(viewer, "cse_fundamentals", async (g) => {
    const day = await latestSession(g, "models.cse_fundamentals");
    const rows = day
      ? await readOutput<CompanyRatios & { code: string }>(g, "models.cse_fundamentals", {
          columns: ["code", "pe", "pb", "dy", "ttm_eps"], where: "session_date = ?", params: [day],
        })
      : [];
    return { date: day, byCode: new Map(rows.map((r) => [r.code, { pe: r.pe, pb: r.pb, dy: r.dy, ttm_eps: r.ttm_eps }])) };
  });
}

export interface CompanyOwnership {
  session_date: string;
  code: string;
  period_date: string | null;
  report_status: string;
  table_status: string | null;
  top20_pct: number | null;
  pct_listed: number | null;
  pct_company: number | null;
  pct_institution: number | null;
  pct_individual: number | null;
  pct_joint: number | null;
  pct_estate: number | null;
  pct_trust: number | null;
  pct_nominee: number | null;
  pct_own_shares: number | null;
  controller_type: string | null;
  controller_name: string | null;
  control_pct: number | null;
  control_level: string | null;
  group_id: string;
  group_head_type: string | null;
  group_head_name: string | null;
  group_size: number;
  free_float_pct: number | null;
  source_url: string | null;
  group_members: string[]; // the other companies in the group (codes), at the same session
}

// Company-level columns only. The tables that name individuals are unpublished: lib/db.ts refuses them, and the
// website's database login has no grant on them.
const OWNERSHIP_COLUMNS = ["session_date", "code", "period_date", "report_status", "table_status", "top20_pct",
  "pct_listed", "pct_company", "pct_institution", "pct_individual", "pct_joint", "pct_estate", "pct_trust",
  "pct_nominee", "pct_own_shares", "controller_type", "controller_name", "control_pct", "control_level", "group_id",
  "group_head_type", "group_head_name", "group_size", "free_float_pct", "source_url"];

/** A company's ownership at the latest session, with the other members of its ownership group. */
export async function companyOwnership(viewer: Viewer, code: string): Promise<Result<CompanyOwnership | null>> {
  return withModel(viewer, "cse_ownership", async (g) => {
    const [row] = await readOutput<Omit<CompanyOwnership, "group_members">>(g, "models.cse_company_ownership", {
      columns: OWNERSHIP_COLUMNS, where: "code = ?", params: [code], orderBy: "session_date desc", limit: 1,
    });
    if (!row) return null;
    const members = row.group_size > 1
      ? await readOutput<{ code: string }>(g, "models.cse_company_ownership", {
          columns: ["code"], where: "session_date = ? and group_id = ? and code <> ?",
          params: [row.session_date, row.group_id, code], orderBy: "code",
        })
      : [];
    return { ...row, group_members: members.map((m) => m.code) };
  });
}
