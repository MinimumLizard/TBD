# CSE share metrics (cse_security_metrics)

## What it shows

For every listed share, on every session: its close, change, turnover and market capitalisation; where the close
sits in the 52-week range the CSE publishes; its volume compared with its recent average; and its price return
compared with the ASPI over one week, one month and three months.

## Inputs

The CSE's trade summary and chart history (prices, `cse.prices_daily_current`), its company summaries (52-week
range, market capitalisation, beta) and the ASPI.

## Method (version 1.0.0)

- **Range position** = (close − 52-week low) / (52-week high − 52-week low), from the CSE's own, unadjusted high
  and low.
- **Volume against average** = the session's volume / the mean volume over the previous 20 sessions, counting a
  session without a trade as 0. Volume is the regular-market volume on days collected live, and the CSE chart's
  total (including negotiated crossings) on earlier days, as the old terminal stored it.
- **Return relative to the ASPI** over 5, 21 and 63 sessions = (P₁ / P₀ − 1) − (A₁ / A₀ − 1), where P is the last
  traded price on or before each end of the window and A is the ASPI. Price only: dividends are not included.
- **Flags.** A move of more than 40% between two consecutive traded closes is the usual sign of a split, bonus
  or rights issue that the CSE's prices do not adjust for. Such a move inside a return window is flagged on that
  window; inside the last 240 sessions it is flagged on the 52-week range.

## Limits

- Prices are not adjusted for corporate actions; the flags mark where that matters. Adjusted total returns are a
  separate, later model.
- A share with no trade in a session carries its last traded price from the CSE's company summary, where the
  summary was collected; otherwise it has no row for that session.

## Parity

Version 1 reproduces the old CSE terminal's Panel B for every share on its watchlist on every session it kept raw
files for (200 share-sessions), to 1e-14. Report: `docs/migration/parity-cse.json`.
