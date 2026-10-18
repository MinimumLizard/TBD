import { expect, test } from "vitest";

import { sig, weeklyPoints } from "@/lib/charts";
import { CRYPTO_ASSETS, assetByPair, assetBySlug, price } from "@/lib/crypto-display";
import { MODEL_ROUTES } from "@/lib/routes";

const days = (n: number, start = "2026-01-01") =>
  Array.from({ length: n }, (_, i) => ({ day: new Date(Date.parse(`${start}T00:00:00Z`) + i * 864e5).toISOString().slice(0, 10), v: i }));

test("charts keep Sundays and the latest day, and never more than the cap", () => {
  const rows = days(30); // 2026-01-04 is a Sunday
  const pts = weeklyPoints(rows, (r) => r.v);
  expect(pts.map((p) => p[0])).toEqual(["2026-01-04", "2026-01-11", "2026-01-18", "2026-01-25", "2026-01-30"]);
  const long = weeklyPoints(days(5600, "2011-09-14"), (r) => r.v);
  expect(long.length).toBeLessThanOrEqual(401);
  expect(long[long.length - 1][1]).toBe(5599); // the latest day is always there
  expect(sig(81384.6345)).toBe(81384.6);
  expect(sig(null)).toBeNull();
});

test("prices are written in their quote currency", () => {
  expect(price(81384.63)).toBe("$81,384.63");
  expect(price(0.21911)).toBe("$0.2191");
  expect(price(0.000012345)).toBe("$0.000012");
  expect(price(0.02946, "BTC")).toBe("0.02946 BTC");
  expect(price(null)).toBe("—");
});

test("every asset has a unique address, and the leak suite visits the crypto pages", () => {
  expect(new Set(CRYPTO_ASSETS.map((a) => a.slug)).size).toBe(CRYPTO_ASSETS.length);
  expect(assetBySlug("btc")?.pair).toBe("btcusd");
  expect(assetByPair("ethbtc")?.quote).toBe("BTC");
  expect(assetBySlug("nope")).toBeUndefined();
  expect(MODEL_ROUTES.crypto_trend_bands.pages).toContain("/crypto/btc");
});
