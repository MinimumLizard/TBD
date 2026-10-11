import { expect, test } from "vitest";

import { NONE, lkr, num, pct, signed } from "@/lib/format";

test("numbers", () => {
  expect(num(1234.567)).toBe("1,234.57");
  expect(num(-1.5, 1)).toBe("−1.5");
  expect(num(null)).toBe(NONE);
  expect(signed(0.5, 1)).toBe("+0.5");
  expect(signed(0, 1)).toBe("±0.0");
  expect(pct(0.0123)).toBe("+1.23%");
  expect(pct(Number.NaN)).toBe(NONE);
});

test("rupees", () => {
  expect(lkr(1_050_000_000)).toBe("Rs 1.05 bn");
  expect(lkr(222_000_000)).toBe("Rs 222.0 mn");
  expect(lkr(9_300_000)).toBe("Rs 9.30 mn");
  expect(lkr(-157_500_000)).toBe("−Rs 157.5 mn");
});
