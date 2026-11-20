# Walk-forward test of the portfolio lab (cse_lab_backtest)

**Internal research.** Nothing here is shown on the site: every output is unpublished (`config/entitlements.yaml`),
the website's database role cannot read it (migration 0017), and the owner reads it through
`python -m data_platform.jobs.lab_report` (decision 0024). A walk-forward test is not a performance claim; it shows how
written rules would have behaved, with their costs.

## What it computes

What the lab's own rules would have built and held on each past date, using only what was known on that date, from
the first date the rules can run to the latest session; under two rebalancing policies; against the ASPI and treasury
bills. For every review: what entered and left, and why; for every model weight: the measurements that explain it.

## The rules of version 1.0.0 (unchanged from the lab)

- **Universe and estimates** as `cse_risk_estimates` 1.1.0: ordinary shares traded on 80 % of the sessions in the
  year to the date, median daily turnover of Rs 1 mn, a known sector; weekly total returns, Ledoit-Wolf covariance,
  Dimson beta, the CBSL 12-month bill yield as published by the date; CAPM expected returns with an assumed 6 %
  premium (used only by maximum Sharpe).
- **Portfolios** as `cse_portfolio_lab` 1.1.0: minimum variance and maximum Sharpe of the full universe with 10 % per
  share, 30 % per sector, 20 % per ownership group and the liquidity cap for Rs 1 mn; the versions with K = 10 and 15
  names (the K largest weights; a name already held stays while it ranks in the top 1.5 K; re-optimised with a cap of
  max(10 %, 1.5 / K) and a floor of 0.5 / K); equal weight on minimum variance's names.
- **Holding them** as `cse_lab_record` 1.1.0: Rs 1 mn each, whole shares, 1.12 % of each trade's value, dividends (after
  the final 15 % withholding tax), splits, scrip and rights booked on their ex-date, changes under Rs 2,500 skipped, and the drift band (a name more
  than max(25 % of its target, 2 points) from its target goes back to it at the next session).

## What version 1.1.0 changes (decision 0025)

Three rules differ from version 1.0.0; everything else is the same. Version 1.0.0 keeps running beside it as the
reference, so the two can always be compared on the same dates.

1. **The covariance is estimated from daily returns** (`_lib/cse_covariance.py`, `daily`). With about 140 shares and
   26 to 52 weekly returns, the weekly estimate has far fewer observations than shares. The daily total returns over
   the same span give about five times as many. Thinly traded shares react to news a day or two late, so same-day
   covariances alone understate how shares move together; the covariances of returns one and two days apart are
   added, with Bartlett weights (2/3 and 1/3), which keep the matrix positive semi-definite:
   **S = Γ₀ + Σ_{l=1,2} (1 − l/3)(Γ_l + Γ_l′)**, Γ_l the covariance of the returns l sessions apart. S is then shrunk
   towards a multiple of the identity by the Ledoit-Wolf amount δ of the daily returns,
   **Σ = A × [(1 − δ) S + δ (tr S / N) I]**, A the number of sessions in a year over the span. A session without a
   trade counts as no change. Betas and expected returns (used only by maximum Sharpe) still come from the weekly
   returns. The two lagged days were fixed before any result was seen.
2. **Filling a K-name portfolio.** A better covariance estimate concentrates the full minimum-variance portfolio in
   fewer names, sometimes fewer than K. The remaining places then go to the shares minimum variance would take next:
   those with the smallest covariance with the portfolio, (Σw)_i (a minimum-variance portfolio leaves a share out
   exactly when that covariance is too high). Version 1.0.0 formed no K-name portfolio on such a date.
3. **A review trades the least that is nearly the best.** Near its minimum a portfolio's volatility changes very
   little with the weights. On a review date, with w* the minimum-variance weights on the K names and h the weights
   held, the model weights are those that **minimise Σ|w_i − h_i|** (what costs are paid on) subject to every cap,
   the floor, Σw = 1 and **√(w′Σw) ≤ 1.01 × √(w*′Σw*)**. At the start, with nothing held, they are w* itself. It
   applies to minimum variance only.

