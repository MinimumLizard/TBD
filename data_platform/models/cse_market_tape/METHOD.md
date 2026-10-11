# CSE market summary (cse_market_tape)

## What it shows

For each session of the Colombo Stock Exchange: every index's level and change (ASPI, S&P SL20, their total
return versions and the sector indices), market turnover, volume and number of trades compared with their recent
average, foreign purchases and sales, the market's valuation figures as the CSE publishes them, and breadth (how
many shares rose, fell or closed unchanged).

## Inputs

The CSE's daily index values, daily market summary and trade summary, stored as published (`cse.*` tables).

## Method (version 1.0.0)

- Sessions are the days the ASPI has a value.
- Index change as a fraction: change / (level − change), from the published level and change.
- Activity against average: the session's turnover (volume, trades) divided by the mean of the previous 20
  sessions of the CSE's daily market summary. The average needs 21 sessions of that summary; until then the
  number of sessions still needed is stored instead. (The summary has been collected daily only since October
  2026, so this fills in over the first weeks.)
- Foreign net = foreign purchases − foreign sales, as the CSE reports them.
- Breadth counts ordinary voting and non-voting shares (`.N0000`, `.X0000`) that traded in the session, comparing
  each close with the previous close.

## Limits

- Valuation figures (P/E, P/B, dividend yield) are the CSE's own, unchecked.
- For sessions before daily collection began, breadth comes from the CSE's chart history and turnover figures
  are not available.

## Parity

Version 1 reproduces the old CSE terminal's Panel A for every session it kept raw files for (5 sessions): index
levels and changes exactly, total-return changes to 1e-16, the CSE's rounded percentage changes to their rounding
(0.005 percentage points), and market activity, flows, valuation and breadth exactly. Measured by
`python -m data_platform.migration.parity cse` (report: `docs/migration/parity-cse.json`).
