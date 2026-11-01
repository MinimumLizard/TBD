# Walk-forward test of the portfolio lab (cse_lab_backtest)

**Internal research.** Nothing here is shown on the site: every output is unpublished (`config/entitlements.yaml`),
the website's database role cannot read it (migration 0017), and the owner reads it through
`python -m data_platform.jobs.lab_report` (decision 0024). A walk-forward test is not a performance claim; it shows how
written rules would have behaved, with their costs.

## What it computes

What the lab's own rules would have built and held on each past date, using only what was known on that date, from
the first date the rules can run to the latest session; under two rebalancing policies; against the ASPI and treasury
bills. For every review: what entered and left, and why; for every model weight: the measurements that explain it.

## The rules (unchanged from the lab)

- **Universe and estimates** as `cse_risk_estimates` 1.1.0: ordinary shares traded on 80 % of the sessions in the
  year to the date, median daily turnover of Rs 1 mn, a known sector; weekly total returns, Ledoit-Wolf covariance,
  Dimson beta, the CBSL 12-month bill yield as published by the date; CAPM expected returns with an assumed 6 %
  premium (used only by maximum Sharpe).
- **Portfolios** as `cse_portfolio_lab` 1.1.0: minimum variance and maximum Sharpe of the full universe with 10 % per
  share, 30 % per sector, 20 % per ownership group and the liquidity cap for Rs 1 mn; the versions with K = 10 and 15
  names (the K largest weights; a name already held stays while it ranks in the top 1.5 K; re-optimised with a cap of
  max(10 %, 1.5 / K) and a floor of 0.5 / K); equal weight on minimum variance's names.
- **Holding them** as `cse_lab_record` 1.1.0: Rs 1 mn each, whole shares, 1.12 % of each trade's value, dividends,
  splits, scrip and rights booked on their ex-date, changes under Rs 2,500 skipped, and the drift band (a name more
  than max(25 % of its target, 2 points) from its target goes back to it at the next session).

## The start, and the walk forward

- **Start**: the first session on which the estimates can be made: at least 26 weekly returns (the lab's preview
  rule) and a published bill yield. Until a full year of weekly returns exists, each date uses all the weeks available
  (at least 26), and is marked as a preview.
- **Point in time**: each date's universe, estimates and portfolios read only facts up to that date
  (`cse_estimates.run_date`); prices and corporate actions on a session are those known by that session (the record's
  `Pricer`). Tested: the rows up to a date do not change when later data arrives.

## The rebalancing policies

1. **Quarterly** (the lab's rule): new model weights on the first session of January, April, July and October; the
   drift band in between.
2. **Dynamic**: a check on the first session of every month. The rules' portfolio is built afresh; the holdings are
   rebalanced to it when their **estimated tracking error** against it, √((w − w*)′ Σ (w − w*)) on the date's
   covariance, exceeds **3 % a year**, or when a holding has left the universe; on the quarterly dates always. The
   drift band in between.

## Benchmarks

- **Market**: Rs 1 mn in ASPI index units. The ASPI is a price index: it leaves out dividends, so it understates the
  market's return by the dividends paid. The ASPI total-return index is stored only from October 2026.
- **Bills**: Rs 1 mn growing at the 12-month treasury bill yield in force (as published), day by day.

## Outputs

- `models.cse_bt_summary`: per policy and portfolio: start and end, value, total return, annualised volatility of
  daily values, the largest fall from a peak, the best and worst months, the number of rebalances and drift repairs,
  turnover (value traded after the start ÷ the average value), costs, names at the end.
- `models.cse_bt_nav`: per session, policy and portfolio: value, cash, number of names.
- `models.cse_bt_event`: each rebalance (inception, scheduled, threshold) and drift repair: the tracking error that
  triggered it, names in and out, the weeks of data, preview or not, what binds, the model's estimated volatility,
  the median volatility of the universe, value traded and cost.
- `models.cse_bt_target`: the rules' weights on each date they were computed (applied or, for the dynamic policy's
  monthly checks, only compared), and on the latest session ("today", shown, not applied): weight, risk contribution,
  volatility, beta, average correlation with the other names, sector, ownership group, at the cap or the floor, its
  rank in the full portfolio, whether it was in the previous portfolio.
- `models.cse_bt_trade`: every change of shares and every corporate action, with its cost and reason.

## Limits (they go with every use of these numbers)

- **Short.** The CSE's public price history reaches back one year, so the test starts in April 2026 with about six
  months of results. Over six months the market's direction dominates; differences of a few points between methods
  are within chance. The test lengthens by itself as the history grows; the CSE's historical data (part of the data
  permission request) would allow a multi-year test.
- **Previews.** Until October 2026 the estimates use 26 to 51 weekly returns, not a full year.
- **Survivorship.** The list of listed securities, sector labels and ownership groups are recorded only from October
  2026 and are used as first recorded for earlier dates: a company delisted before then is missing, and the group caps
  use October's groups.
- **Costs and prices.** Closing prices; no market impact beyond the stated cost; the cost per side is to be checked
  against the current CSE schedule; no tax on dividends.
- These are rules applied to public data, for research and education. They are not advice and say nothing about any
  share's future price.

## Versions

**1.0.0** (2026-11-01): first version.
