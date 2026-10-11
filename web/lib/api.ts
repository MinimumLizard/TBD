// The JSON API's common shape (docs/architecture.md §8). Every response is per visitor, so nothing is cached by a
// shared cache: a CDN must never hand one tier's response to another.
import "server-only";

import { NextResponse } from "next/server";

import type { Result } from "./data/common";
import { type ModelName, modelEntry, registry } from "./registry";
import { isIsoDate } from "./time";

const NO_SHARED_CACHE = { "Cache-Control": "private, no-store", Vary: "Cookie, Authorization" };

export function json(body: unknown, status = 200): NextResponse {
  return NextResponse.json(body, { status, headers: NO_SHARED_CACHE });
}

export function badRequest(message: string): NextResponse {
  return json({ error: "bad_request", message }, 400);
}

export function dateParam(url: URL): string | undefined | null {
  const value = url.searchParams.get("date");
  if (value === null) return undefined;
  return isIsoDate(value) ? value : null; // null: present but malformed
}

/** 403 with no data when denied; otherwise the data with its model, version, preview limit and disclaimer. */
export function respond<T>(model: ModelName, result: Result<T>): NextResponse {
  const { access } = result;
  if (!access.allowed) {
    return json({ error: "tier_required", model, required_tier: access.requiredTier }, 403);
  }
  const entry = modelEntry(model);
  return json({
    model,
    method_version: access.version,
    preview: access.maxDate ? { delay_days: access.delayDays, data_to: access.maxDate } : null,
    disclaimer: registry.disclaimers[entry.disclaimer_key].en,
    attribution: registry.disclaimers.data_sources.en,
    data: result.data,
  });
}
