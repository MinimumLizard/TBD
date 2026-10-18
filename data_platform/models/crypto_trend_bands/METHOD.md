# Bitcoin long-run trend bands (crypto_trend_bands)

## What it shows

Two straight-line trends through bitcoin's whole price history drawn on logarithmic axes, with bands around each
at one and two standard deviations of the price's distance from the line. The **position between the fitted bands**
is where today's close sits between the lower and upper outer band: 0 at the lower band, 1 at the upper, 0.5 on
the line (below 0 or above 1 when the price is outside the bands).

The lines summarise how the price has grown so far. They are not a value the price should have, they are not a
forecast, and a position near 0 or 1 is not a signal of anything. The fitted lines move as each day is added.

## Inputs

Bitstamp's daily BTC/USD closes, from 2011-09-14 (`crypto.ohlc_daily`). **The history starts where Bitstamp's does**:
bitcoin's prices from 2010 to September 2011, which published versions of these fits include, are not in it.

## Method (version 1.0.0)

t is the number of days from the genesis block (2009-01-03) to the day of the close, P the close.

| Fit | Line | Weights | Units of intercept, slope and σ |
|---|---|---|---|
| **Log regression** | ln P = a + b·ln t | each day weighted 1/t | natural logs |
| **Power law** | log₁₀ P = A + B·log₁₀ t | every day weighted equally | base-10 logs |

Both are least-squares fits of log price on log time, so both are straight lines on log-log axes (and b and B are
both the exponent of t: a power law). They differ in how much each part of the history counts:

- **power law** (the form published by G. Santostasi, with A ≈ −17.01 and B ≈ 5.82 on data from 2010): ordinary
  least squares, every day counts once. Because there are many more recent days than early ones, recent years
  dominate the fit;
- **log regression**: weighted least squares with weight 1/t, which gives every equal stretch of log-time the same
  total weight, so the early years count as much as the recent ones.

**Re-fitted point in time.** On each day D both fits use only the closes from 2011-09-14 to D, and that day's
coefficients are stored with it. Day D's row therefore never changes when later days arrive (tested); the fit is
computed from running sums of the weighted x, y, x², xy and y², and equals a direct least-squares fit of the same
closes (tested). No fit is made before 365 closes exist (the first is on 2012-09-12).

**Bands.** σ(D) is the residual standard deviation of that day's fit: √(Σw·e² / Σw × n / (n − 2)), with e the
residuals in the fit's log units (equal weights give the usual √(Σe² / (n − 2))). With m(D) the fitted log price:

- fitted line: m(D); bands at m(D) ± 1σ and m(D) ± 2σ, converted back to US dollars;
- **position between the fitted bands** = (log P(D) − (m(D) − 2σ)) / (4σ).

## Limits

- One exchange's closes, and a history that starts in September 2011.
- A straight line on log-log axes is a summary of the past. Its slope has drifted as the history grew, and it can
  keep drifting; the bands assume the distances from the line behave alike over time, which they have not exactly.
- The two lines differ mainly in how they weight the early years; their gap is itself a measure of how uncertain
  any such line is.

## Sources

- Bitstamp OHLC data: https://www.bitstamp.net/api/ . Commercial use needs a signed Data License Agreement, which
  is pending; until it is signed this section is a prototype for the owners' preview.
- Power law: G. Santostasi, "The Bitcoin Power Law Theory" (2024 and earlier public posts).
- Weighted least squares: any regression text (e.g. Weisberg, *Applied Linear Regression*, ch. 7).
