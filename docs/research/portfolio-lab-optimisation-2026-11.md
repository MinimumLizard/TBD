# Optimising the portfolio lab (November 2026)

The owner asked for the portfolio lab to be optimised and finished. This note records what was tested, what changed
and what did not, with the numbers. The lab stays internal research: nothing here is published or shown on the site,
and nothing here is advice (decision 0010 point 6, `docs/plan-retail-features.md` §5).

**How the numbers were measured.** On the working database built from the old repositories' state of 12 to 13
November 2026 (every source to 12 November):

- `uv run python -m data_platform.jobs.models --model cse_lab_backtest` (the stored results, both versions);
- `uv run python scripts/research/lab_tournament.py <out.json>` (the wider comparison of rules).

## 1. The finding that mattered

The lab's first rules built a "minimum-variance" portfolio that was **no steadier than the market**.

| 8 April to 12 November 2026, Rs 1 mn, with costs | Return | Volatility | Largest fall | Costs |
|---|---|---|---|---|
| Example portfolio, first rules (1.0.0) | +1.9 % | 13.6 % | −15.7 % | Rs 24,066 |
| ASPI (prices only) | +1.1 % | 12.6 % | −14.9 % | – |
| Treasury bills | +5.5 % | 0.4 % | none | – |

The cause was the estimate of how shares move together. It used at most 52 weekly returns for about 140 shares, far
fewer observations than shares. It forecast a volatility of 11.4 % and delivered 13.0 %.

## 2. The risk test

Five ways of estimating the covariance were compared on risk only. Every week for 31 weeks (8 April to 11 November
2026), the minimum-variance portfolio was built with each, using only what was known that week, and its volatility
was measured over the week that followed, without costs.

| Covariance estimate | Forecast | Realised | Realised variance against the first rules (90 % interval) | Weights changed per week | Realised, 15 names |
|---|---|---|---|---|---|
| **Daily returns, two lagged days** | 10.9 % | **10.2 %** | 0.62 (0.52 to 0.72) | 5.3 % | 10.1 % |
| Weekly, constant-correlation target | 11.1 % | 10.9 % | 0.70 (0.59 to 0.81) | 5.5 % | 11.0 % |
| Weekly, single-index target | 10.4 % | 12.2 % | 0.88 (0.77 to 1.00) | 5.4 % | 13.8 % |
| Weekly, identity target, OAS amount | 11.4 % | 12.9 % | 0.98 (0.95 to 1.01) | 6.1 % | 12.9 % |
| Weekly, identity target (the first rules) | 11.4 % | 13.0 % | 1 | 5.7 % | 12.8 % |
| Reference: equal weight, every share | | 19.0 % | | | |
| Reference: the ASPI | | 12.6 % | | | |

- The daily estimate gave the lowest realised volatility, forecast it most closely, and changed its weights least.
- Its interval stays well below 1, so the difference from the first rules is not chance.
- The number of lagged days (two) was fixed before any result was seen. With none to four lagged days the realised
  volatility of the full portfolio was 10.0 %, 10.0 %, 10.2 %, 10.5 % and 10.9 %: the result does not depend on it.

## 3. What else was tested, and the outcome

With costs, through the same engine as the model.

| Question | Tested | Outcome |
|---|---|---|
| How many names? | 10, 15, 20, 25 with the daily estimate | Volatility 10.1 % to 10.5 % for 10 to 20 names, with similar costs; 12.2 % for 25. No reason to change from 15. |
| Rebalance more often? | The monthly check with thresholds of 2 %, 3 % and 5 % | No steadier (10.6 % to 10.7 %), and Rs 3,000 more in costs. Quarterly reviews stay. |
| Trade less at a review? | Allowing 1 %, 2 % and 5 % more estimated volatility than the minimum | Turnover fell from 86 % to 68 % of the average value and costs from Rs 20,635 to Rs 18,608 at 1 %. Wider tolerances saved nothing more. Adopted at 1 %. |
| A wider buffer for names already in? | 2 × K instead of 1.5 × K | No difference. Unchanged. |
| A K-name portfolio when the full one has fewer names | Filling with the shares minimum variance would take next | Needed: with a sharper estimate the full portfolio often has 14 to 20 names. Adopted. |

## 4. The result: version 1.1.0

| 8 April to 12 November 2026, Rs 1 mn, with costs | Return | Volatility | Largest fall | Costs | Traded |
|---|---|---|---|---|---|
| **Example portfolio, current rules (1.1.0)** | +3.8 % | **10.7 %** | **−10.0 %** | Rs 18,608 | 68 % |
| Example portfolio, first rules (1.0.0) | +1.9 % | 13.6 % | −15.7 % | Rs 24,066 | 118 % |
| ASPI (prices only) | +1.1 % | 12.6 % | −14.9 % | – | – |
| Treasury bills | +5.5 % | 0.4 % | none | – | – |

The example portfolio is still minimum variance, 15 names, quarterly reviews (decision 0024). What changed is how
its risk is estimated and how much it trades.

## 5. What this does not show

- **Seven months is short.** The return column says almost nothing about the method: bills beat every share
  portfolio over the period. Only the risk columns are evidence.
- **The estimate was chosen on the weeks that test it.** Picking the best of five flatters the winner. The interval
  (0.52 to 0.72) is far enough from 1 to survive that, but the real test is the record from here on. The risk test is
  stored with the model and repeats itself every day.
