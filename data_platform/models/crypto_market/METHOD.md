# Crypto prices, returns and drawdowns (crypto_market)

## What it shows

For bitcoin, ether and other large crypto-assets, priced in US dollars, and for ether priced in bitcoin (ETH/BTC):
each day's closing price, how much it has changed over a day, a week, a month and a year, how far it is below the
highest close so far, how long ago that high was, and how much the price has been moving (realised volatility).

These are descriptions of past prices. They are not forecasts and say nothing about what prices will do.

## Inputs

Bitstamp's daily candles (`crypto.ohlc_daily`), one per pair per UTC day (00:00 to 24:00 UTC). The close is the last
traded price of the UTC day on Bitstamp. Only finished days are stored.

| Pair | Bitstamp history from |
|---|---|
| BTC/USD | 2011-09-14 |
| XRP/USD | 2016-12-16 |
| LTC/USD | 2017-06-16 |
| ETH/USD, ETH/BTC | 2017-08-16 |
| LINK/USD | 2020-10-19 |
| ADA/USD | 2021-11-17 |
| AVAX/USD | 2022-03-08 |
| SOL/USD, DOT/USD | 2022-08-18 |
| DOGE/USD | 2022-12-21 |

**History starts where Bitstamp's does.** Bitcoin traded before 2011-09-14 (the 2011 high in June is not in this
data), and every asset traded elsewhere before Bitstamp listed it. So "the highest close so far" means the highest
Bitstamp close since that date.

## Method (version 1.0.0)

For a pair with daily closes P, on day D:

- **Returns** over k days, for k = 1, 7, 30 and 365: P(D) / P(D − k) − 1, where P(D − k) is the close k calendar
  days earlier (the last close on or before that day, should a day ever be missing). None until the pair has k
  days of history.
- **Highest close to date**: H(D) = the largest close from the pair's first day to D, and the first day it was
  reached. **Drawdown** = P(D) / H(D) − 1 (0 on a day that sets a new high). **Days since the high** = D minus that
  day.
- **Realised volatility** over n = 30 and 90 days: the sample standard deviation (n − 1 in the denominator) of the
  last n daily log returns r = ln(P(t) / P(t − 1)), multiplied by √365, because crypto trades every day of the year.
  None until n returns exist.
- **ETH/BTC** is Bitstamp's own ETH/BTC market, not a ratio of the two dollar prices. It is treated as any other
  pair; its close is in bitcoin.

Every value for day D uses closes up to D only, so a day's row does not change when later days arrive (tested).

## Limits

- One exchange. Prices on other venues differ, by a little most of the time and by more in fast markets.
- Closes, not intraday highs: the highest close is lower than the highest traded price.
- Price only: nothing here measures market size, holders, or any on-chain activity.

## Sources

Bitstamp, https://www.bitstamp.net/api/ (OHLC data). Bitstamp's commercial terms need a signed Data License
Agreement, which is pending; until it is signed this section is a prototype for the owners' preview.
