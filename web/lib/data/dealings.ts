// Directors' share dealings (cse_dealings, free) and money flows (cse_flows, Plus with a delayed free preview).
// Names as the companies filed them are shown (the owner's decision, decision 0021): each dealing carries its
// director, account and the CSE's notice, read through the same model's grant as the dealing itself.
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
  director?: string | null; // as filed with the CSE
  account?: string | null; // the account that dealt, as filed (the director, or a related party)
  source_url?: string | null; // the notice on the CSE's site
}

export interface AsFiled {
  transaction_id: string;
  director: string;
  account: string;
  source_url: string;
}

async function asFiled(g: Parameters<typeof readOutput>[0], ids: string[]): Promise<Map<string, AsFiled>> {
  if (ids.length === 0) return new Map();
  const rows = await readOutput<AsFiled>(g, "models.cse_dealing_as_filed", {
    columns: ["transaction_id", "director", "account", "source_url"], where: "transaction_id = any(?)", params: [ids],
  });
  return new Map(rows.map((r) => [r.transaction_id, r]));
}

async function named(g: Parameters<typeof readOutput>[0], rows: Dealing[]): Promise<Dealing[]> {
  const names = await asFiled(g, rows.map((r) => r.transaction_id));
  return rows.map((r) => {
    const n = names.get(r.transaction_id);
    return { ...r, director: n?.director ?? null, account: n?.account ?? null, source_url: n?.source_url ?? null };
  });
}

const DEALING_COLUMNS = ["transaction_id", "symbol", "company", "role", "account_type", "deal_date", "side", "quantity",
  "price", "value", "announced_date", "lag_days"];
const NEWEST_FIRST = "deal_date desc, announced_date desc, announcement_id desc, line_no";

/** The most recent counted transactions market-wide (re-filed notices left out), newest first. */
export async function recentDealings(viewer: Viewer, limit = 60): Promise<Result<Dealing[]>> {
  return withModel(viewer, "cse_dealings", async (g) =>
    named(g, await readOutput<Dealing>(g, "models.cse_dealing", {
      columns: DEALING_COLUMNS, where: "superseded_by is null and deal_date is not null", orderBy: NEWEST_FIRST, limit,
    })),
  );
}

/** One company's counted transactions, newest first. `code` is the company code ("AAA"), or a share ("AAA.N0000"). */
export async function companyDealings(viewer: Viewer, code: string): Promise<Result<Dealing[]>> {
  return withModel(viewer, "cse_dealings", async (g) =>
    named(g, await readOutput<Dealing>(g, "models.cse_dealing", {
      columns: DEALING_COLUMNS, where: "symbol = ? and superseded_by is null", params: [companyCode(code)],
      orderBy: NEWEST_FIRST,
    })),
  );
}

/** The director, account and notice of dealings shown elsewhere (the large dealings of the money flows). */
export async function dealingNames(viewer: Viewer, ids: string[]): Promise<Result<Map<string, AsFiled>>> {
  return withModel(viewer, "cse_dealings", (g) => asFiled(g, ids));
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
  accounts: FlowAccount[]; // the accounts that dealt in the window, largest total value first
}

export interface FlowAccount {
  actor_key: string;
  actor: string; // as filed: a person, a company or a fund
  actor_type: string;
  purchase_value: number;
  disposal_value: number;
  net_value: number;
  n_transactions: number;
  companies: string; // JSON: [[code, net value], ...]
}

const SHOWN_ACCOUNTS = 20;

const gross = (c: { purchase_value: number; disposal_value: number }) => c.purchase_value + c.disposal_value;

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
    if (!summary) return { summary: null, first_date: null, window, companies: [], large: [], names: {}, accounts: [] };
    const [first] = await readOutput<{ as_of: string }>(g, "models.cse_flow_summary", { columns: ["as_of"], orderBy: "as_of", limit: 1 });
    const columns = ["symbol", "company", "purchase_value", "disposal_value", "net_value", "n_purchasers", "n_disposers",
      "n_transactions", "cluster"];
    const [companies, year, large, accounts] = await Promise.all([
      readOutput<FlowCompany>(g, "models.cse_flow_company", { columns, where: "as_of = ? and window_days = ?", params: [summary.as_of, window] }),
      readOutput<{ symbol: string; company: string }>(g, "models.cse_flow_company", {
        columns: ["symbol", "company"], where: "as_of = ? and window_days = ?", params: [summary.as_of, 365],
      }),
      readOutput<LargeDealing>(g, "models.cse_flow_dealing", {
        columns: ["transaction_id", "symbol", "deal_date", "side", "value", "actor_type", "related_account"],
        where: "large and side <> ? and deal_date > ? and deal_date <= ?", params: ["other", addDays(summary.as_of, -30), summary.as_of],
        orderBy: "deal_date desc, transaction_id",
      }),
      readOutput<FlowAccount>(g, "models.cse_flow_actor", {
        columns: ["actor_key", "actor", "actor_type", "purchase_value", "disposal_value", "net_value", "n_transactions", "companies"],
        where: "as_of = ? and window_days = ?", params: [summary.as_of, window],
      }),
    ]);
    accounts.sort((a, b) => gross(b) - gross(a) || a.actor.localeCompare(b.actor));
    companies.sort((a, b) => gross(b) - gross(a) || a.symbol.localeCompare(b.symbol));
    const names = Object.fromEntries(year.map((r) => [r.symbol, r.company]));
    return { summary, first_date: first?.as_of ?? null, window, companies, large, names, accounts: accounts.slice(0, SHOWN_ACCOUNTS) };
  });
}
