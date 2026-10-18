import { describe, expect, test } from "vitest";

import { authorize, tierRank } from "@/lib/entitlements";
import { MODEL_NAMES, TIERS, modelEntry } from "@/lib/registry";

const TODAY = "2026-10-12";
const daysBefore = (n: number) => new Date(Date.parse(`${TODAY}T00:00:00Z`) - n * 864e5).toISOString().slice(0, 10);

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
        const window = entry.recent_window;
        if (tierRank(tier) >= tierRank(entry.minimum_tier) && window && tierRank(tier) < tierRank(window.full_history_tier)) {
          expect(access).toEqual({ allowed: true, model, version: entry.current_version, maxDate: null, delayDays: 0,
                                   minDate: daysBefore(window.days), fullHistoryTier: window.full_history_tier });
        } else if (tierRank(tier) >= tierRank(entry.minimum_tier)) {
          expect(access).toEqual({ allowed: true, model, version: entry.current_version, maxDate: null, delayDays: 0,
                                   minDate: null, fullHistoryTier: null });
        } else if (entry.free_preview) {
          expect(access.allowed).toBe(true);
          if (access.allowed) {
            expect(access.delayDays).toBe(entry.free_preview.delay_days);
            expect(access.maxDate).toBe(daysBefore(entry.free_preview.delay_days));
          }
        } else {
          expect(access).toEqual({ allowed: false, model, requiredTier: entry.minimum_tier });
        }
      });
    }
  }

  test("the yield curve: free sees the last 30 days, Plus and above the whole history", () => {
    const free = authorize({ id: null, tier: "free" }, "bond_ns_curve", TODAY);
    const plus = authorize({ id: null, tier: "plus" }, "bond_ns_curve", TODAY);
    expect(free.allowed && free.minDate).toBe("2026-09-12");
    expect(plus.allowed && plus.minDate).toBe(null);
  });

  test("only the current method version is ever granted", () => {
    for (const model of MODEL_NAMES) {
      const access = authorize({ id: null, tier: "professional" }, model, TODAY);
      expect(access.allowed && access.version).toBe(modelEntry(model).current_version);
    }
  });
});
