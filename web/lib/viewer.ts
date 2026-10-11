// Who is looking. Until accounts exist (Supabase Auth; docs/decisions/0016), every visitor is anonymous and on
// the free tier. Tiers are then read from the visitor's subscription row on the server, never from the browser.
import "server-only";

import { headers } from "next/headers";

import type { Viewer } from "./entitlements";
import { isTier } from "./registry";

export const ANONYMOUS: Viewer = { id: null, tier: "free" };

// The tier-leak tests act as each tier through this header. It works only when ALLOW_TEST_TIERS=1 AND the app is
// not running as production AND not on Vercel at all (VERCEL is set on every Vercel deployment, previews included),
// so it can never be used on any deployed site.
export function testTiersEnabled(env: NodeJS.ProcessEnv = process.env): boolean {
  return env.ALLOW_TEST_TIERS === "1" && env.APP_ENV !== "production" && !env.VERCEL && !env.VERCEL_ENV;
}

export async function getViewer(): Promise<Viewer> {
  // Reading the request makes every page render per visitor, so no page is ever built once and served to all.
  const requestHeaders = await headers();
  if (testTiersEnabled()) {
    const asked = requestHeaders.get("x-test-tier");
    if (isTier(asked)) return { id: "test", tier: asked };
  }
  return ANONYMOUS;
}
