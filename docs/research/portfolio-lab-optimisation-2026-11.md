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

## 6. Not done, and why

- `cse_risk_estimates`, `cse_portfolio_lab` and `cse_lab_record` still use the weekly estimate (their version 1.1.0).
  They are the lab's workings (the universe, the frontier, the forward record). Moving them to the daily estimate is
  a new version of each, and the forward record should start from the estimate the owner settles on. Proposed as the
  next step once the owner has seen this note.
- A multi-year test needs the CSE's historical data (part of the permission request, roadmap item 0).
