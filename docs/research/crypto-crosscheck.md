# Crypto section: cross-checks against independent public reference points (2026-10-18)

What was checked, against what, and how well it agreed. The references are the public points listed in
`docs/research/crypto-itc-review.md`, plus the other public sources named in each row. **Nothing was tuned to them**:
every setting in the models is the published definition, fixed before the comparison.

**How the numbers were measured** (on the dev database, Bitstamp history collected 2026-10-18 to the 2026-10-17
close):

```
uv run python -m data_platform.jobs.collect bitstamp           # 66 requests, 29,329 daily candles
uv run python -m data_platform.jobs.models --market crypto
uv run python -m data_platform.jobs.crosscheck_crypto          # the table below; exit 1 if any check fails
CROSSCHECK_DATABASE_URL=<that database> uv run pytest tests/test_crypto_crosscheck.py   # the same, as tests
```

The history is never committed (the repository is public and Bitstamp's data needs a licence), so CI skips
`tests/test_crypto_crosscheck.py`. Re-run it after each change to a crypto model.

## Result: 30 checks, 0 failures (2 rows are information only)

| Group | Check | Measured | Reference | Tolerance | Result | Note |
|---|---|---|---|---|---|---|
| Pi cycle | 111/350 crossing near the 2013 top | 2013-12-05 | 2013-11-29/30 | within 21 days | pass | 5 day(s) from the nearest reference date |
| Pi cycle | 111/350 crossing near the 2017 top | 2017-12-16 | 2017-12-17 | within 21 days | pass | 0 day(s) from the nearest reference date |
| Pi cycle | 111/350 crossing near the April 2021 top | 2021-04-12 | 2021-04-13/14 | within 21 days | pass | 1 day(s) from the nearest reference date |
| Pi cycle | No 111/350 crossing at the October 2025 high | none | reportedly no crossing at the 2025-10-06 high | none after mid-2021 | pass |  |
| Pi cycle | Other 111/350 crossings | 2013-04-05 | the April 2013 high (2013-04-09/10 on Mt.Gox) is also a widely reported crossing | information | info | near the first 2013 high; not a reference in the review |
| Pi cycle | 150/471 crossing near the January 2015 low | 2015-01-14 | 2015-01-14 | within 21 days | pass | 0 day(s) |
| Pi cycle | 150/471 crossing near the December 2018 low | 2018-12-16 | 2018-12-15 | within 21 days | pass | 1 day(s) |
| Pi cycle | 150/471 crossing in July 2022 | 2022-07-13 | reported by Cointelegraph on 2022-07-12 as about to cross ('the third Pi Cycle bottom') | within 7 days | pass | the review's 'only 2015 and 2018 so far' predates it |
| Pi cycle | pi_ema_150 on 2022-07-12 | $32,161 | $32,332 (Cointelegraph) | ±3% (another venue) | pass | -0.53% |
| Pi cycle | pi_sma_471x0745 on 2022-07-12 | $32,154 | $32,208 (Cointelegraph) | ±3% (another venue) | pass | -0.17% |
| 200-week average | 21–30 June 2026, range | $62,243 – $62,643 | $61.6k – $62.4k (late June 2026, by source) | ±3% of the reference range | pass | +1.0% to +0.4% against the range's ends |
| 200-week average | 15 August 2026 (August range) | $63,997 ($63,547 – $64,860) | about $63.8k (August 2026) | ±3% | pass | +0.31% |
| Cycle table | cycle peak, epoch 1 | 2013-12-04 close $1,132; intraday high ±3 days $1,153 | 2013 top: ~$1,163 (CoinDesk) to $1,242 (Mt.Gox) | date ±7 days; price ±5% (close or intraday) | pass | 4 day(s) from the reference date |
| Cycle table | cycle low, epoch 1 | 2015-01-14 close $171.41; intraday low ±3 days $152.40 | 2015 low: ~$152–177 | date ±7 days; price ±5% (close or intraday) | pass | 0 day(s) from the reference date |
| Cycle table | cycle peak, epoch 2 | 2017-12-16 close $19,188; intraday high ±3 days $19,666 | 2017 top: ~$19,783 (CoinDesk) to $20,089 intraday | date ±7 days; price ±5% (close or intraday) | pass | 1 day(s) from the reference date |
| Cycle table | cycle low, epoch 2 | 2018-12-15 close $3,180; intraday low ±3 days $3,122 | 2018 low: ~$3,122 | date ±7 days; price ±3% (close or intraday) | pass | 0 day(s) from the reference date |
| Cycle table | cycle peak, epoch 3 | 2021-11-08 close $67,559; intraday high ±3 days $69,000 | 2021 top: ~$68,789–69,044 | date ±7 days; price ±3% (close or intraday) | pass | 2 day(s) from the reference date |
| Cycle table | cycle low, epoch 3 | 2022-11-21 close $15,766; intraday low ±3 days $15,479 | 2022 low: ~$15,480 | date ±7 days; price ±3% (close or intraday) | pass | 0 day(s) from the reference date |
| Cycle table | cycle peak, epoch 4 | 2025-10-06 close $124,728; intraday high ±3 days $126,272 | 2025 high: ~$126,080–126,270 | date ±7 days; price ±3% (close or intraday) | pass | 0 day(s) from the reference date (provisional) |
| Halvings | halving 1 (block 210,000) | 2012-11-28 | 2012-11-28 (block header time, blockstream.info, read 2026-10-18) | same UTC date | pass |  |
| Halvings | halving 2 (block 420,000) | 2016-07-09 | 2016-07-09 (block header time, blockstream.info, read 2026-10-18) | same UTC date | pass |  |
| Halvings | halving 3 (block 630,000) | 2020-05-11 | 2020-05-11 (block header time, blockstream.info, read 2026-10-18) | same UTC date | pass |  |
| Halvings | halving 4 (block 840,000) | 2024-04-20 | 2024-04-20 (block header time, blockstream.info, read 2026-10-18) | same UTC date | pass |  |
| BTC closes | 2016-12-31 | $966.30 | 2016 year-end: ~$960–1,000 (press, walletinvestor) | ±3% | pass | inside the range |
| BTC closes | 2019-12-31 | $7,168 | 2019 year-end: ~$7,183–7,193 (press) | ±3% | pass | -0.20% from the range |
| BTC closes | 2020-12-31 | $28,993 | 2020 year-end: ~$29,000–29,244 (walletinvestor, substack) | ±3% | pass | -0.02% from the range |
| BTC closes | 2023-12-31 | $42,258 | 2023 year-end: $42,265 (walletinvestor) | ±3% | pass | -0.02% from the range |
| BTC closes | 2024-12-31 | $93,381 | 2024 year-end: $93,429 (walletinvestor) | ±3% | pass | -0.05% from the range |
| Consistency | ETH/BTC vs ETH/USD ÷ BTC/USD, 3212 days from 2018 | median 0.057%, 99th percentile 0.44% | the two should agree closely | median under 0.5% | pass | three separate Bitstamp markets |
| Power law | fit on 2026-10-17 (A, B) | A = -16.20, B = 5.599 | A ≈ −17.01, B ≈ 5.82 (Santostasi, data from 2010) | information | info | our line $139,395 vs the published line $151,217 on that day (-7.8%); our data starts in September 2011 |

Year-end references: [walletinvestor annual table](https://walletinvestor.com/currency/bitcoin),
[Binance Square](https://www.binance.com/en/square/post/4304019141018), [Ruen substack](https://ruen.substack.com/p/bitcoin-year-on-year-incl-aths),
[MEXC news](https://www.mexc.com/news/641945). Pi cycle 2022: [Cointelegraph, July 2022](https://cointelegraph.com/markets/bitcoin-price-indicator-that-marked-2015-and-2018-bottoms-is-flashing).
No independent year-end figure was found in the research notes or the search for 2011–2015, 2017–2018, 2021–2022
and 2025; the cycle-table rows cover those years' highs and lows instead.

## Where our measurement and a reference differ, and why

1. **The 2013 peak is dated 2013-12-04, the references say 2013-11-29/30.** Bitstamp's close on 2013-11-29 was
   $1,131.99 and on 2013-12-04 $1,132.01: two cents apart, so the "highest close" falls on the later day. The index
   reference ($1,163) is CoinDesk's, and the $1,242 is Mt.Gox's, which traded at a premium in 2013. Venue and
   close-versus-intraday, not a method difference. The Pi crossing (2013-12-05) is within a week of both.
2. **Closes are below the quoted tops.** References for tops (2017: $19,783–20,089; 2021: $68,789–69,044; 2025:
   $126,080–126,270) are intraday highs or index values. Bitstamp's closes are lower ($19,188; $67,559; $124,728), and
   its intraday highs on the same days match ($19,666; $69,000; $126,272). The 2021 close peak (2021-11-08) is two
   days before the intraday high (2021-11-10).
3. **A third Pi cycle bottom crossing, in July 2022.** The review says "only 2015 and 2018 so far", which reflects
   the indicator page's text from before 2022. Cointelegraph reported on 2022-07-12 that the 150-day EMA ($32,332) was
   about to fall below 0.745 × the 471-day average ($32,208); we measure $32,161 and $32,154 that day and a crossing on
   2022-07-13. So our result agrees with a contemporary report; the review's line is out of date and has been noted
   here rather than changed in the model.
4. **An April 2013 Pi top crossing (2013-04-05)** is not in the review's list, but the April 2013 high is widely
   reported as one of the indicator's crossings. Shown as information.
5. **The power law's coefficients differ from Santostasi's** (A −16.20, B 5.60 against −17.01, 5.82). Ours is fitted
   to Bitstamp's closes from September 2011 only, while the published fit includes 2010 and early 2011, when prices
   were far lower. On 2026-10-17 our line is 7.8% below the published one. The fit also drifts as history grows,
   because it is re-fitted point in time (below). Not tuned: the gap is the honest result of the shorter history.
6. **The 200-week average convention.** On a Sunday our value equals the average of the last 200 Sunday closes
   (2026-06-28: $62,442 both ways). Mid-week it uses the day's close for the unfinished week, as a weekly chart does;
   the difference between the two conventions is at most 1/200 of a week's price change. Late-June 2026 values
   ($62,243–62,643) sit at or a little above the top of the reported range ($61.6–62.4k), within 1%; mid-August
   ($63,997) is 0.3% from the report.

## Point-in-time fits drift; the site says so

The trend bands are re-fitted every day on the data to that day (`models.crypto_trend_band`):

| Day | Power law exponent B | Log regression exponent b | Power-law line | Position (power law) |
|---|---|---|---|---|
| 2013-12-04 | 7.918 | 7.523 | $166 | 1.331 |
| 2017-12-16 | 5.609 | 5.843 | $2,802 | 1.109 |
| 2021-11-08 | 5.929 | 5.968 | $29,467 | 0.790 |
| 2025-10-06 | 5.686 | 5.792 | $108,947 | 0.552 |
| 2026-10-17 | 5.599 | 5.735 | $139,395 | 0.291 |

(`psql ... -c "select day, fit, slope, fitted, position from models.crypto_trend_band where pair='btcusd' and day in (...)"`.)
A line fitted in late 2013 had an exponent near 8; by 2017 it was under 6. That is exactly why each day's line is
stored as it was then: a chart that redraws history with today's line would make the past look better described than
it was. The method page states the drift as a limit.

## Data integrity

- **Re-download:** a separate download of every pair's full history, made the same day with a different client
  (`urllib`, exploration script in the session scratchpad), was compared field by field with what the collector
  stored: 29,329 of 29,329 candles identical (open, high, low, close, volume).
- **No gaps:** every pair has a candle for every day from its first to 2026-10-17 (the collector's run message; the
  gap check `crypto.ohlc_daily` entry also passes).
- **Consistency:** Bitstamp's own ETH/BTC market agrees with ETH/USD ÷ BTC/USD to a median 0.057% (table above).

## Rows collected

`select pair, count(*), min(day), max(day) from crypto.ohlc_daily group by 1`:

| Pair | Days | From | To |
|---|---|---|---|
| btcusd | 5,513 | 2011-09-14 | 2026-10-17 |
| xrpusd | 3,593 | 2016-12-16 | 2026-10-17 |
| ltcusd | 3,411 | 2017-06-16 | 2026-10-17 |
| ethusd | 3,350 | 2017-08-16 | 2026-10-17 |
| ethbtc | 3,350 | 2017-08-16 | 2026-10-17 |
| linkusd | 2,190 | 2020-10-19 | 2026-10-17 |
| adausd | 1,796 | 2021-11-17 | 2026-10-17 |
| avaxusd | 1,685 | 2022-03-08 | 2026-10-17 |
| solusd | 1,522 | 2022-08-18 | 2026-10-17 |
| dotusd | 1,522 | 2022-08-18 | 2026-10-17 |
| dogeusd | 1,397 | 2022-12-21 | 2026-10-17 |

ETH's first Bitstamp day (2017-08-16) is a single trade at $300 (volume 0.02 ETH): kept, as the record shows it.
