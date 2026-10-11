# Trades against quotes (bond_execution_gap)

## What it shows

On days when a bond both quoted and traded, its executed weighted-average yield can be compared with its quoted
mid. The gap is the median of (traded yield − quoted mid) in basis points over the last 20 calendar days.
Positive: trades printed at higher yields, that is lower prices, than the quote screen.

## Inputs

The quote and trade points of `bond_ns_curve` (the same yields the curve stores).

## Method (version 1.0.0)

- Every bond-day in the 20 calendar days to the day scored on which the bond had both a quote in the curve and a
  trade.
- The median of those gaps, reported only when there are at least 8.
- Not split by maturity: in the old tool's out-of-sample test, maturity buckets predicted the next quarter's gap
  worse (10.9 bp mean absolute error) than one blended figure (9.2 bp). The 20-day window was chosen the same way.

## Limits

The gap has ranged over more than 140 bp in this history, and a 20-day median of a few dozen observations moves
with it. It describes a recent regime, not a precise level.

## Parity

Version 1 reproduces the old tool's `execution.gap()` for every curve day (209 days) exactly. Report:
`docs/migration/parity-bonds.json`.
