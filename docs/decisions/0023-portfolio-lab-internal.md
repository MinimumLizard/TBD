# 0023 — The portfolio lab, as internal research (Phase 3b, part 4)

- **Date:** 2026-10-20
- **Status:** Proposed (part of Phase 3b's approval; the owner approved building it as internal research)

## Context

The old CSE terminal ran model portfolios with a live record (audit C8–C11). Publishing model portfolios or their
rebalancing waits for a lawyer's view (decision 0010 point 6; `docs/plan-retail-features.md` §5), and the owner asked
for the lab to be ported as internal research, with retail versions of 10 and 15 names (plan §6).

## Decisions

1. **Internal only, by construction.** Three models, `cse_risk_estimates` (C4, C8, C9), `cse_portfolio_lab` (C10) and
   `cse_lab_record` (C11), are listed under `internal_models` in `config/entitlements.yaml`: they have no tier, every
   output is in `unpublished_outputs`, migration 0016 revokes every one of their tables from the website's role, and
   `registry export-web` leaves them out of the website's copy of the registry (no methods page, no plans entry, no
   API listing). The registry check enforces all of this. The tier-leak suite seeds lab rows whose values must
   appear nowhere. The owner reads the lab through `python -m data_platform.jobs.lab_report --out <file>`, which
   writes one self-contained HTML file and refuses a path inside the repository.
2. **Personal settings stay private.** The old conflict-of-interest list and portfolio size are the owner's personal
   settings. They live in a private file (`LAB_PRIVATE_FILE`; in Actions the secret `LAB_PRIVATE_YAML`), stored by the
   reviews job as `cse.lab_private_settings` (append-only, every version kept); the website cannot read it. Version
   1.0.0 needs it and computes nothing without it; version 1.1.0 does not use it. The old "my book" and the old trade
   list are not ported (personal; a trade instruction).
3. **Version 1.0.0 is the exact port** (status `reference`): the old code's arithmetic in the same order, the same
   solver versions (cvxpy 1.9.3, Clarabel 0.11.1, scikit-learn 1.9.1), the owner's typed risk-free 9.9 % and the
   assumed 6 % premium, the old preview while the history was short, and the old record continued from its inception
   on 2026-10-07 with numbers kept to 8 decimals as the old files kept them. Parity: within 1e-9 at all 9 old
   sessions and the 9 stored lab files (the largest weight difference 3e-13, from the last bits of the price inputs);
   two stored risk-parity solutions differ by up to 5.3e-6, as do the old tool's own runs on identical inputs (the
   solver stops at its tolerance), so they are compared within 1e-5; the old record files agree row for row.
4. **Version 1.1.0 is current.** The risk-free rate is the CBSL's 12-month treasury bill yield as published by the
   estimate date (a month's figure is used once a full month has passed after it); the 6 % premium is kept and
   labelled an assumption; no personal exclusions; no preview.
5. **A neutral notional of Rs 1 mn** for the liquidity caps and the record (instead of the owner's portfolio size).
   It is a plausible size for a retail portfolio, and with the universe's Rs 1 mn median-turnover floor the liquidity
   cap (at least 200 %) never binds at that size; the record's smallest change is scaled with it (Rs 2,500, the same
   0.25 % of the notional as the old Rs 25,000 of Rs 10 mn).
6. **The 10- and 15-name versions** follow plan §6: the K largest names of the full portfolio of the same kind
   (minimum variance, maximum Sharpe; equal weight on the minimum-variance names), a name already in staying while it
   ranks in the top 1.5 K, re-optimised with the same sector, group and liquidity caps, a per-share cap of
   max(10 %, 1.5 / K) and a floor of 0.5 / K; set on the first estimate date and then only on the quarterly rebalance
   dates; tracking error against the full portfolio reported.
7. **The record is forward-only and never backfilled.** Version 1.1.0's record starts at the first production run
   that finds valid model weights. Each run reads back the rows recorded and adds only later sessions; a session
   recorded is never rewritten. No historical simulation is built.
8. **The covariance is stored in factor form** (the weekly returns, the universe and the shrinkage determine it
   exactly), not as about 10,000 numbers a day; the lab rebuilds it and checks the shrinkage to the last bit.
9. **Each date's portfolios are reused when nothing they depend on changed** (a SHA-256 of the date's inputs,
   parameters, the previous rebalance date's names and the code, stored per date), so a daily run computes only new
   or changed dates. The result equals a full recomputation (tested).
10. **Money flows completed in place** (cse_flows 1.0.0, no production run yet): the owner's aliases and the
   same-ownership-group flag, as the old page had them; parity with the old code remains exact.

## Consequences

- The risk estimates are recomputed in full on every run, so their run time grows with the history (a later version
  can compute only new dates); the portfolios are reused date by date.
- Nothing of the lab can be shown until the owner decides, with the lawyer, between paths P1–P3 (plan §5); the lab
  report contains wording mock-ups of the three for that conversation.
- Model portfolios on in-sample estimates are fragile (one year of weekly returns, CAPM with an assumed premium; a
  Sharpe ratio's uncertainty about ±1): the report carries these caveats with every number.
