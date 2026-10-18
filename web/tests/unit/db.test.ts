import { describe, expect, test } from "vitest";

import { buildQuery, dateColumn, poolConfig } from "@/lib/db";
import { type Granted, authorize } from "@/lib/entitlements";
import { modelEntry } from "@/lib/registry";

const TODAY = "2026-10-12";
const version = modelEntry("bond_rv_zscores").current_version;
const full = authorize({ id: null, tier: "professional" }, "bond_rv_zscores", TODAY) as Granted;
const preview = authorize({ id: null, tier: "free" }, "bond_rv_zscores", TODAY) as Granted;

describe("buildQuery", () => {
  test("always filters to the granted version", () => {
    const q = buildQuery(full, "models.bond_residual_zscore", { where: "obs_date = ?", params: ["2026-10-09"], orderBy: "isin" });
    expect(q.text).toBe("select * from models.bond_residual_zscore where method_version = $1 and (obs_date = $2) order by isin");
    expect(q.values).toEqual([version, "2026-10-09"]);
  });

  test("a preview can never read past its date", () => {
    expect(preview.maxDate).toBe("2026-10-07");
    const q = buildQuery(preview, "models.bond_residual_zscore", { where: "obs_date = ?", params: ["2026-10-09"] });
    expect(q.text).toContain("obs_date <= $2");
    expect(q.values).toEqual([version, "2026-10-07", "2026-10-09"]);
  });

  test("a recent window can never read before its first day", () => {
    const recent = authorize({ id: null, tier: "free" }, "bond_ns_curve", TODAY) as Granted;
    const q = buildQuery(recent, "models.bond_curve_point", { where: "isin = ?", params: ["LKB01"] });
    expect(q.text).toContain("obs_date >= $2");
    expect(q.values).toEqual([modelEntry("bond_ns_curve").current_version, "2026-09-12", "LKB01"]);
    const plus = authorize({ id: null, tier: "plus" }, "bond_ns_curve", TODAY) as Granted;
    expect(buildQuery(plus, "models.bond_curve_point").text).not.toContain(">=");
  });

  test("a grant cannot be made up: only authorize() issues them", () => {
    const forged = { allowed: true, model: "bond_carry", version: "1.1.0", maxDate: null, delayDays: 0, minDate: null, fullHistoryTier: null } as Granted;
    expect(() => buildQuery(forged, "models.bond_carry")).toThrow(/not a grant/);
    expect(() => buildQuery({ ...full }, "models.bond_residual_zscore")).toThrow(/not a grant/);
    expect(Object.isFrozen(full)).toBe(true);
  });

  test("a model can read only its own outputs, never an unpublished one", () => {
    expect(() => buildQuery(full, "models.bond_carry")).toThrow(/not an output/);
    expect(() => buildQuery(full, "models.model_stats")).toThrow(/not published/);
    const identity = authorize({ id: null, tier: "free" }, "bond_identity", TODAY) as Granted;
    expect(() => buildQuery(identity, "models.bond_quotes; drop table x")).toThrow();
  });

  test("tables without dates are known, so they can never be served as a preview", () => {
    expect(dateColumn("models.bond_reference")).toBeNull();
    expect(dateColumn("models.bond_residual_zscore")).toBe("obs_date");
    expect(dateColumn("models.cse_security_session")).toBe("session_date");
  });

  test("identifiers and placeholders are checked", () => {
    expect(() => buildQuery(full, "models.bond_residual_zscore", { columns: ["zscore; drop"] })).toThrow(/bad column/);
    expect(() => buildQuery(full, "models.bond_residual_zscore", { orderBy: "isin; drop" })).toThrow(/bad order by/);
    expect(() => buildQuery(full, "models.bond_residual_zscore", { where: "isin = ?", params: [] })).toThrow(/too few/);
    expect(() => buildQuery(full, "models.bond_residual_zscore", { where: "isin = 'x'", params: [1] })).toThrow(/too many/);
  });
});

describe("connection settings", () => {
  const env = (extra: Record<string, string>) => ({ ...extra }) as unknown as NodeJS.ProcessEnv;

  test("a remote database is only used over verified TLS", () => {
    expect(() => poolConfig(env({ DATABASE_URL: "postgresql://web_reader.x@aws-0-ap-south-1.pooler.supabase.com:6543/postgres" }))).toThrow(/DATABASE_CA_CERT/);
    const c = poolConfig(env({ DATABASE_URL: "postgresql://u@db.example:6543/postgres", DATABASE_CA_CERT: "PEM" }));
    expect(c.ssl).toEqual({ ca: "PEM", rejectUnauthorized: true });
  });

  test("timeouts and a small pool, so a database problem fails fast", () => {
    const c = poolConfig(env({ DATABASE_URL: "postgresql://web_reader@127.0.0.1:5432/x" }));
    expect(c.ssl).toBeUndefined();
    expect(c.max).toBe(3);
    expect(c.connectionTimeoutMillis).toBeGreaterThan(0);
    expect(c.query_timeout).toBeGreaterThan(0);
  });
});
