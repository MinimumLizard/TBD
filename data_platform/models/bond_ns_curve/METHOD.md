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

## Limits

- λ was chosen using the whole sample, including days after any given date. A test of how the residuals behaved
  over time therefore uses a little information from the future.
- Quotes are averages across primary dealers of indicative prices; nobody is obliged to deal on them. Executed
  yields have run above the quote mids for most of the history (see the trade bias and `bond_execution_gap`).
- Restructuring bonds and one-way quotes are not in the fit (decision 0014 plans a version 2 that includes every
  two-way quote at its 1/spread² weight).

## Parity

Version 1 reproduces the old tool's `curve_fits` (210 days) and `curve_residuals` (13,414 rows); the largest
difference is about 1e-12. Report: `docs/migration/parity-bonds.json`.
