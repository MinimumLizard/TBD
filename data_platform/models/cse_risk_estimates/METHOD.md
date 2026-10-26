# Risk estimates for the portfolio lab (cse_risk_estimates)

**Internal research only.** Nothing here is shown on the site: every output is unpublished
(`config/entitlements.yaml`), the website's database role cannot read it (migration 0016), and the owner reads it
through `python -m data_platform.jobs.lab_report`. Model portfolios wait for a lawyer's view (decision 0010 point 6,
`docs/plan-retail-features.md` §5).

## What it computes

For every estimate date (a CSE session), from the facts known on that date:

1. **The universe**: which ordinary shares the lab may use, and for every security left out, why.
2. **Weekly total returns** of every share and of the ASPI.
3. **Risk and expected return** of every share in the universe: the Ledoit-Wolf covariance (and so each share's
   volatility), its Dimson beta, its CAPM expected return, and its Amihud illiquidity.

It is a port of the old CSE terminal (MinimumLizard/CSE@e05c6f3 `cse/estimates.py`, `cse/returns.py`,
`cse/sectors.py`; its `docs/METHODS.md` §6 and §8). Version 1.0.0 reproduces it exactly; version 1.1.0 (current)
changes three inputs, listed at the end.

## Inputs

- The ASPI (`cse.indices_daily_current`): the session calendar, and the market return.
- Prices (`cse.prices_daily_current`, one row per share and session, the daily row preferred): the days a share
  traded and its turnover.
- Each share's total-return index (`cse_total_returns`, which applies dividends, splits, scrip and rights issues).
- The CSE's security list on the date (`cse.security_list`).
- Each share's sector label from its CSE company profile (`cse.company_profiles`), mapped to one of the 20 S&P/CSE
  industry groups, with the owner's assignments in `config/sector_overrides.yaml` (stored as `cse.sector_overrides`).
- Ownership groups (`cse_ownership`): the companies whose largest voting blocks trace to the same holder.
- Version 1.0.0 only: the owner's conflict-of-interest list, from the private settings file (`LAB_PRIVATE_FILE`,
  stored as `cse.lab_private_settings`; it never enters this public repository). Without it, version 1.0.0 computes
  nothing.
- Version 1.1.0 only: the CBSL's 12-month treasury bill yield (table 4.04, `rates.cbsl_monthly_current`).

Every input is read as known on the estimate date: the prices, index values and total-return index up to it; the
security list of the latest session on or before it; the latest company profile fetched by then (before the first
one, the first); the ownership groups of cse_ownership's latest session on or before it (before the first, the
first). The owner's sector assignments and private settings are the latest stored version.

## Sector (audit C4)

In this order: the owner's assignment for the share; the profile label, if after removing case, punctuation, digits
and spacing it equals one of the 20 industry-group names (Energy, Materials, Capital Goods, Commercial & Professional
Services, Transportation, Automobiles & Components, Consumer Durables & Apparel, Consumer Services, Retailing, Food &
Staples Retailing, Food, Beverage & Tobacco, Household & Personal Products, Health Care Equipment & Services, Banks,
Diversified Financials, Insurance, Software & Services, Telecommunication Services, Utilities, Real Estate Management
& Development); a GICS sub-industry with one unambiguous industry group (for example "Investment Banking & Brokerage"
→ Diversified Financials). Anything else is unclassified.

## The universe (audit C8)

Each security on the date's list is tested in this order; the first test it fails is its reason:

1. Ordinary shares only: `.N0000` (voting) and `.X0000` (non-voting). Rights, warrants, preference shares, fund units
   and debt issuers are left out, named as such.
2. Version 1.0.0: not on the owner's conflict-of-interest list ("excluded (conflict of interest)").
3. History: at least 52 weekly total returns (below).
4. Traded on at least 80 % of the ASPI's sessions in the 52 weeks to the date: sessions in (date − 52 weeks, date].
5. Median daily turnover over those sessions of at least Rs 1 mn, counting a session without a trade as 0. Turnover
   is the CSE's own figure where the daily summary had one, otherwise close × volume (the source is reported per
   share: real, estimated or mixed).
6. Sector classified.

## Weekly returns

