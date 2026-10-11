import { describe, expect, test } from "vitest";

import { buildQuery, dateColumn } from "@/lib/db";
import type { Granted } from "@/lib/entitlements";

const full: Granted = { allowed: true, model: "bond_rv_zscores", version: "1.1.0", maxDate: null, delayDays: 0 };
const preview: Granted = { ...full, maxDate: "2026-10-07", delayDays: 5 };

describe("buildQuery", () => {
  test("always filters to the granted version", () => {
    const q = buildQuery(full, "models.bond_residual_zscore", { where: "obs_date = ?", params: ["2026-10-09"], orderBy: "isin" });
    expect(q.text).toBe("select * from models.bond_residual_zscore where method_version = $1 and (obs_date = $2) order by isin");
    expect(q.values).toEqual(["1.1.0", "2026-10-09"]);
  });

  test("a preview can never read past its date", () => {
    const q = buildQuery(preview, "models.bond_residual_zscore", { where: "obs_date = ?", params: ["2026-10-09"] });
    expect(q.text).toContain("obs_date <= $2");
    expect(q.values).toEqual(["1.1.0", "2026-10-07", "2026-10-09"]);
  });

  test("a model can read only its own outputs, never an unpublished one", () => {
    expect(() => buildQuery(full, "models.bond_carry")).toThrow(/not an output/);
    expect(() => buildQuery(full, "models.model_stats")).toThrow(/not published/);
    expect(() => buildQuery({ ...full, model: "bond_identity" }, "models.bond_quotes; drop table x")).toThrow();
  });

  test("a table without dates cannot be served as a preview", () => {
    expect(dateColumn("models.bond_reference")).toBeNull();
    expect(() => buildQuery({ ...preview, model: "bond_identity" }, "models.bond_reference")).toThrow(/delayed preview/);
  });

  test("identifiers and placeholders are checked", () => {
    expect(() => buildQuery(full, "models.bond_residual_zscore", { columns: ["zscore; drop"] })).toThrow(/bad column/);
    expect(() => buildQuery(full, "models.bond_residual_zscore", { orderBy: "isin; drop" })).toThrow(/bad order by/);
    expect(() => buildQuery(full, "models.bond_residual_zscore", { where: "isin = ?", params: [] })).toThrow(/too few/);
    expect(() => buildQuery(full, "models.bond_residual_zscore", { where: "isin = 'x'", params: [1] })).toThrow(/too many/);
  });
});
