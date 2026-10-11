import { describe, expect, test } from "vitest";

import { authorize, tierRank } from "@/lib/entitlements";
import { MODEL_NAMES, TIERS, modelEntry } from "@/lib/registry";

const TODAY = "2026-10-12";

describe("authorize", () => {
  test("tiers are ordered free < plus < pro < professional", () => {
    expect(TIERS).toEqual(["free", "plus", "pro", "professional"]);
    expect(tierRank("free")).toBeLessThan(tierRank("professional"));
  });

  for (const model of MODEL_NAMES) {
    const entry = modelEntry(model);
    for (const tier of TIERS) {
      test(`${model} for ${tier}`, () => {
        const access = authorize({ id: null, tier }, model, TODAY);
        if (tierRank(tier) >= tierRank(entry.minimum_tier)) {
          expect(access).toEqual({ allowed: true, model, version: entry.current_version, maxDate: null, delayDays: 0 });
        } else if (entry.free_preview) {
          expect(access.allowed).toBe(true);
          if (access.allowed) {
            expect(access.delayDays).toBe(entry.free_preview.delay_days);
            expect(access.maxDate).toBe(new Date(Date.parse(`${TODAY}T00:00:00Z`) - entry.free_preview.delay_days * 864e5).toISOString().slice(0, 10));
          }
        } else {
          expect(access).toEqual({ allowed: false, model, requiredTier: entry.minimum_tier });
        }
      });
    }
  }

  test("only the current method version is ever granted", () => {
    for (const model of MODEL_NAMES) {
      const access = authorize({ id: null, tier: "professional" }, model, TODAY);
      expect(access.allowed && access.version).toBe(modelEntry(model).current_version);
    }
  });
});
