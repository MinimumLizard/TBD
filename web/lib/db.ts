// Reads model outputs, and (one write) passes visitors' feedback to the database's checked submit function. The
// only module that talks to the database.
//
// readOutput() takes a `Granted` access from lib/entitlements.ts, so a caller cannot read a model it was not
// authorised for. It reads only that model's own output tables, never one listed as unpublished, only the current
// method version, (for a free preview) only rows dated on or before the preview date, and (for a recent window)
// only rows dated on or after the window's first day.
import "server-only";

import { Pool, type PoolConfig, types } from "pg";

import { type Granted, isGrant } from "./entitlements";
import type { FeedbackInput, Outcome } from "./feedback";
import { registry } from "./registry";

types.setTypeParser(1082, (v: string) => v); // date -> "YYYY-MM-DD", never shifted by a time zone
types.setTypeParser(20, (v: string) => Number(v)); // bigint -> number (rupee amounts fit exactly below 2^53)

let pool: Pool | null = null;

// Settings for a site that runs as many short-lived serverless functions (Vercel) against Supabase's connection
// pooler: few connections each, short timeouts so a database problem fails fast instead of hanging a request, and
// an encrypted connection that verifies the server (DATABASE_CA_CERT: Supabase's certificate, PEM text).
export function poolConfig(env: NodeJS.ProcessEnv = process.env): PoolConfig {
  const connectionString = env.DATABASE_URL;
  if (!connectionString) throw new Error("DATABASE_URL is not set (see .env.example)");
  const host = new URL(connectionString.replace(/^postgres(ql)?:/, "http:")).hostname;
  const local = host === "localhost" || host === "127.0.0.1" || host === "::1";
  const config: PoolConfig = {
    connectionString,
    max: Number(env.DATABASE_POOL_MAX ?? 3),
    connectionTimeoutMillis: 5_000,
    idleTimeoutMillis: 10_000,
    query_timeout: 15_000,
  };
  if (env.DATABASE_CA_CERT) config.ssl = { ca: env.DATABASE_CA_CERT, rejectUnauthorized: true };
  else if (!local) throw new Error("DATABASE_CA_CERT is not set: a remote database is only used over a verified TLS connection");
  return config;
}

function getPool(): Pool {
  if (!pool) pool = new Pool(poolConfig());
  return pool;
}

const IDENT = /^[a-z_][a-z0-9_]*$/;

// The date column of each output table; a table with none cannot be served as a free preview.
const DATE_COLUMN: Record<string, string | null> = {
  "models.bond_reference": null,
  "models.cse_market_session": "session_date",
  "models.cse_index_session": "session_date",
  "models.cse_security_session": "session_date",
  "models.cse_security_reference": null,
  "models.savings_rates": "month",
  "models.savings_growth": "start_month",
  "models.savings_summary": null,
};

export function dateColumn(table: string): string | null {
  if (table in DATE_COLUMN) return DATE_COLUMN[table];
  return table.startsWith("models.bond_") ? "obs_date" : null;
}

export interface ReadOptions {
  columns?: string[];
  where?: string; // with ? placeholders, filled from params in order
  params?: unknown[];
  orderBy?: string;
  limit?: number;
}

export function buildQuery(access: Granted, table: string, opts: ReadOptions = {}): { text: string; values: unknown[] } {
  if (!isGrant(access)) throw new Error("not a grant issued by authorize()");
  const entry = registry.models[access.model];
  if (!entry.outputs.includes(table)) throw new Error(`${table} is not an output of ${access.model}`);
  if (registry.unpublished_outputs.includes(table)) throw new Error(`${table} is not published`);
  const columns = opts.columns ?? ["*"];
  for (const c of columns) if (c !== "*" && !IDENT.test(c)) throw new Error(`bad column ${c}`);
  const values: unknown[] = [access.version];
  const clauses = ["method_version = $1"];
  if (access.maxDate) {
    const column = dateColumn(table);
    if (!column) throw new Error(`${table} has no date, so it cannot be served as a delayed preview`);
    values.push(access.maxDate);
    clauses.push(`${column} <= $${values.length}`);
  }
  if (access.minDate) {
    const column = dateColumn(table);
    if (!column) throw new Error(`${table} has no date, so it cannot be served as a recent window`);
    values.push(access.minDate);
    clauses.push(`${column} >= $${values.length}`);
  }
  if (opts.where) {
    let i = 0;
    const params = opts.params ?? [];
    const sql = opts.where.replace(/\?/g, () => {
      if (i >= params.length) throw new Error("too few params");
      values.push(params[i++]);
      return `$${values.length}`;
    });
    if (i !== params.length) throw new Error("too many params");
    clauses.push(`(${sql})`);
  }
  let text = `select ${columns.join(", ")} from ${table} where ${clauses.join(" and ")}`;
  if (opts.orderBy) {
    const parts = opts.orderBy.split(",").map((p) => p.replace(/^\s+|\s+$/g, ""));
    if (!parts.every((p) => /^[a-z_][a-z0-9_]*( (asc|desc))?$/i.test(p))) throw new Error("bad order by");
    text += ` order by ${parts.join(", ")}`;
  }
  if (opts.limit !== undefined) text += ` limit ${Math.max(0, Math.floor(opts.limit))}`;
  return { text, values };
}

export async function readOutput<T = Record<string, unknown>>(access: Granted, table: string, opts: ReadOptions = {}): Promise<T[]> {
  const { text, values } = buildQuery(access, table, opts);
  const result = await getPool().query(text, values);
  return result.rows as T[];
}

// The website's only write. Its database role cannot read or change the feedback table; it can only call this
// function, which checks every field again and limits how often one sender can write (migration 0012).
export async function submitFeedback(input: FeedbackInput, viewerTier: string, senderKey: string): Promise<Outcome> {
  const vote = input.kind === "page_vote";
  const result = await getPool().query("select community.submit_feedback($1, $2, $3, $4, $5, $6, $7) as r", [
    input.page, input.kind, vote ? input.useful : null, vote ? null : input.topic, vote ? null : input.message,
    viewerTier, senderKey,
  ]);
  const r = result.rows[0]?.r;
  return r === "ok" || r === "limited" ? r : "invalid";
}
