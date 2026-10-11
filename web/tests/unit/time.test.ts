import { expect, test } from "vitest";

import { isModelName } from "@/lib/registry";
import { isIsoDate } from "@/lib/time";

test("only real dates are accepted", () => {
  expect(isIsoDate("2026-10-09")).toBe(true);
  for (const bad of ["2026-02-30", "0000-01-01", "2026-13-01", "2026-1-1", "x", 20261009]) expect(isIsoDate(bad)).toBe(false);
});

test("built-in object names are not models", () => {
  for (const name of ["constructor", "__proto__", "toString", "hasOwnProperty"]) expect(isModelName(name)).toBe(false);
  expect(isModelName("bond_ns_curve")).toBe(true);
});
