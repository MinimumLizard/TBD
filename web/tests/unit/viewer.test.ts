import { expect, test } from "vitest";

import { testTiersEnabled } from "@/lib/viewer";

test("acting as a tier is possible only in tests, never in production", () => {
  expect(testTiersEnabled({ ALLOW_TEST_TIERS: "1" } as unknown as NodeJS.ProcessEnv)).toBe(true);
  expect(testTiersEnabled({} as unknown as NodeJS.ProcessEnv)).toBe(false);
  expect(testTiersEnabled({ ALLOW_TEST_TIERS: "1", APP_ENV: "production" } as unknown as NodeJS.ProcessEnv)).toBe(false);
  expect(testTiersEnabled({ ALLOW_TEST_TIERS: "1", VERCEL_ENV: "production" } as unknown as NodeJS.ProcessEnv)).toBe(false);
  expect(testTiersEnabled({ ALLOW_TEST_TIERS: "1", VERCEL_ENV: "preview" } as unknown as NodeJS.ProcessEnv)).toBe(false);
  expect(testTiersEnabled({ ALLOW_TEST_TIERS: "1", VERCEL: "1" } as unknown as NodeJS.ProcessEnv)).toBe(false);
});
