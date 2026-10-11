# Bond residuals against their own history (bond_rv_zscores)

## What it shows

A bond's residual (its distance from the fitted curve) is partly permanent: some bonds always sit a little above
or below the curve. This model compares each bond's residual with that bond's own recent residuals, and does the
same for the residual spread between pairs of nearby bonds. A z-score of +2 means the residual is two standard
deviations above that bond's (or pair's) own recent average.

This is a description of the data under stated assumptions. It is not a forecast, and it is not a suggestion to
deal in any bond.

## Inputs

The quote residuals from `bond_ns_curve`; auction results and announcements (to know which bonds have ever been
auctioned).

## Method (version 1.0.0)

For each bond, on each day:

    z = (residual today − mean of the window) / standard deviation of the window

- The window is the 60 previous observations of that bond, not including the day scored, so no z-score has seen
  the value it scores. At least 30 are needed. A standard deviation under 0.5 bp gives no z-score.
- deviation_bp = residual − window mean: the same comparison in basis points, since a large z on a tiny standard
  deviation is a small number of basis points.

Pairs: the residual spread (bond a minus bond b) is scored the same way, against the pair's own previous 60
common observations (at least 30). A pair is shown on a day when, on that day, the two bonds' maturities are within
2 years of each other, or both had been auctioned by then (benchmark issues are compared across the curve).

The model also computes some research statistics from its own history. They are not published.

## Limits

- One sample, one market regime. Over a few hundred days a 60-day window is a short history.
- The residuals inherit the curve's limits, including its whole-sample λ.

## Versions

- **1.1.0 (current):** reads version 2 of the curve (every two-way quote, decision 0014), so the restructuring
  bonds appear here too. Every pair row uses only what was known on its day: each bond's maturity on that day,
  and pair membership as of that day. A row, once computed, never changes when later days arrive.
- **1.0.0 (reference):** reads version 1 of the curve and reproduces the old tool, which labelled each pair with the
  bonds' median maturity over all history and formed pairs from all history; kept running beside 1.1.0.

## Parity

Version 1 reproduces the old tool's per-bond scores (9,285 rows), pair scores (86,829 rows) and both reversion
figures; the largest difference is about 1e-12. Report: `docs/migration/parity-bonds.json`.
