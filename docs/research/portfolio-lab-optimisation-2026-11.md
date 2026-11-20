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
  (Inland Revenue (Amendment) Act No. 45 of 2022). Fixed in every walk-forward version and in the record's 1.2.0
  (`dividend_withholding: 0.15`); none has had a production run. The record's 1.0.0 and 1.1.0 keep the old tool's
  setting, because 1.0.0 must reproduce the old tool (parity).
- **F2. Weights that do not quite sum to 1:** `cse_portfolio_lab` 1.2.0 stored one set of weights summing to
  0.9999975, on 28 October. The solver keeps weights above 1e-7, but only weights above 1e-6 are stored. Found by
  the new audit (`python -m data_platform.jobs.lab_audit`). Fixed in 1.2.0, which has not had a production run.
- **Everything else the audit checks passes on every stored row:** the cash and value of every walk-forward book,
  rebuilt from its trades and prices; caps, floors, sector and group limits; costs; whole shares; review dates; the
  summaries.

### 7.5 Results (scripts/research/lab_methods.py; 31 weeks from 8 April 2026, data to 12 November)

Realised volatility of each candidate, held a week at a time without costs (Q1, Q2) or walked forward with costs
(Q3). "Ratio" is realised variance against the current method's; p is the Ledoit-Wolf (2011) studentised block
bootstrap test, 4,999 draws, blocks of 10 sessions; Holm adjusts for the several candidates in each question.

| Question | Candidate | Volatility | Ratio | p (Holm) | Adopted under §7.3 |
|---|---|---|---|---|---|
| Q1, whole portfolio | current (daily, two lags) | 10.24 % | 1 | | kept |
| | nonlinear shrinkage | 15.23 % | 2.21 | 0.135 | no |
| | exponentially weighted | 10.45 % | 1.04 | 0.577 | no |
| Q1, 15 names | current | 10.08 % | 1 | | kept |
| | nonlinear shrinkage | 19.90 % | 3.90 | 0.056 | no |
| | exponentially weighted | 10.14 % | 1.01 | 0.889 | no |
| Q2, 15 names | minimum variance (current) | 10.08 % | 1 | | kept |
| | hierarchical risk parity | 9.41 % | 0.87 | 0.018 | passed the rule; see §7.6 |
| | maximum diversification | 9.94 % | 0.97 | 1.000 | no |
| | equal risk contribution | 10.10 % | 1.00 | 1.000 | no |
| | inverse volatility | 10.28 % | 1.04 | 0.298 | no |
| | equal weight | 10.90 % | 1.17 | 0.002 (worse) | no |
| Q2, whole universe | minimum variance (current) | 10.24 % | 1 | | kept |
| | the five others | 14.2 % to 19.0 % | 1.9 to 3.4 | ≤ 0.001 (worse) | no |

Q3, minimum variance with 15 names, Rs 1 mn, with costs:

| Rule | Return | Volatility | Largest fall | Costs | Traded | Reviews |
|---|---|---|---|---|---|---|
| current (quarterly) | +3.49 % | 10.66 % | −10.27 % | Rs 18,586 | 68 % | 3 |
| half-yearly | +4.09 % | 10.64 % | −9.44 % | Rs 14,543 | 31 % | 2 |
| partial adjustment (half way) | +4.53 % | 10.74 % | −9.68 % | Rs 18,163 | 64 % | 3 |
| monthly | +2.72 % | 10.35 % | −10.28 % | Rs 22,151 | 100 % | 8 |
| wider drift band | identical to current: the band never triggered in this period | | | | | |

What this says:

- **The risk estimate stays.** Neither alternative beat the current estimate. Nonlinear shrinkage did much worse,
  which is the opposite of its record in large, liquid markets. The likely reason: it was applied, as
  pre-registered, to the lag-augmented matrix. The lagged terms make that matrix only approximately a sample
  covariance, and nonlinear shrinkage relies on that structure more than linear shrinkage does. A diagnostic on
  plain daily returns (§7.6, D1) is also worse (14.94 %), so the lags are not the whole story; with about 130
  sessions for about 100 shares, the high-dimensional regime the method was built for is at its edge. The
  implementation reproduces the method on simulated data (tests/test_cse_research_methods.py).
- **Minimum variance beats every alternative on the whole universe by a wide margin.** It is the only method that
  uses the covariances fully; the others ignore most of them or spread weight onto volatile shares.
- **Half-yearly reviews qualify:** 22 % less cost, no more volatile. Partial adjustment also qualifies, narrowly
  (2 % less cost). Monthly reviews were steadier but cost 19 % more. Returns are reported but were never a
  criterion.

### 7.6 Follow-ups (post hoc: run after §7.5 was seen, so they confirm or qualify, never select)

`scripts/research/lab_methods_followup.py`:

| Check | Result |
|---|---|
| D1. Nonlinear shrinkage on plain daily returns (no lags) | 14.94 %, ratio 2.13, p 0.079: still worse than current |
| C1. HRP **within the lab's limits** (10 % a share, 30 % a sector, floor 0.5/K) against minimum variance | 10.25 % against 10.08 %, ratio 1.03, p 0.161: no better |
| C1. HRP without limits (as in Q2) | 9.41 %, ratio 0.87, p 0.009: confirms Q2 |
| C2. With costs: current / HRP within limits / half-yearly / HRP half-yearly | vol 10.66 / 10.72 / 10.64 / 10.89 %; costs Rs 18,586 / 19,754 / 14,543 / 14,922 |

HRP's advantage in Q2 came from the comparison, not from the method: Q2 weighted the 15 names by HRP **without**
the lab's caps, against minimum variance **with** them. Inside the same limits HRP is no steadier, and with costs
it is slightly more volatile and costs more. Adopting it would mean dropping the per-share and per-sector caps, a
design choice (decision 0023), not a statistical one. So it is not adopted; the owner can decide whether the caps
should stay (they guard against concentration that a year of data cannot justify).

### 7.7 What changed (decision 0026)

- `cse_lab_backtest` 1.2.0 (current): a third policy, half-yearly reviews (January and July), now the example's;
  quarterly and the monthly check run beside it. 1.1.0 is kept as a reference.
- `cse_portfolio_lab` 1.2.0 and `cse_lab_record` 1.2.0: versions with K names reviewed half-yearly, January and July
  (both had no production run, decision 0015 rule 11).
- F1 and F2 (§7.4) fixed. The audit (`python -m data_platform.jobs.lab_audit`) passes on every stored row after the
  rerun.
- Not adopted: nonlinear shrinkage, exponential weighting, HRP, inverse volatility, equal risk contribution,
  maximum diversification, partial adjustment (it qualified but saved only 2 %; combining it with half-yearly
  reviews was not tested, so it is not stacked on top), the wider drift band (no evidence either way).
- Thirty-one weeks and two or three reviews are very little. These rules are to be re-run at the twelve-month review
  (April 2027) with the same scripts and the same adoption rules.
