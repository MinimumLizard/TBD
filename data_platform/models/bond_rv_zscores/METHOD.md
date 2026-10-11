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

Pairs: the residual spread (bond a minus bond b) is scored the same way. A pair is formed when the two bonds'
median maturities are within 2 years of each other, or when both have ever been auctioned (benchmark issues are
compared across the curve). Pairs need at least 31 common days.

The model also measures, from its own history, how far pair spreads moved back toward their window mean 10
business days after a z-score of at least 2 and at least 3. These figures are stored for research and are not
shown on the site (config/entitlements.yaml).

## Limits

- One sample, one market regime. Over a few hundred days a 60-day window is a short history.
- The residuals inherit the curve's limits, including its whole-sample λ.

## Versions

- **1.1.0 (current):** the same method, reading version 2 of the curve (every two-way quote, decision 0014).
  Bonds that only version 2 fits (the restructuring bonds) appear here too.
- **1.0.0 (reference):** reads version 1 of the curve and reproduces the old tool; kept running beside 1.1.0.

## Parity

Version 1 reproduces the old tool's per-bond scores (9,285 rows), pair scores (86,829 rows) and both reversion
figures; the largest difference is about 1e-12. Report: `docs/migration/parity-bonds.json`.
