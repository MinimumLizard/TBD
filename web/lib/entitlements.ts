// THE ONLY PLACE A TIER DECISION IS MADE (docs/architecture.md §8; hard rule 5: paid data never reaches an
// unentitled browser). Every page and every API route reads model outputs through lib/db.ts, which accepts only
// the `Granted` value this module returns, so there is no way to read a model's rows without passing through here.
import "server-only";

import { type ModelName, type Tier, TIERS, modelEntry } from "./registry";
import { addDays, todaySLT } from "./time";

export interface Viewer {
  id: string | null; // null: anonymous
  tier: Tier;
}

export interface Granted {
  allowed: true;
  model: ModelName;
  version: string; // the current method version: the only series the site shows
  maxDate: string | null; // free preview: only rows dated on or before this; null = no limit
  delayDays: number; // 0 unless this is a free preview
  minDate: string | null; // recent window: only rows dated on or after this; null = the whole history
  fullHistoryTier: Tier | null; // the tier that would see the whole history, when this grant is a recent window
}

export interface Denied {
  allowed: false;
  model: ModelName;
  requiredTier: Tier;
}

export type Access = Granted | Denied;

// Grants are issued only by authorize(). lib/db.ts refuses any object not in this set, so a grant cannot be made up
// as an object literal elsewhere in the code.
const ISSUED = new WeakSet<Granted>();

export function isGrant(access: unknown): access is Granted {
  return typeof access === "object" && access !== null && ISSUED.has(access as Granted);
}

function grant(g: Omit<Granted, "allowed">): Granted {
  const issued: Granted = Object.freeze({ allowed: true as const, ...g });
  ISSUED.add(issued);
  return issued;
}

export function tierRank(tier: Tier): number {
  return TIERS.indexOf(tier);
}

export function authorize(viewer: Viewer, model: ModelName, today: string = todaySLT()): Access {
  const entry = modelEntry(model);
  const required = entry.minimum_tier;
  if (tierRank(viewer.tier) >= tierRank(required)) {
    const window = entry.recent_window;
    if (window && tierRank(viewer.tier) < tierRank(window.full_history_tier)) {
      return grant({ model, version: entry.current_version, maxDate: null, delayDays: 0,
                     minDate: addDays(today, -window.days), fullHistoryTier: window.full_history_tier });
    }
    return grant({ model, version: entry.current_version, maxDate: null, delayDays: 0, minDate: null, fullHistoryTier: null });
  }
  if (entry.free_preview && entry.free_preview.delay_days > 0) {
    const days = entry.free_preview.delay_days;
    return grant({ model, version: entry.current_version, maxDate: addDays(today, -days), delayDays: days,
                   minDate: null, fullHistoryTier: null });
  }
  return { allowed: false, model, requiredTier: required };
}
