// Chart option builders (lib/charts.ts): plain data, one scale per chart.
import { describe, expect, it } from "vitest";

import { barOption, indexed, lineOption, scatterOption } from "@/lib/charts";

describe("chart options", () => {
  it("indexes a series to 100 at its first value, keeping gaps", () => {
    expect(indexed([["2026-01-01", 200], ["2026-01-02", 210], ["2026-01-03", null], ["2026-01-04", 190]]))
      .toEqual([["2026-01-01", 100], ["2026-01-02", 105], ["2026-01-03", null], ["2026-01-04", 95]]);
    expect(indexed([["2026-01-01", null], ["2026-01-02", 50], ["2026-01-03", 75]]))
      .toEqual([["2026-01-01", null], ["2026-01-02", 100], ["2026-01-03", 150]]);
    expect(indexed([])).toEqual([]);
  });

  it("draws bars with an optional line on the same, single scale", () => {
    const bars = { name: "Turnover", points: [["2026-01-01", 5]] as [string, number][] };
    const alone = barOption(bars, undefined, "Rs mn");
    expect(alone.series).toHaveLength(1);
    expect(alone.legend).toBeUndefined();                         // one series: the heading names it
    const both = barOption(bars, { name: "Average", points: [["2026-01-01", 4]] }, "Rs mn");
    expect(both.series.map((s) => s.type)).toEqual(["bar", "line"]);
    expect(both.legend).toBeDefined();                            // two series: always a legend
    expect(Array.isArray(both.yAxis)).toBe(false);                // never two y-axes
  });

  it("gives two or more lines a legend and one line none", () => {
    const p: [string, number][] = [["2026-01-01", 1]];
    expect(lineOption([{ name: "A", points: p }]).legend).toBeUndefined();
    expect(lineOption([{ name: "A", points: p }, { name: "B", points: p }]).legend).toBeDefined();
  });

  it("labels each point of a scatter and marks zero", () => {
    const o = scatterOption([[2.5, 120, "10.00%2030A"]], { series: "Total", x: "Duration", y: "bp" });
    expect(o.series[0].data).toEqual([[2.5, 120, "10.00%2030A"]]);
    expect(o.series[0].markLine.data).toEqual([{ yAxis: 0 }]);
    expect(o.xAxis.name).toBe("Duration");
  });
});
