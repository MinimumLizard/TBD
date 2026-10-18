import { describe, expect, test } from "vitest";

import { companyName } from "@/lib/cse-display";
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