Wednesday to Wednesday. For a level series X (a share's total-return index, or the ASPI), X_w is its last value on or
before Wednesday w, and the weekly return is **r_w = X_w / X_{w−1} − 1**. The Wednesdays run from the first ASPI
session; a week before the first value has no return. The estimates use the last T = 52 returns, ending on the last
Wednesday on or before the date (so the window moves once a week).

## Estimates (audit C9)

With R the T × N matrix of weekly returns of the N shares in the universe:

- **Covariance**: Ledoit-Wolf shrinkage (scikit-learn 1.9.1 `LedoitWolf`, its default target: a multiple of the
  identity), annualised: **Σ = 52 × [(1 − δ) S + δ (tr S / N) I]**, where S = X′X / T is the sample covariance of the
  demeaned returns X and δ the shrinkage intensity the method estimates (stored per date).
- **Volatility**: σ_i = √Σ_ii.
- **Beta** (Dimson, one lag): ordinary least squares of r_i,t − r_f on (r_m,t − r_f) and (r_m,t−1 − r_f), with a
  constant; **β_i = β₀ + β₁**. The weekly risk-free rate is r_f = (1 + R_f)^(1/52) − 1; the market return r_m is the
  ASPI's (a price index: the old decision D4, kept).
- **Expected return** (CAPM): **E[R_i] = R_f + β_i × ERP**, with the equity risk premium ERP = 6 %, an assumption.
  Historical average returns are never used.
- **Amihud illiquidity**: the mean, over the weeks with turnover, of |r_w| ÷ (the week's turnover in Rs mn), the
  week's turnover being the sum of the daily turnover over (previous Wednesday, Wednesday].

**While the universe has fewer than two shares** the date is "waiting". Version 1.0.0 then, as the old lab did,
computes a *preview* on the longest history available when that is at least 26 weekly returns (the universe tests
with that history in place of 52). A preview is labelled as such and never used for the record.

## Outputs

- `models.cse_weekly_return`: per share (and the ASPI, `ASI`) and Wednesday: the level used, the session it is from,
  the weekly return.
- `models.cse_risk_summary`: per date: ok or waiting (and why), preview or not, the counts, the weeks used, the
  shrinkage δ, the risk-free rate and its source, the equity risk premium, the market proxy.
- `models.cse_risk_universe`: per date and security: in or out, the reason, weeks of history, share of sessions
  traded, median turnover, share of real turnover, sector.
- `models.cse_risk_estimate`: per date and share in the universe: sector, ownership group, β (and its two parts),
  E[R], σ, Amihud, median turnover and its source.

**The covariance is stored in factor form.** A covariance matrix per date would be about 10,000 numbers a day.
Instead, the weekly returns (stored once per share and week), the date's universe and its shrinkage δ determine it
exactly: `data_platform/models/_lib/cse_estimates.py ledoit_wolf()` rebuilds it from them (cse_portfolio_lab does, and
checks that the rebuilt δ equals the stored one to the last bit).

## Version 1.1.0 (current)

- **Risk-free rate**: the CBSL's 12-month treasury bill yield (end of month, table 4.04) instead of the old typed
  9.9 %. Point in time: the yield of the latest month whose figure had surely been published by the date, counting a
  month as published once one full month has passed after it (on 15 October, August's figure). This never uses a
  figure before it could have been public. A date with no figure yet is "waiting".
- **Equity risk premium**: 6 %, kept, and labelled an assumption wherever it is shown.
- **No personal exclusions**: the conflict-of-interest list is the old owner's personal setting.
- **No preview**, and estimate dates from the first session with a full year of weekly returns possible.

## Limits

- One year of weekly returns is a short sample: betas, and so CAPM expected returns, are noisy. These are in-sample
  estimates of risk; they do not predict returns.
- The ASPI is a price index (dividends are not in it), so the market return is understated by the dividend yield.
- A late fact (a corporate action confirmed later, a late price) changes the total-return index, and so the rows of
  dates after its ex-date, on the next run; every change is kept in `models.revisions` for version 1.1.0.
- Each run computes every date again, so the run time grows with the history; a later version can compute only new
  dates.

## Parity

Version 1.0.0 against the old terminal (counts only: `docs/migration/parity-cse-portfolio-lab.json`): at each of its
9 sessions, the old code run on its own files cut at that session, and the stored `data/lab/<session>.json` files:
the universe and every reason, every share's estimates, the weeks, shrinkage, risk-free rate and group names.
