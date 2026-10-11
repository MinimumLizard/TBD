# 0010 — Compliance is enforced by the build: disclaimers, copy lint, controlled vocabulary

- **Date:** 2026-10-11
- **Status:** Proposed (implements the owner's hard rule)

## Context

Sri Lanka's SEC penalises unlicensed investment advice; it has acted against people giving stock tips online. The
existing tools, as personal tools, use buy/sell framing (audit §8). The product must be information, tools and
education only.

## Decision

1. **Disclaimers:** one registry, `compliance/disclaimers.yaml`, referenced by key. Every model page must show its
   disclaimer, and CI checks it.
2. **Copy lint (CI, fails the build):**
   - Scans message files, manifests, METHOD pages, templates and rendered sample pages.
   - The banned list starts with imperatives and evaluations: *buy, sell, hold, strong buy, accumulate, add to,
     trim, get in, get out, entry, exit point, price target, target price, fair value of, undervalued, overvalued,
     cheap, rich, bargain, top pick(s), our picks, you should, we recommend, recommended, outperform, underperform,
     guaranteed, sure thing, can't lose*.
   - Matching is case-insensitive and whole-word.
   - Factual uses the product needs ("directors **bought** Rs 12 mn on 3 Oct") pass only through
     `compliance/banned_phrases.yaml → allow` entries, each with a file, the exact phrase and a reason.
3. **Controlled vocabulary for model outputs.** Labels come from `compliance/vocabulary.yaml`, and manifests declare
   which they use. Bond residuals read "above / below the fitted curve by n bp". Pair dislocations read "spread n
   standard deviations above its 60-day average". There are no "verdict", "buy leg" or "sell leg" columns.
4. **No personalised output.** No feature combines a user's own holdings or circumstances with a model to produce an
   action.
5. **Historical "what happened next" statistics** (for example the bond reversion table) are shown only on methodology
   pages, as in-sample research results with their caveats, never beside a live reading.
6. **Deferred pending legal advice:** publishing model portfolios or a live model-portfolio record (CSE lab).

## Consequences

Ported models whose old labels were evaluative are renamed in version 1 of their manifest, so parity tests compare
numbers, not labels. This reduces risk but does not replace a lawyer's review before launch.
