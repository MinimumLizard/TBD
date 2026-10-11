# 0007 — The API is the web app's server routes; one function decides access

- **Date:** 2026-10-11
- **Status:** Proposed

## Context

The brief asks for a thin server layer that checks the user's tier against the model manifest, so that paid data
never reaches an unentitled browser. Today all three sites publish their full data as static files (audit F12).

## Decision

- Server routes in the Next.js app read the pre-computed model tables.
- `web/lib/entitlements.ts` exposes `authorize(user, model)`, the **only** place a tier decision is made. It uses the
  user's subscription (server-side) and the model's `minimum_tier` from the registry.
- Paid pages render on the server per request. Statically generated pages contain only free data.
- Second line: Postgres row-level security. The browser's key reads only rows marked public. The privileged key exists
  only on the server.
- CI runs tier-leak tests for every model × tier (architecture §8).

## Alternatives considered

A separate Python API service (FastAPI) would be a second deployable, a second set of secrets and another bill, and it
adds no protection the server routes can't give.

## Consequences

If a third-party API is ever wanted, it becomes its own decision, because it raises redistribution rights.
