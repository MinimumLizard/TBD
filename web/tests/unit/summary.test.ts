import { describe, expect, test } from "vitest";

import { marketSummary } from "@/lib/summary";

describe("marketSummary", () => {
  test("describes the day in order: index, breadth, turnover, foreign flows, bond yields", () => {
    const lines = marketSummary({
      aspi: { value: 20185.05, pct: 0.0107 },
      breadth: { up: 188, down: 35, flat: 53 },
      turnover: { value: 1.14e9, avg20: 0.95e9 },
      foreignNet: -8.71e6,
      curve: { y1: 9.71, y5: 11.38, y10: 12.21 },
    });
    expect(lines.map((l) => l.key)).toEqual([
      "home.summary.aspiUp", "home.summary.breadth", "home.summary.turnoverAvg", "home.summary.foreignOut", "home.summary.bonds",
    ]);
    expect(lines[0].values).toEqual({ pct: "1.07%", value: "20,185.05" });
    expect(lines[2].values.ratio).toBe("1.20×");
    expect(lines[3].values.value).toBe("Rs 8.71 mn");
    expect(lines[4].values).toEqual({ y1: "9.71%", y5: "11.38%", y10: "12.21%" });
  });

  test("leaves out what is missing, and a flat day is described as unchanged", () => {
    expect(marketSummary({ aspi: { value: 100, pct: 0 } }).map((l) => l.key)).toEqual(["home.summary.aspiFlat"]);
    expect(marketSummary({ turnover: { value: null, avg20: null }, foreignNet: 0 })).toEqual([]);
  });
});
