# Forward record of the research portfolios (cse_lab_record)

**Internal research only.** Nothing here is shown on the site: every output is unpublished
(`config/entitlements.yaml`), the website's database role cannot read it (migration 0016), and the owner reads it
through `python -m data_platform.jobs.lab_report`. A record of a model portfolio is not a performance claim and must
not be published before a lawyer's view (decision 0010 point 6).

## What it records

What the model portfolios of `cse_portfolio_lab` would have held, session by session, from the day the record started:
whole shares, costs paid, corporate actions booked, and the market (the ASPI) beside them. It is a port of the old CSE
terminal's live record (MinimumLizard/CSE@e05c6f3 `cse/record.py`; its `docs/METHODS.md` §9). The old personal
comparison portfolio and the old personal trade list are not ported.

## Forward only

- **Append-only.** Each run reads back the rows already recorded and returns them unchanged; it adds only the sessions
  after the last one recorded, one at a time, in order. A session already recorded is never rewritten, even when the
  inputs of a past date change later.
- **Never backfilled.** Version 1.1.0 starts at the first run that finds valid model weights, on that run's latest
  session. Version 1.0.0 continues the old tool's own series `v1-52w-grp20` from its inception on 2026-10-07 (its rows
  for 2026-10-07 to 2026-10-15 equal the old record files).
- A look at the past (`--as-of`) returns the rows recorded up to that date; it adds nothing.

## Rules

N is the notional (version 1.0.0: Rs 10 mn per portfolio, the old setting; version 1.1.0: Rs 1 mn, neutral) and c the
cost per side, 1.12 % (to be checked against the current CSE cost schedule).

- **Inception.** Each portfolio starts with N in cash and takes, for each name, **⌊w × N / (P × (1 + c))⌋** shares at
  that session's close P; it pays c on each trade's value and keeps the rest as cash. The market portfolio has
  N / ASPI index units.
- **Value** each session = Σ shares × the last traded close + cash. If a share-count event went ex but the share has not
  traded since, the old close is divided by the factor (or replaced by the theoretical ex-rights price, or reduced by
  the dividend), so the value does not jump.
- **Corporate actions on holdings**, on their ex-date (actions in use by `cse_corporate_actions` only): a cash dividend
  credits shares × dividend × (1 − withholding, 0 %); a sub-division or scrip issue sets shares = ⌊shares × factor⌋
  (fractions dropped); a rights issue is taken up, ⌊shares × m / n⌋ new shares at the subscription price, paid from
  cash, as far as the cash allows (the shortfall is noted).
- **Rebalance dates**: the first session of January, April, July and October. Every name goes back to its model weight
  of that day at that close, decreases first, then increases limited by cash; a change smaller than the minimum
  (Rs 25,000 in 1.0.0; Rs 2,500, the same 0.25 % of the notional, in 1.1.0) is skipped. On a rebalance date without
  valid model weights nothing changes and the note says so.
- **Drift band.** After each session a name is flagged when **|weight − model weight| > max(0.25 × model weight,
  2 percentage points)**; flagged names go back to their model weight at the next session's close (model weights
  unchanged).
- The versions with 10 and 15 names (1.1.0) follow the same rules; their model weights are the ones in force in the
  lab on the day (set on the first estimate date and on each rebalance date).
- Version 1.0.0 keeps every number rounded to 8 decimals and reads the state back rounded, exactly as the old files
  did; version 1.1.0 keeps full precision.

The direction of a change of shares is recorded as `increase` or `decrease`; corporate actions as `dividend`,
`subdivision`, `scrip` or `rights`.

## Outputs

- `models.cse_lab_nav`: per session, series and portfolio: value, cash, value of the holdings, a note (inception,
  scheduled rebalance, the names brought back inside the drift band).
- `models.cse_lab_holding`: per session, series, portfolio and name: shares, price, value, weight, model weight,
  outside the drift band or not.
- `models.cse_lab_trade`: each change of shares and each corporate action: shares, price, value, cost, reason.

## Limits

- Closing prices, no market impact beyond the stated cost, no taxes other than the stated withholding.
- Statistics of the record (return, volatility, drawdown) are meaningful only after many months; the old tool showed
  none before 26 weeks, and the lab report follows that.

## Parity

Version 1.0.0: every row of the old `record/nav.csv`, `holdings.csv` and `trades.csv` (both old series: `v0-52w` on
2026-10-07, started on the portfolios without the group cap, and `v1-52w-grp20` from 2026-10-07 to 2026-10-15), as the
old CSV writer formats them. Counts only: `docs/migration/parity-cse-portfolio-lab.json`.
