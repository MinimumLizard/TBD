// Directors' share dealings (cse_dealings, free) and money flows (cse_flows, Plus with a delayed free preview).
// Only the published tables are read: no output that contains a person's name is ever served (config/entitlements.yaml
// unpublished_outputs; lib/db.ts refuses them, and the database role cannot read them).
import "server-only";

import type { Viewer } from "../entitlements";
import { readOutput } from "../db";
import { type FlowWindow, companyCode } from "../dealings-display";
import { type Result, cappedDate, withModel } from "./common";

export interface Dealing {
  transaction_id: string;
  symbol: string; // the company's code (no share class)
  company: string;
  role: string; // chair | chief_executive | executive | non_executive | independent_non_executive | several | not_stated
  account_type: "own" | "related";
  deal_date: string | null;
  side: "purchase" | "disposal" | "other";
  quantity: number | null;
  price: number | null;
  value: number | null;
  announced_date: string | null;
  lag_days: number | null;
}

const DEALING_COLUMNS = ["transaction_id", "symbol", "company", "role", "account_type", "deal_date", "side", "quantity",
  "price", "value", "announced_date", "lag_days"];
const NEWEST_FIRST = "deal_date desc, announced_date desc, announcement_id desc, line_no";

/** The most recent counted transactions market-wide (re-filed notices left out), newest first. */
export async function recentDealings(viewer: Viewer, limit = 60): Promise<Result<Dealing[]>> {
  return withModel(viewer, "cse_dealings", (g) =>
    readOutput<Dealing>(g, "models.cse_dealing", {
      columns: DEALING_COLUMNS, where: "superseded_by is null and deal_date is not null", orderBy: NEWEST_FIRST, limit,
    }),
  );
}

/** One company's counted transactions, newest first. `code` is the company code ("AAA"), or a share ("AAA.N0000"). */
export async function companyDealings(viewer: Viewer, code: string): Promise<Result<Dealing[]>> {
  return withModel(viewer, "cse_dealings", (g) =>
    readOutput<Dealing>(g, "models.cse_dealing", {
      columns: DEALING_COLUMNS, where: "symbol = ? and superseded_by is null", params: [companyCode(code)],
      orderBy: NEWEST_FIRST,
    }),
  );
}

export interface FlowCompany {
  symbol: string;
  company: string;
  purchase_value: number;
  disposal_value: number;
  net_value: number;
  n_purchasers: number;
  n_disposers: number;
  n_transactions: number;
  cluster: boolean;
}

export interface FlowSummary {
  as_of: string;
  n_dealings: number;
  n_trades: number;
  lag_median: number | null;
}

export interface LargeDealing {
  transaction_id: string;
  symbol: string;
  deal_date: string;
  side: "purchase" | "disposal" | "other";
  value: number | null;
  actor_type: string;
  related_account: boolean;
}

export interface Flows {
  summary: FlowSummary | null;
  first_date: string | null; // the earliest dealing date counted
  window: FlowWindow;
  companies: FlowCompany[]; // largest total value dealt (purchases + disposals) first: activity, not direction
  large: LargeDealing[]; // Rs 10 mn or more, in the 30 days to the date
  names: Record<string, string>; // company code -> name
}

function addDays(iso: string, days: number): string {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

/** The money flows on the latest dealing date the visitor may see (on or before `date`, if given). */
export async function flows(viewer: Viewer, window: FlowWindow = 30, date?: string): Promise<Result<Flows>> {
  return withModel(viewer, "cse_flows", async (g) => {
    const day = cappedDate(g, date);
    const [summary] = await readOutput<FlowSummary>(g, "models.cse_flow_summary", {
      where: day ? "as_of <= ?" : undefined, params: day ? [day] : [], orderBy: "as_of desc", limit: 1,
    });
    if (!summary) return { summary: null, first_date: null, window, companies: [], large: [], names: {} };
    const [first] = await readOutput<{ as_of: string }>(g, "models.cse_flow_summary", { columns: ["as_of"], orderBy: "as_of", limit: 1 });
    const columns = ["symbol", "company", "purchase_value", "disposal_value", "net_value", "n_purchasers", "n_disposers",
      "n_transactions", "cluster"];
    const [companies, year, large] = await Promise.all([
      readOutput<FlowCompany>(g, "models.cse_flow_company", { columns, where: "as_of = ? and window_days = ?", params: [summary.as_of, window] }),
      readOutput<{ symbol: string; company: string }>(g, "models.cse_flow_company", {
        columns: ["symbol", "company"], where: "as_of = ? and window_days = ?", params: [summary.as_of, 365],
      }),
      readOutput<LargeDealing>(g, "models.cse_flow_dealing", {
        columns: ["transaction_id", "symbol", "deal_date", "side", "value", "actor_type", "related_account"],
        where: "large and side <> ? and deal_date > ? and deal_date <= ?", params: ["other", addDays(summary.as_of, -30), summary.as_of],
        orderBy: "deal_date desc, transaction_id",
      }),
    ]);
    const gross = (c: FlowCompany) => c.purchase_value + c.disposal_value;
    companies.sort((a, b) => gross(b) - gross(a) || a.symbol.localeCompare(b.symbol));
    const names = Object.fromEntries(year.map((r) => [r.symbol, r.company]));
    return { summary, first_date: first?.as_of ?? null, window, companies, large, names };
  });
}
