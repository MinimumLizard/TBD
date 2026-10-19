import { describe, expect, test } from "vitest";

import { buildQuery, dateColumn } from "@/lib/db";
import { companyCode, flowWindow } from "@/lib/dealings-display";
import { type Granted, authorize } from "@/lib/entitlements";
import { modelEntry, registry } from "@/lib/registry";

const TODAY = "2026-10-19";

describe("directors' dealings and money flows", () => {
  test("no output that holds a person's name can be read by anyone", () => {
    expect(registry.unpublished_outputs).toEqual(expect.arrayContaining(["models.cse_dealing_as_filed", "models.cse_flow_actor"]));
    const dealings = authorize({ id: null, tier: "professional" }, "cse_dealings", TODAY) as Granted;
    const flows = authorize({ id: null, tier: "professional" }, "cse_flows", TODAY) as Granted;
    expect(() => buildQuery(dealings, "models.cse_dealing_as_filed")).toThrow(/not published/);
    expect(() => buildQuery(flows, "models.cse_flow_actor")).toThrow(/not published/);
    expect(buildQuery(dealings, "models.cse_dealing").text).toContain("from models.cse_dealing where");
  });

  test("the money flows' free preview stops a week back on every table it reads", () => {
    expect(modelEntry("cse_flows").free_preview?.delay_days).toBe(7);
    const preview = authorize({ id: null, tier: "free" }, "cse_flows", TODAY) as Granted;
    expect(preview.maxDate).toBe("2026-10-12");
    for (const table of ["models.cse_flow_company", "models.cse_flow_summary", "models.cse_flow_dealing"]) {
      const column = dateColumn(table);
      expect(column, table).not.toBeNull();
      expect(buildQuery(preview, table).text).toContain(`${column} <= $2`);
    }
    expect(authorize({ id: null, tier: "plus" }, "cse_flows", TODAY)).toMatchObject({ allowed: true, maxDate: null });
  });

  test("dealings are free; windows and company codes are read safely", () => {
    expect(modelEntry("cse_dealings").minimum_tier).toBe("free");
    expect([flowWindow("90"), flowWindow("365"), flowWindow("7"), flowWindow(undefined), flowWindow("x")]).toEqual([90, 365, 30, 30, 30]);
    expect(companyCode("AAA.N0000")).toBe("AAA");
    expect(companyCode("AAA")).toBe("AAA");
  });
});
