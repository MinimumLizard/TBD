# 0014 — The bond curve model will use every published quote

- **Date:** 2026-10-11
- **Status:** Accepted (owner), applies in Phase 3

## Owner's words

> "I think in the earlier model we excluded a few quotes because those bonds weren't being traded as much? Lets
> include all of them for now, this model will anyway be a long work in progress and require regular tweaking"

## What the old model actually excluded

Two separate things, often remembered as one:

1. **Left out of the curve entirely, at ingest (about 38 quotes a day):** the 2023 restructuring bonds
   (step-coupon and sub-1% bonds, posted at an administered 13.00/12.00 every day, 100 bp wide) and one-way quotes
   (only a bid or only an offer). Excluded because they look administered rather than traded, not because of
   trading volume.
2. **Kept in the curve, but not listed as signals:** bonds that trade rarely ("wider market" tier). These were
   always part of the fit; the dashboard just didn't rank them.

## Decision

- Phase 2 already stores every quote as published (decision 0013), so nothing more is needed on the data side.
- Phase 3 ports the curve as **version 1, identical to the old model**, to pass the parity tests. **Version 2
  includes every two-way quote**, administered and step-coupon bonds too, and lists every quoted bond on the page
  with its liquidity tier shown rather than hidden.
- Kept in version 2, because it is how "include everything" stays safe: each quote is weighted by 1/spread², as
  before. A 100 bp administered quote then carries about 1/40th of the weight of a typical 16 bp quote, so it is in
  the fit without being able to drag the curve.
- One-way quotes have no mid; version 2 shows them but cannot fit them. The page will say so.
- Version 2's METHOD.md states the change and its measured effect on fit error, compared with version 1.