- **Costs are still high for Rs 1 mn**: 1.9 % over seven months, more than half of it the first purchases.
- The limits in `data_platform/models/cse_lab_backtest/METHOD.md` all still apply (survivorship, closing prices, no
  market impact).

## 6. Moved to the new estimate (2026-11-17)

The owner approved moving the lab's other three models to the daily estimate. `cse_risk_estimates`,
`cse_portfolio_lab` and `cse_lab_record` now have a version 1.2.0, with 1.1.0 kept as the reference:

- On 12 November the 26 shares in the backtest's portfolios have exactly the same volatility in both models.
  Command: a join of `models.cse_bt_target` (today) with `models.cse_risk_estimate` 1.2.0 on symbol and date.
- With the daily estimate, the full minimum-variance portfolio has 16 names, against 29 under the weekly estimate.

Still waiting:

- A multi-year test needs the CSE's historical data (part of the permission request, roadmap item 0).

## 7. Second review (2026-11-20): plan, written before any result was seen

The owner asked for a check of the lab for bugs, a review of every formula, and a test of better methods from the
academic literature. This section was committed before the tests were run, so the choice cannot be fitted to the
results.

### 7.1 What is tested

**Q1. The risk estimate.** Is the current one beaten? The candidates are:

- **Current:** daily returns with two lagged days, Ledoit-Wolf linear shrinkage towards the identity.
- **Nonlinear shrinkage** (Ledoit & Wolf 2020, *Annals of Statistics* 48(5), "Analytical nonlinear shrinkage of
  large-dimensional covariance matrices"). Each eigenvalue is shrunk by its own amount instead of one common amount,
  applied to the same lag-adjusted daily matrix.
- **Exponentially weighted** (RiskMetrics 1996; decay 0.97 a session, half-life about 23 sessions). It weights recent
  days more; then the current lags and shrinkage are applied.

**Q2. How the portfolio is built from the same names.** The 15 names the current rules choose are weighted six ways:

- **Minimum variance**, with the current caps and floor.
- **Hierarchical risk parity** (López de Prado 2016, *Journal of Portfolio Management* 42(4), "Building diversified
  portfolios that outperform out of sample").
- **Inverse volatility.**
- **Equal risk contribution** (Maillard, Roncalli & Teïletche 2010, *Journal of Portfolio Management* 36(4)).
- **Maximum diversification** (Choueifaty & Coignard 2008, *Journal of Portfolio Management* 35(1)).
- **Equal weight**: the naive benchmark of DeMiguel, Garlappi & Uppal (2009, *Review of Financial Studies* 22(5)),
  which most optimised portfolios fail to beat out of sample.

The same six are also run on the whole universe, without choosing 15 names.

**Q3. How often, and how far, it rebalances, with costs.** The candidates are:

- **Current:** quarterly, trading the least within 1 % of the minimum, the drift band in between.
- **Partial adjustment** (after Gârleanu & Pedersen 2013, *Journal of Finance* 68(6)): at each review, move half of
  the way from the weights held towards the new target.
- **Monthly reviews**, same rules.
- **Half-yearly reviews**, same rules.
- **A wider drift band** (50 % of a target, not 25 %), in the spirit of the no-trade region of Leland (1999) and
  Donohue & Yip (2003).

### 7.2 How each is judged

- **Q1 and Q2: realised risk only**, as in §2. Each week the portfolio is formed with what was known that week and
  held for the next week without costs. Each candidate's realised variance is compared with the current method's by
  the test of Ledoit & Wolf (2011, *Wilmott*, "Robust performance hypothesis testing with the variance"). That test is
  a studentized circular block bootstrap of the difference in log variances, with 4,999 draws and blocks of 10
  sessions. Holm's correction is applied across each family of comparisons.
- **Q3:** costs, realised volatility and the largest fall over the walk-forward test, with costs.

### 7.3 When something is adopted

- **Q1 and Q2:** only if a candidate's realised variance is lower than the current method's with a Holm-adjusted
  p-value below 0.05, and by at least 5 %. Anything weaker is reported and not adopted. A worse result never removes
  the current method on this evidence alone either.
- **Q3:** with only two or three reviews in seven months, no test has the power to decide. A rule is adopted only
  if it costs less and is no more volatile (within 0.2 percentage points); otherwise it is reported for the
  twelve-month review.

### 7.4 Formula and input review (before the tests)

- **Cost per side 1.12 %:** confirmed. Brokerage 0.64 %, CSE 0.084 %, CDS 0.024 %, SEC cess 0.072 % and share
  transaction levy 0.30 %, for trades up to Rs 100 mn (CAL, CT CLSA and Invest Sri Lanka schedules).
- **F1. Dividend withholding: wrong.** The lab credits dividends in full (`dividend_withholding: 0.0`, the old
  tool's setting). Since 1 January 2023 dividends from resident companies bear a final 15 % withholding tax
  (Inland Revenue (Amendment) Act No. 45 of 2022). The next version uses 0.15.
- **F2. Weights that do not quite sum to 1:** `cse_portfolio_lab` 1.2.0 stored one set of weights summing to
  0.9999975, on 28 October. The solver keeps weights above 1e-7, but only weights above 1e-6 are stored. Found by
  the new audit (`python -m data_platform.jobs.lab_audit`). Fixed in 1.2.0, which has not had a production run.
- **Everything else the audit checks passes on every stored row:** the cash and value of every walk-forward book,
  rebuilt from its trades and prices; caps, floors, sector and group limits; costs; whole shares; review dates; the
  summaries.
