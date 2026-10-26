# Model portfolios for research (cse_portfolio_lab)

**Internal research only.** Nothing here is shown on the site: every output is unpublished
(`config/entitlements.yaml`), the website's database role cannot read it (migration 0016), and the owner reads it
through `python -m data_platform.jobs.lab_report`. Publishing model portfolios in any form waits for a lawyer's view
(decision 0010 point 6, `docs/plan-retail-features.md` §5). These portfolios are rules applied to estimates; they say
nothing about what anyone should do.

## What it computes

For every estimate date of `cse_risk_estimates`: long-only, fully invested portfolios of the shares in its universe,
built by stated rules, with their estimated risk and the constraints that bind; the constrained efficient frontier;
and (version 1.1.0) versions with only 10 or 15 names. It is a port of the old CSE terminal (MinimumLizard/CSE@e05c6f3
`cse/optimize.py` and `cse/lab.py`; its `docs/METHODS.md` §8.5), solved with cvxpy 1.9.3 and Clarabel 0.11.1, the
old tool's versions.

## Constraints

For minimum variance, risk parity and maximum Sharpe, with weights w_i:

- **0 ≤ w_i ≤ cap_i**, **cap_i = min(10 %, 0.20 × median daily turnover_i × 10 / notional)**: a share may be at
  most 10 % of the portfolio, and at most 20 % of its median daily turnover over 10 days as a share of a
  portfolio of the notional size (the liquidity cap);
- the shares of one sector (the 20 S&P/CSE industry groups) sum to at most **30 %**;
- the shares of one ownership group (`cse_ownership`) sum to at most **20 %** (a one-share group adds a constraint only
  when 20 % is tighter than the per-share cap);
- **Σ w_i = 1**.

**Feasibility first.** Σ cap_i ≥ 1, and the sum over sectors of min(30 %, the sector's caps) ≥ 1, are necessary
(and, without groups, sufficient). With groups the same reach test runs per group, then an exact linear program
decides. If the constraints cannot all be met, nothing is solved and the date's status names what binds (too few
shares for the per-share cap, liquidity caps, sector caps, group caps, or sector and group caps together).

## The portfolios

Σ is the date's covariance and μ the CAPM expected returns (`cse_risk_estimates`), R_f its risk-free rate.

1. **Minimum variance**: minimise w′Σw.
2. **Risk parity**: the convex log-barrier form (Spinu 2013): minimise ½ y′Σy − (1/n) Σ log y_i with the caps written
   on y (y_i ≤ cap_i Σy, sector and group sums ≤ cap × Σy), then w = y / Σy. With no cap binding each share
   contributes the same share of the risk; where one binds the actual contributions are reported.
3. **Maximum Sharpe** on the CAPM expected returns: minimise y′Σy subject to (μ − R_f)′y = 1, y = κw, the constraints
   scaled by κ ≥ 0; w = y / κ.
4. **Equal weight**: 1/N across the universe, no caps (a comparison).
5. **Market** (version 1.1.0, a reference row): the ASPI, β = 1 by definition, so E[R] = R_f + ERP; its volatility is
   the sample standard deviation of its weekly returns over the same 52 weeks × √52.

After solving, weights under 0.0000001 are set to 0 and the rest rescaled to sum to 1.

Per portfolio: E[R] = μ′w, **σ = √(w′Σw)**, **Sharpe = (E[R] − R_f) / σ**; each holding's **risk contribution**
w_i (Σw)_i / w′Σw (they sum to 1); sector and group totals; the constraint report (sum, smallest weight, the largest
excess over a cap, a sector cap and a group cap, all within 0.000001) and, new here, **what binds**: the shares at
their cap (and how many at the liquidity cap), the sectors and groups at theirs, the names at a floor.

**Frontier**: minimum variance at 25 target returns, evenly spaced from the minimum-variance portfolio's E[R] up to
the highest E[R] the constraints allow.

## Versions with fewer names (version 1.1.0)

