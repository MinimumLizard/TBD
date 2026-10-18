# Into The Cryptoverse (ITC): what it offers, what is public, what to avoid (2026-10-18)

Research for the owner's request to build crypto analytics comparable to ITC's paid tier. Public sources only; nothing
behind the paywall was opened. Raw notes: the session scratchpad (not in git).

## Tiers and prices (homepage pricing table, page modified 2026-03-27; USD, shown "on sale")

| Plan | Monthly | 6 months | Yearly | Lifetime | Includes |
|---|---|---|---|---|---|
| Lite | free | free | free | free | weekly newsletter; log regression for BTC, ETH, total market cap; DCA simulator; heatmap |
| Standard | 49 | 249 | 449 | — | "All risk indicators and historical charts"; risk dashboard; TradingView indicators; portfolio-theory and exit tools; "150+ charts" |
| Pro | 109 | 599 | 1,099 | 12,999 | Standard + 3 weekly videos, private Telegram, macro section, no-code indicator builder; "300+ charts" |
| Direct Access | — | 9,700 / 3 months | — | — | Pro + monthly one-to-one call; five members |

Sources: https://intothecryptoverse.com/ ; https://intothecryptoverse.com/direct-access/ ; tier contents:
https://help.intothecryptoverse.com/support/solutions/articles/69000833996 (2025-07-23, "may be slightly out of date").

## What the paid tiers contain, and whether the method is public

- **Proprietary:** the 0–1 "risk" score per asset and the views built on it (dashboards, colour-coded price, time in
  bands, weighted risk). ITC says only that it is "based off of the fair value regression band and the historical price".
  Inputs, windows, mapping and time adjustment are unknown. **Not to be copied or imitated by name.**
- **Public idea, private settings:** log-regression "fair value" bands (ITC's coefficients, window and band spacing are
  not public); total-market-cap trendlines; "short-term bubble" (probably price vs 20-week SMA); "flippening" ratio.
- **Public methods** (definitions with sources below): running ROI; ROI from halvings, cycle lows and peaks; monthly
  returns; long moving averages incl. the 200-week MA; the 20W SMA / 21W EMA band; RSI, MACD, Bollinger bands, crosses;
  Pi Cycle top and bottom; BTC dominance; altcoin-season index; Fear & Greed (alternative.me); correlations.
- **On-chain (public methods, licensed data):** MVRV, MVRV-Z, supply in profit, Puell multiple, exchange flows, coin
  days destroyed, HODL waves.
- **Pro macro and equities:** public series, mostly FRED (CPI, unemployment, Fed funds, curve spreads, M2, Fed balance
  sheet, NFCI; S&P 500 EPS, P/E, Shiller P/E, dividend yield).

## Public definitions

- **Pi Cycle Top** (P. Swift, 2019): the 111-day SMA crosses above 2 × the 350-day SMA.
  https://www.lookintobitcoin.com/charts/pi-cycle-top-indicator/
- **Pi Cycle Bottom:** the 150-day EMA below 0.745 × the 471-day SMA (only 2015 and 2018 so far; correction
  2026-10-18: a third crossing in July 2022 was reported at the time and is in our data, see `crypto-crosscheck.md`).
- **200-week MA heatmap** (Plan B, 2019): the 200-week MA's month-on-month change. Colour cut-offs are not published.
- **20W SMA / 21W EMA band:** on weekly closes.
- **MVRV Z-score:** (market cap − realized cap) / σ(market cap), with σ over all history to date (Glassnode).
  Short-term holder realized price: coins younger than 155 days.
- **Puell multiple:** daily issuance in USD / its 365-day MA.
- **Altcoin season:** 75% of the top 50 coins (no stablecoins or wrapped tokens) beat BTC over 90 days.
- **Power law** (Santostasi): log10 price = A + B·log10(days since 2009-01-03), A ≈ −17.01, B ≈ 5.82.
- **Halvings:** 2012-11-28, 2016-07-09, 2020-05-11, 2024-04-20 (confirm on a block explorer).

## Reference points for cross-checking our own code (venue-dependent; test with tolerance)

| Event | Date | Price |
|---|---|---|
| 2013 top | 2013-11-29/30 | ~$1,163 (CoinDesk index) to $1,242 (Mt.Gox) |
| 2015 low | 2015-01-14/15 | ~$152–177 |
| 2017 top | 2017-12-17 | ~$19,783 (CoinDesk) to $20,089 intraday |
| 2018 low | 2018-12-15 | ~$3,122 |
| 2021 top | 2021-11-10 | ~$68,789–69,044 |
| 2022 low | 2022-11-21/22 | ~$15,480 |
| 2025 high | 2025-10-06 | ~$126,080–126,270 |

Pi Cycle Top is reported to have crossed near the 2013, 2017 and April-2021 tops, and reportedly not at the
October-2025 top. The 200-week MA was reported at about $61.6–62.4k in late June 2026 and about $63.8k in
August 2026 (±1–2% by source).

## ITC's terms of use (updated 2026-03-18), and what that means for us

Use is "for personal, non-commercial purposes". The terms forbid programmatic extraction and using their output "to
develop models that compete", and forbid copying, derivative works or republishing.

So we:
1. **Never subscribe in order to calibrate against, scrape or systematically compare with ITC.** We cross-check
   against independent public data (the table above) and across independent price sources.
2. **Never reproduce their charts, text, videos, scripts or the risk-score method.**
3. **Never use their names or branding:** "Into the Cryptoverse", "ITC", Cowen's name in marketing, "Risk Metric",
   "Bubble Risk", "Does it Bleed", "Workbench", "Exit Strategies" and similar. We use neutral, descriptive labels.
4. **Avoid entry and exit framing.** "Zones" to accumulate or sell would break hard rule 4. Any 0–1 position score
   is published only as a description ("where the price sits between fitted bands"), and only after a legal view.
5. **Write our code from the published definitions**, not from community TradingView scripts.

## Recommended set (built from public methods, on price data alone)

Moving averages:
- 50/200-day MAs; the 200-week MA and its monthly change; the Mayer multiple.

Cycle indicators:
- the 20W SMA / 21W EMA band and the price's distance above the 20-week SMA;
- Pi Cycle top and bottom crossings.

Fair-value bands:
- log-regression and power-law bands fitted point in time, with their coefficients published.

Returns and risk:
- drawdown from the all-time high;
- running 1-year ROI;
- ROI from each halving, cycle low and peak, and days since the halving;
- cycle overlays;
- monthly and quarterly returns;
- realised volatility;
- rolling correlations;
- RSI, MACD and Bollinger bands;
- ETH/BTC.

Other sources these need:
- **Market-cap data**, for dominance, the altcoin index and the flippening ratio: subject to the data-source research.
- **FRED macro series**, checking each series for third-party copyright.
- **Fear & Greed**, with alternative.me's attribution beside the data.
- **On-chain metrics** need licensed data or our own Bitcoin node: deferred.