## The risk test (version 1.1.0)

Which covariance estimate to use is decided on the one thing it is for, risk, never on returns: over months a
difference in return between two methods is chance; a difference in risk can be measured.

- Every week from the start (the last session on or before each Wednesday), the minimum-variance portfolio is built
  with each of five estimates (the first rules' weekly identity target; OAS; a constant-correlation target; a
  single-index target; the daily estimate above), with the lab's caps, using only facts up to that date. It is then
  left alone for a week, without costs, and its daily total returns are recorded. Done for the full portfolio and
  for the 15-name version.
- Per estimate: the **realised volatility** (standard deviation of those daily returns × √sessions a year); the
  average **forecast volatility** √(w′Σw); the average weekly change in weights; and its realised variance divided by
  the first rules', with a **90 % interval** from a paired moving-block bootstrap (blocks of 5 sessions, 2,000 draws,
  a fixed seed so the rows are the same on every run).
- Two reference rows: an equal amount in every share of the universe, and the ASPI.
- The test is stored with every run (`models.cse_bt_risk_test`), so the choice is re-examined as history grows.

**What it does not show.** The estimate was chosen on the same weeks that test it, which flatters it somewhat. It
says nothing about returns.

## The start, and the walk forward

- **Start**: the first session on which the estimates can be made: at least 26 weekly returns (the lab's preview
  rule) and a published bill yield. Until a full year of weekly returns exists, each date uses all the weeks available
  (at least 26), and is marked as a preview.
- **Point in time**: each date's universe, estimates and portfolios read only facts up to that date
  (`cse_estimates.run_date`); prices and corporate actions on a session are those known by that session (the record's
  `Pricer`). Tested: the rows up to a date do not change when later data arrives.

## The rebalancing policies

1. **Half-yearly** (version 1.2.0, the example's; decision 0026): new model weights on the first session of January
   and July; the drift band in between. In the second review it cost 22 % less than quarterly reviews and was no more
   volatile (`docs/research/portfolio-lab-optimisation-2026-11.md` §7).
2. **Quarterly** (the lab's first rule; still run for comparison): the same on the first session of January, April,
   July and October.
3. **Dynamic**: a check on the first session of every month. The rules' portfolio is built afresh; the holdings are
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
- `models.cse_bt_risk_test` (version 1.1.0): per scope (the full portfolio, the 15-name version) and estimate: the
  weeks and days, realised and forecast volatility, weekly turnover, the effective number of names, and the realised
  variance against the first rules' with its 90 % interval; plus the two reference rows.

## Limits (they go with every use of these numbers)

- **Short.** The CSE's public price history reaches back one year, so the test starts in April 2026 with about six
  months of results. Over six months the market's direction dominates; differences of a few points between methods
  are within chance. The test lengthens by itself as the history grows; the CSE's historical data (part of the data
  permission request) would allow a multi-year test.
- **Previews.** Until October 2026 the estimates use 26 to 51 weekly returns, not a full year.
- **Survivorship.** The list of listed securities, sector labels and ownership groups are recorded only from October
  2026 and are used as first recorded for earlier dates: a company delisted before then is missing, and the group caps
  use October's groups.
- **Costs and prices.** Closing prices; no market impact beyond the stated cost. The cost per side, 1.12 %, was checked
  against the CSE's published schedule on 2026-11-20; dividends are credited after the final 15 % withholding tax
  (review F1).
- These are rules applied to public data, for research and education. They are not advice and say nothing about any
  share's future price.

## Versions

**1.0.0** (2026-11-01): first version. Kept as the reference.

**1.1.0** (2026-11-16, reference): the covariance from daily returns with two lagged days; the fill for K-name
portfolios; reviews that trade the least within 1 % of the minimum volatility; the stored risk test.

**1.2.0** (2026-11-20, current; decision 0026): 1.1.0's rules with a third policy, half-yearly reviews, now the
example's. Every version credits dividends net of the final 15 % withholding tax (review F1).
