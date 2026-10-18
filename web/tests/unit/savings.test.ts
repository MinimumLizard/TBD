// The savings calculator's form reading and month arithmetic, and the rupee and month formats it uses.
import { expect, test } from "vitest";

import { monthYear, rupees } from "@/lib/format";
import { addMonths, dataThrough, readCalc } from "@/lib/savings-calc";

const FIRST = "2003-01-01";
const THROUGH = "2026-08-01";

test("months add across year ends, both ways", () => {
  expect(addMonths("2026-08-01", -120)).toBe("2016-08-01");
  expect(addMonths("2025-11-01", 2)).toBe("2026-01-01");
  expect(addMonths("2003-01-01", -1)).toBe("2002-12-01");
});

test("the data runs to the last month with all three figures", () => {
  expect(dataThrough([
    { month: "2026-08-01", fd_rate_pct: 8.3, bill_rate_pct: 9.9, cpi: 400 },
    { month: "2026-09-01", fd_rate_pct: null, bill_rate_pct: null, cpi: 401 },
  ])).toBe("2026-08-01");
  expect(dataThrough([])).toBeNull();
});

test("the calculator defaults to Rs 100,000 over the latest five years", () => {
  expect(readCalc({}, FIRST, THROUGH)).toEqual({ amount: 100_000, start: "2021-08-01", years: 5, invalid: false });
});

test("the calculator reads its form", () => {
  expect(readCalc({ amount: "250,000", sy: "2010", sm: "3", years: "10" }, FIRST, THROUGH)).toEqual(
    { amount: 250_000, start: "2010-03-01", years: 10, invalid: false });
  // a missing start falls back to the latest period of the chosen length
  expect(readCalc({ years: "1" }, FIRST, THROUGH).start).toBe("2025-08-01");
});

test("anything unreadable falls back to the default and says so", () => {
  for (const params of [{ amount: "-5" }, { amount: "1e9" }, { amount: "abc" }, { years: "11" }, { years: "0" }, { sm: "13" },
                        { sy: "1999" }, { sy: "2027" }, { amount: "99999999999" }]) {
    const c = readCalc(params, FIRST, THROUGH);
    expect(c.invalid, JSON.stringify(params)).toBe(true);
    expect(c.amount > 0 && c.years >= 1 && c.years <= 10).toBe(true);
    expect(c.start >= FIRST && c.start <= THROUGH).toBe(true);
  }
  expect(readCalc({ amount: ["5000", "7000"] }, FIRST, THROUGH).amount).toBe(5000);
});

test("rupees and months", () => {
  expect(rupees(110870.15)).toBe("Rs 110,870");
  expect(rupees(null)).toBe("—");
  expect(monthYear("2026-08-01")).toBe("Aug 2026");
});
