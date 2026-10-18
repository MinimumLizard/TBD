import { describe, expect, test } from "vitest";

import { yieldScenarios } from "@/lib/scenarios";

describe("yieldScenarios", () => {
  test("duration and convexity: prices fall when yields rise, and fall less than they rise for the same move", () => {
    const rows = yieldScenarios(100, 4, 25, [-100, 100]);
    expect(rows[0].change).toBeCloseTo(0.04 + 0.00125, 10);
    expect(rows[1].change).toBeCloseTo(-0.04 + 0.00125, 10);
    expect(rows[1].price).toBeCloseTo(96.125, 10);
    expect(Math.abs(rows[0].change)).toBeGreaterThan(Math.abs(rows[1].change));
  });
});
