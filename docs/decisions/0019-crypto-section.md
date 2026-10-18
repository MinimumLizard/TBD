# 0019 — A crypto section, built from public methods on Bitstamp prices

- **Date:** 2026-10-18
- **Status:** Built as a prototype for the owners' preview (the owner asked for it on 2026-10-18). Not public until the
  data licence is signed and a lawyer has read the pages.

## Decision

1. **Source: Bitstamp only** (`config/sources.yaml`, `bitstamp`). Daily candles for BTC, ETH, XRP, LTC, SOL, ADA, LINK,
   DOGE, AVAX and DOT in US dollars, and ETH in bitcoin, from 2011-09-14 (bitcoin) and each asset's Bitstamp listing.
   Collected daily at 00:17 UTC (repair run 06:17 UTC), only finished UTC days, append-only, with the usual raw
   archive. Every price on the pages is in US dollars (ETH/BTC in bitcoin).
2. **Licence status: permission required.** Bitstamp's terms need a signed commercial Data License Agreement
   (partners@bitstamp.net; draft request in `docs/letters/data-permission-requests.md`). The source is enabled for
   development, stays `permission_required`, and so appears in `sources.launch_blockers()`. Every crypto page says
   "Prototype: the data licence for this section is pending".
3. **Models, from published definitions only** (each with a METHOD.md giving the formulas and sources):
   - `crypto_market` 1.0.0 — returns, the fall from the highest close, days since it, realised volatility; ETH/BTC.
   - `crypto_cycle` 1.0.0 — 50/200-day and 200/20-week averages, the 21-week EMA, the Mayer multiple, the Pi cycle
     lines and their crossing days, halvings, each epoch's peak and low (the ends of its largest fall), monthly
     returns.
   - `crypto_trend_bands` 1.0.0 — a log regression and a power law of bitcoin's price, re-fitted every day on the data
     to that day, with ±1 and ±2 standard-deviation bands and the "position between the fitted bands".
   Every row for day D uses data up to D only (tested), so history shown on the site is what was known then.
4. **Tiers** (`config/entitlements.yaml`, the owner can change them): `crypto_market` free; `crypto_cycle` Plus with a
   7-day free preview; `crypto_trend_bands` Pro.
5. **Framing.**
   - Neutral, descriptive names only. Nothing is named after, or imitates, any paid crypto-research service; no
     "risk" score, no zones, no entry or exit language, nothing promotional, no exchange links, no "how to get
     crypto". The 0–1 number is "position between the fitted bands", described as where the price sits, never as risk.
   - A `crypto_risk` disclaimer (compliance/disclaimers.yaml) at the top of every crypto page. It cites the CBSL: crypto
     is not legal tender; the CBSL has licensed no entity to operate crypto schemes; and its 2023 statement that
     crypto is not recognised as an asset class in Sri Lanka.
   - The copy lint covers all of it, code included.
6. **Cross-checked, not tuned:** `docs/research/crypto-crosscheck.md` (30 checks against public reference points, all
   met, each difference explained), re-runnable with `python -m data_platform.jobs.crosscheck_crypto`.

## Deferred

- **On-chain measures** (MVRV, realized price, supply in profit, Puell multiple, exchange flows): they need licensed
  on-chain data or our own Bitcoin node (about 2 TB of SSD and a small server). Not started.
- **Market capitalisations, dominance, an altcoin index, the "flippening" ratio:** they need a paid aggregator with a
  commercial licence, such as CoinMarketCap's Startup plan (USD 79/month).
- **Sentiment** (alternative.me Fear & Greed): allowed with attribution; not added yet.
- **RSI, MACD, Bollinger bands, rolling correlations, quarterly returns:** public methods, computable from these
  prices; left for a later version.
- **Hourly data:** Bitstamp serves it; the section uses daily closes only.

## Before anything is public

- Bitstamp's Data License Agreement signed, and the source's status changed to `allowed`.
- A Sri Lankan lawyer's view on the pages, given the CBSL's 2023 statement urging those "engaged in promoting and
  facilitating the promotion of investing and trading in cryptocurrency to refrain from such activities"
  (`docs/research/data-sources-2026-10-18.md`), and on publishing the band position at all
  (`docs/research/crypto-itc-review.md`, point 4).

**Note (2026-10-18, at merge):** the trend-band model was first named `crypto_fair_value`. It was renamed
`crypto_trend_bands` before any production run, because "fair value" reads as a valuation and so sits too close to a
price target (hard rule 4) even in an identifier. Its output table was already `models.crypto_trend_band`.
