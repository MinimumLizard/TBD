// The model registry, as generated from the manifests and config/entitlements.yaml by
// `python -m data_platform.models.registry export-web`. CI fails if this copy is out of date.
import registryJson from "./generated/registry.json";

export type Tier = "free" | "plus" | "pro" | "professional";

export interface ModelEntry {
  market: "lk_bonds" | "cse" | "crypto";
  title_key: string;
  summary_key: string;
  disclaimer_key: string;
  outputs: string[];
  current_version: string;
  versions: { method_version: string; status: string; changes: string | null }[];
  minimum_tier: Tier;
  free_preview: { delay_days: number } | null;
  recent_window: { days: number; full_history_tier: Tier } | null;
  method_md: string;
}

interface Registry {
  tiers: Tier[];
  unpublished_outputs: string[];
  disclaimers: Record<string, { en: string }>;
  calendars: Record<string, { name: string; every_day?: boolean; closures: string[] }>;
  models: Record<string, ModelEntry>;
}

export const registry = registryJson as unknown as Registry;
export const TIERS: Tier[] = registry.tiers;
export type ModelName = keyof typeof registryJson.models;
export const MODEL_NAMES = Object.keys(registry.models) as ModelName[];

export function isTier(value: unknown): value is Tier {
  return typeof value === "string" && (TIERS as string[]).includes(value);
}

export function isModelName(value: unknown): value is ModelName {
  return typeof value === "string" && Object.hasOwn(registry.models, value);
}

export function modelEntry(name: ModelName): ModelEntry {
  return registry.models[name];
}
