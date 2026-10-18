# Crypto cycles and long averages (crypto_cycle)

## What it shows

For bitcoin, ether and the other crypto-assets in US dollars: long moving averages of the price, how far the price is from them, two pairs
of lines known publicly as the Pi cycle indicators and the days they crossed, the bitcoin halvings, the peaks and
lows of each four-year epoch between halvings, the change since each, and the return of every calendar month.

All of these describe the past. Some of these lines crossed close to past highs and lows; that is a description of
what happened, a handful of times, and not evidence that it will happen again. Nothing here is a forecast.

## Inputs

Bitstamp's daily closes for every US-dollar pair collected (`crypto.ohlc_daily`; BTC/USD from 2011-09-14, ETH/USD
from 2017-08-16, the others later: see the crypto prices method). The close is the last trade of the UTC day. **The
history starts where Bitstamp's does**, so the 2011 bitcoin high (June 2011) and anything before 2011-09-14 are not in
it, and every other asset starts at its Bitstamp listing. The halvings are bitcoin events; for other assets the epochs
between them are used as the same calendar periods. The Pi cycle settings were published for bitcoin.

## Method (version 1.0.0)

Notation: P(D) is the close on day D; SMA_n is the simple average of the last n daily closes (none until n exist);
EMA_n is the exponential average with α = 2 / (n + 1), started from the simple average of the first n closes.

**Daily averages**
- SMA_50 and SMA_200.
- **Mayer multiple** = P(D) / SMA_200(D) (Trace Mayer, 2013).

**Weekly averages** (weeks run Monday to Sunday, UTC; a week's close is its Sunday close). On day D the latest week is
the one D falls in, with P(D) as its close so far, as a weekly chart shows it:
- SMA_nw(D) = (P(D) + the n − 1 previous Sunday closes) / n, for n = 200 and 20.
- EMA_21w(D) = α·P(D) + (1 − α)·(the weekly EMA at the previous Sunday), α = 2 / 22, started from the simple
  average of the first 21 weekly closes.
- **Change of the 200-week average over four weeks** = SMA_200w(D) / SMA_200w(D − 28) − 1 (its month-on-month
  change, the quantity behind Plan B's 2019 "200-week moving average heatmap"; no colour scale is applied here).
- **Distance from the 20-week average** = P(D) / SMA_20w(D) − 1. The 20-week SMA and 21-week EMA are shown together
  as a band.

**Pi cycle lines** (Philip Swift, 2019, published as the "Pi Cycle Top" and "Pi Cycle Bottom" indicators):
- first pair: SMA_111 and 2 × SMA_350. A **crossing** is a day on which SMA_111 > 2 × SMA_350 while the day before it
  was not (both lines defined on both days);
- second pair: EMA_150 and 0.745 × SMA_471. A **crossing** is a day on which EMA_150 < 0.745 × SMA_471 while the day
  before it was not.
The multipliers (2 and 0.745) and windows are the published ones; they were chosen by their author from the
history, which is why past crossings line up with past highs and lows.

**Halvings** (the bitcoin block reward halves every 210,000 blocks). The UTC dates of blocks 210,000, 420,000,
630,000 and 840,000, read from the block headers on a public block explorer (blockstream.info, 2026-10-18):

| Halving | Block | Date (UTC) |
|---|---|---|
| 1 | 210,000 | 2012-11-28 15:24 |
| 2 | 420,000 | 2016-07-09 16:46 |
| 3 | 630,000 | 2020-05-11 19:23 |
| 4 | 840,000 | 2024-04-20 00:09 |

- Days since the latest halving, and the change since it: P(D) / P(halving day) − 1, where P(halving day) is the
  close of the UTC day of the halving. For ether, a halving before its Bitstamp history has no close and no change.

**Epochs, cycle peaks and cycle lows.** Epoch k runs from halving k to the day before halving k + 1 (epoch 0: from the
first close to the day before the first halving). As known on day D:
- an epoch's **cycle peak** and **cycle low** are the two ends of its largest fall so far: the pair of days, peak
  before low, inside the epoch and up to D, with the lowest ratio P(low) / P(peak). Before any fall the peak is the
  highest close so far and there is no low;
- epoch 0 has no peak (Bitstamp's history starts after the June 2011 high); its low is its lowest close so far;
- the highest close of an epoch is *not* used as its peak: in epoch 3 that close came on 2024-03-13, five weeks before
  the next halving, while the epoch's large fall ran from the November 2021 high to the November 2022 low;
- a peak or low in an epoch that has not ended yet can still move. It is marked **provisional**.

For every anchor (halving, peak, low) known on D: the change since it, P(D) / P(anchor) − 1, and the days since it.
In cycle order (low 0, halving 1, peak 1, low 1, halving 2, ...) each anchor also carries its change from the
previous anchor and the days between them.

**Months.** For each calendar month whose last day is in the data: the month's last close and its change from the
previous month's last close. The current month is shown only as the change so far: P(D) / (the previous month's
last close) − 1.

Every value for day D uses closes up to D only, so a day's row does not change when later days arrive (tested).
Crossing days, once recorded, never change for the same reason.

## Limits

- One exchange; closes, not intraday prices. Highs and lows on other venues, or intraday, differ in date and level
  (`docs/research/crypto-crosscheck.md`).
- For assets other than bitcoin, the halvings are only calendar markers, and the Pi cycle settings were never
  chosen for them.
- Four halvings and four cycles are a very small sample. The cycle table describes them; it does not establish a
  rule.
- The Pi cycle settings were fitted to past data by their author, so their record on that same data is not a test.

## Sources

- Bitstamp OHLC data: https://www.bitstamp.net/api/ . Commercial use needs a signed Data License Agreement, which
  is pending; until it is signed this section is a prototype for the owners' preview.
- Pi cycle indicators: P. Swift (2019), https://www.lookintobitcoin.com/charts/pi-cycle-top-indicator/
- 200-week average and its monthly change: Plan B (2019).
- Mayer multiple: T. Mayer (2013).
- Halving blocks: block headers, https://blockstream.info/
