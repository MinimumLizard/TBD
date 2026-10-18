import { describe, expect, test } from "vitest";

import { actionAmount, companyName } from "@/lib/cse-display";
import { sparkline } from "@/lib/sparkline";

describe("companyName", () => {
  test("capitals become title case, keeping PLC and initials the CSE uses", () => {
    expect(companyName("JOHN KEELLS HOLDINGS PLC")).toBe("John Keells Holdings PLC");
    expect(companyName("BANK OF CEYLON")).toBe("Bank of Ceylon");
    expect(companyName("AMANA TAKAFUL  PLC")).toBe("Amana Takaful PLC");
  });
  test("a name already in mixed case is kept as published", () => {
    expect(companyName("Assetline Finance PLC")).toBe("Assetline Finance PLC");
    expect(companyName(null)).toBeNull();
  });
});

describe("actionAmount", () => {
  const blank = { amount_per_share: null, ratio_new: null, ratio_held: null, factor: null, subscription_price: null };
  test("each kind of corporate action reads in words, with the figures the CSE gave", () => {
    expect(actionAmount({ ...blank, action_type: "cash_dividend", amount_per_share: 0.5 })).toEqual({ key: "dividend", values: { amount: "0.50" } });
    expect(actionAmount({ ...blank, action_type: "cash_dividend", amount_per_share: 0.0625 })!.values.amount).toBe("0.0625");
    expect(actionAmount({ ...blank, action_type: "subdivision", factor: 5, ratio_new: 4, ratio_held: 1 })).toEqual({ key: "split", values: { factor: "5" } });
    expect(actionAmount({ ...blank, action_type: "scrip", ratio_new: 1, ratio_held: 108.2352945432 })!.values.existing).toBe("108.2353");
    expect(actionAmount({ ...blank, action_type: "rights", ratio_new: 3, ratio_held: 50, subscription_price: 200 }))
      .toEqual({ key: "rights", values: { new: "3", existing: "50", price: "200.00" } });
    expect(actionAmount({ ...blank, action_type: "rights", ratio_new: 3, ratio_held: 50 })!.key).toBe("rightsNoPrice");
  });
  test("nothing is shown that the record does not give", () => {
    expect(actionAmount({ ...blank, action_type: "scrip" })).toBeNull();
    expect(actionAmount({ ...blank, action_type: "rights", ratio_new: 3 })).toBeNull();
  });
});

describe("sparkline", () => {
  test("scales the series into the box, highest point at the top", () => {
    const s = sparkline([1, 3, 2], 100, 20)!;
    expect(s.line).toBe("M0 18 L50 2 L100 10");
    expect(s.area.endsWith("L100 20 L0 20 Z")).toBe(true);
  });
  test("needs two numbers", () => {
    expect(sparkline([1, null])).toBeNull();
    expect(sparkline([5, 5])!.line).toBe("M0 30 L120 30");   // a flat series sits on the floor
  });
});
