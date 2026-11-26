import { describe, expect, test } from "vitest";

import { authorize, tierRank } from "@/lib/entitlements";
import { MODEL_NAMES, TIERS, modelEntry } from "@/lib/registry";

const TODAY = "2026-10-12";
const daysBefore = (n: number) => new Date(Date.parse(`${TODAY}T00:00:00Z`) - n * 864e5).toISOString().slice(0, 10);

describe("authorize", () => {
  test("tiers are a ladder: free < pro < plus (decision 0027)", () => {
    expect(TIERS).toEqual(["free", "pro", "plus"]);
    expect(tierRank("free")).toBeLessThan(tierRank("pro"));
    expect(tierRank("pro")).toBeLessThan(tierRank("plus"));
  });

  for (const model of MODEL_NAMES) {
    const entry = modelEntry(model);
    for (const tier of TIERS) {
      test(`${model} for ${tier}`, () => {
        const access = authorize({ id: null, tier }, model, TODAY);
        const window = entry.recent_window;
        const top = entry.top_rows;
        const none = { maxDate: null, delayDays: 0, minDate: null, fullHistoryTier: null, topRows: null, topFullTier: null };
        if (tierRank(tier) >= tierRank(entry.minimum_tier) && window && tierRank(tier) < tierRank(window.full_history_tier)) {
          expect(access).toEqual({ allowed: true, model, version: entry.current_version, ...none,
                                   minDate: daysBefore(window.days), fullHistoryTier: window.full_history_tier });
        } else if (tierRank(tier) >= tierRank(entry.minimum_tier) && top && tierRank(tier) < tierRank(top.full_tier)) {
          expect(access).toEqual({ allowed: true, model, version: entry.current_version, ...none,
                                   topRows: top.rows, topFullTier: top.full_tier });
        } else if (tierRank(tier) >= tierRank(entry.minimum_tier)) {
          expect(access).toEqual({ allowed: true, model, version: entry.current_version, ...none });
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

  test("the yield curve: free and Pro see the last 30 days, Plus the whole history", () => {
    const free = authorize({ id: null, tier: "free" }, "bond_ns_curve", TODAY);
    const pro = authorize({ id: null, tier: "pro" }, "bond_ns_curve", TODAY);
    const plus = authorize({ id: null, tier: "plus" }, "bond_ns_curve", TODAY);
    expect(free.allowed && free.minDate).toBe("2026-09-12");
    expect(pro.allowed && pro.minDate).toBe("2026-09-12");
    expect(plus.allowed && plus.minDate).toBe(null);
  });

  test("ownership: free gets a taste (top three), Pro and Plus everything", () => {
    const free = authorize({ id: null, tier: "free" }, "cse_ownership", TODAY);
    expect(free.allowed && free.topRows).toBe(3);
    expect(free.allowed && free.topFullTier).toBe("pro");
    for (const tier of ["pro", "plus"] as const) {
      const a = authorize({ id: null, tier }, "cse_ownership", TODAY);
      expect(a.allowed && a.topRows).toBe(null);
    }
  });

  test("the portfolio lab and share analysis are Pro; bond analysis is Plus", () => {
    for (const m of ["cse_lab_backtest", "cse_fundamentals", "cse_total_returns"] as const) {
      expect(authorize({ id: null, tier: "free" }, m, TODAY).allowed).toBe(false);
      expect(authorize({ id: null, tier: "pro" }, m, TODAY).allowed).toBe(true);
    }
    for (const m of ["bond_carry", "bond_execution_gap", "bond_liquidity"] as const) {
      expect(authorize({ id: null, tier: "pro" }, m, TODAY).allowed).toBe(false);
      expect(authorize({ id: null, tier: "plus" }, m, TODAY).allowed).toBe(true);
    }
  });

  test("only the current method version is ever granted", () => {
    for (const model of MODEL_NAMES) {
      const access = authorize({ id: null, tier: "plus" }, model, TODAY);
      expect(access.allowed && access.version).toBe(modelEntry(model).current_version);
    }
  });
});