The full portfolios have up to about 140 names; many holdings are too small to be worth their costs in a small
portfolio. Following `docs/plan-retail-features.md` §6, for K = 10 and 15:

- **Which names.** The full portfolio of the same kind is ranked by weight (equal weight uses the names chosen for
  minimum variance). The first time, the K largest. On each later rebalance date, a name already in the portfolio
  stays while it ranks within the top ⌊1.5 K⌋ (the buffer: 15 for K = 10, 22 for K = 15); the remaining places go to
  the highest-ranked names not already in.
- **Weights.** Minimum variance or maximum Sharpe re-optimised on those K names only, with the same sector, group
  and liquidity caps, a per-share cap of **max(10 %, 1.5 / K)** (15 % for 10 names, 10 % for 15) and a floor of
  **0.5 / K** per name (5 % and 3.3 %), so every holding is worth having. Equal weight: 1/K, no caps.
- **When.** Set on the first estimate date with valid full portfolios, then only on the rebalance dates: the first
  session of January, April, July and October. Between them the weights stay as set (each date's row shows the
  weights in force, with the date they were set, and their risk on that date's estimates).
- **Tracking error** against the full portfolio of the same kind on the date: **√((w − w_full)′ Σ (w − w_full))**.
- If the caps and the floor cannot all be met on a rebalance date, the portfolio keeps the weights it had and the date
  says why.

## Notional

The liquidity caps depend on the portfolio's size. Version 1.0.0 used the old owner's own size (a personal setting,
from the private settings file); version 1.1.0 uses a stated neutral **Rs 1 mn** (decision 0023). With the universe's
Rs 1 mn median turnover floor the liquidity cap is then at least 0.2 × 1 mn × 10 / 1 mn = 200 %, so it never binds;
it starts to bind only for portfolios of several tens of millions.

## Outputs

- `models.cse_lab_summary`: per date: ok, waiting or infeasible (with the reason), preview, the notional, and the
  fingerprint of the date's inputs.
- `models.cse_lab_cap`: per date and share: the cap and the liquidity cap.
- `models.cse_lab_portfolio`: per date and portfolio: family (full, fewer names, market), K, status, the date the
  weights were set, number of names, E[R], σ, Sharpe, tracking error, the constraint report and what binds.
- `models.cse_lab_weight`: per date, portfolio and name: weight, risk contribution, cap, sector, group, E[R], at cap.
- `models.cse_lab_exposure`: per date and portfolio: the weight of each sector and ownership group, and whether at
  its cap.
- `models.cse_lab_frontier`: per date: the 25 frontier points.

**Reuse.** A date's result depends only on that date's estimates and weekly returns, the parameters, the names in the
fewer-name versions before it, and this code. Their SHA-256 is stored with the date; a later run keeps the stored rows
of a date whose fingerprint is unchanged and computes every other date afresh. This gives the same rows as computing
everything again (tested), in a fraction of the time.

## Caveats (they go with every use of these numbers)

- **In-sample estimates.** One year of weekly returns, CAPM expected returns with an assumed 6 % premium. With one
  year of data a Sharpe ratio's uncertainty is roughly ±1: differences of a few hundredths are noise. Nothing here
  promises a return.
- **Maximum Sharpe is unstable**: one new week of data can change several of its largest names. The fewer-name
  versions therefore change only on the quarterly calendar and with a buffer.
- These are model portfolios computed by rules, for research. They are not advice and not an offer, and they say
  nothing about any security's future price.

## Parity

Version 1.0.0 reproduces the old lab: at each of the old terminal's 9 sessions its own code run on its own files cut
at that session, and its stored `data/lab/*.json`. Two stored risk-parity solutions (2026-10-09 and 2026-10-12) differ
from the old code's own rerun by up to 0.0000033 in a weight: the old tool's own runs on identical inputs differ by
the same amount (the solver stops at its tolerance), so those two are compared within 0.00001. The plan §6 table is
reproduced from the 2026-10-15 inputs. Counts only: `docs/migration/parity-cse-portfolio-lab.json`.
