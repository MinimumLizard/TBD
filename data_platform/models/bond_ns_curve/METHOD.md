# LKR government bond yield curve (bond_ns_curve)

## What it shows

One smooth yield curve per day, fitted to the dealers' quoted yields, and each bond's residual: how far its quoted
yield sits above (positive) or below (negative) the curve, in basis points. Trades are compared with the same
curve afterwards, as a daily check on how well quotes describe where business is done.

## Inputs

Each day's resolved quotes (`bond_identity`) and the PDMO trade summary for the same day.

## Method (version 1.0.0)

The Nelson-Siegel curve gives the yield of a bond with τ years to maturity as

    y(τ) = β0 + β1·f1(τ) + β2·f2(τ),   f1 = (1 − e^(−τ/λ)) / (τ/λ),   f2 = f1 − e^(−τ/λ)

β0 is the long-run level, β0 + β1 the very short end, β2 the hump, and λ where the hump sits.

- λ is fixed at 2.82179 years, the value the old tool calibrated once over its whole sample and then held fixed.
  With λ fixed the curve is a weighted linear regression, which has one exact answer and cannot fail to converge.
- The fit uses quote mids, (bid + offer) / 2, for bonds with at least 0.08 years (about a month) to maturity.
  Step-coupon bonds are left out. A day needs at least 6 bonds.
- Each quote is weighted by 1 / spread², where spread is its bid-offer width in bp, floored at 1 bp and capped at
  300 bp; a missing spread takes the day's median. Weights are scaled to average 1. Wide quotes carry little
  weight; this choice does more for the fit than any other.
- τ is calendar days to maturity / 365.25: the curve is a yield-to-maturity curve, not a cash-flow curve.
- Trades (weighted-average yields of bonds that traded) are held out of the fit. Each day stores how many there
  were, their root-mean-square error against the curve, and their median error (the trade bias).

## Method (version 2.0.0, current; decision 0014)

Identical, except that it fits every two-way quote from `bond_identity` version 2, step-coupon and administered
bonds included. Each quote keeps its 1/spread² weight, so a 100 bp administered quote counts about 1/40th as much
as a typical 16 bp one: it is in the fit without being able to pull the curve far. One-way quotes have no mid and
cannot be fitted; the bond page shows them with that note.

Measured effect over the 210 days both versions fitted (`python -m data_platform.models.bond_ns_curve.compare
1.0.0 2.0.0`, 2026-10-11):

| | version 1 | version 2 |
|---|---|---|
| bonds in the fit, per day (mean) | 52.5 | 92.1 |
| weighted error on its own quotes (median) | 9.48 bp | 26.32 bp |
| weighted error on version 1's quotes (median) | 9.48 bp | 9.84 bp |
| curve move at version 1's bonds | | median 2.7 bp, 95th percentile 7.1 bp |
| error against executed trades (median) | 21.39 bp | 19.47 bp |
| trade bias (median) | 16.01 bp | 13.40 bp |

The error on its own quotes rises because the administered quotes sit far from any curve; on the bonds both versions
fit, the curve is almost unchanged, and it is slightly closer to where trades actually printed. Version 1 keeps
running beside it as the reference series that matches the old tool.

## Limits

- λ was chosen using the whole sample, including days after any given date. A test of how the residuals behaved
  over time therefore uses a little information from the future.
- Quotes are averages across primary dealers of indicative prices; nobody is obliged to deal on them. Executed
  yields have run above the quote mids for most of the history (see the trade bias and `bond_execution_gap`).
- In version 1, restructuring bonds and one-way quotes are not in the fit. Version 2 (current) fits every two-way
  quote; one-way quotes have no mid and are not fitted in either version.

## Parity

Version 1 reproduces the old tool's `curve_fits` (210 days) and `curve_residuals` (13,414 rows); the largest
difference is about 1e-12. Report: `docs/migration/parity-bonds.json`.
