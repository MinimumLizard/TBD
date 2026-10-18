# CSE total returns (cse_total_returns)

## What it shows

For every listed share and every session it traded in: the **total return** since the previous traded close, which
counts the share's confirmed cash dividends and corrects for sub-divisions, scrip dividends and rights issues; the
**total-return index** (TRI) built from it; and, beside them, the **price-only return**. Also the total return over
1 week, 1 month and 3 months.

## Inputs

- The CSE's closing prices (`cse.prices_daily_current`: the daily trade summary where it was collected, otherwise
  the CSE's one-year chart). They are **unadjusted**: after a 1-for-5 split the price simply drops to a fifth.
- The corporate actions in use from `cse_corporate_actions` (version 1.0.0): confirmed, or confirmed by the owner.
  Actions awaiting confirmation are never used.
- The ASPI's sessions, for the 1-week, 1-month and 3-month windows.

## Method (version 1.0.0)

For two consecutive traded closes P₀ (the earlier) and P₁, take every action in use whose ex-date falls **after
P₀'s session and on or before P₁'s**:

- **F** = the product of the share-count factors that went ex (sub-division or scrip of b new shares per a held:
  F = (a + b) / a). F = 1 when there are none.
- **D** = the sum of the cash dividends per share that went ex. D = 0 when there are none.
- **base** = the theoretical ex-rights price if a rights issue of m new shares for every n held, at price S, went
  ex: (n × P₀ + m × S) / (n + m). Otherwise base = P₀.
- **Total return** R = (P₁ × F + D × (1 − w)) / base − 1, where w is the dividend withholding rate (0 in version
  1, as in the old terminal: dividends counted in full).
- **TRI** = the product of (1 + R) over every step, starting at 1 on the share's first close.
- **Price-only return** = P₁ / P₀ − 1.
- **Total return over 5, 21 and 63 sessions** = TRI₁ / TRI₀ − 1, where TRI₁ is the TRI on the session and TRI₀ the
  TRI at the last trade on or before the ASPI session 5, 21 or 63 sessions earlier (the same windows as the share
  metrics' price returns).

An action therefore applies to the **first traded close on or after its ex-date**, which matters for shares that
do not trade on the ex-date. With no actions, the total return equals the price-only return.

**No double adjustment.** Because the prices are unadjusted, F and the theoretical ex-rights price are applied. At
every confirmed split or scrip with F ≥ 1.5 the run checks that the close actually fell by about F (whichever of
"fell by F" and "did not fall" is nearer, on a log scale). If it did not, the prices already look adjusted and the
run stops rather than adjust them twice.

Worked example (CIC, 2026): a final dividend of Rs 0.50 went ex on 1 July. The close was Rs 31.00 on 30 June and
Rs 31.80 on 1 July, so R = (31.80 + 0.50) / 31.00 − 1 = 4.19%, while the price-only return is 2.58%.

## Limits

- Only actions in use count: a dividend still awaiting confirmation is left out until it is confirmed, and the
  total return is understated meanwhile.
- Withholding tax on dividends is not deducted (w = 0).
- A share that did not trade has no row for that session; its TRI moves on its next trade.
- A row for a session never changes when later sessions arrive. It changes only when a fact about an earlier date
  arrives: a late-confirmed action, a restored price, or (through the corporate-action model) a scrip whose
  share-count check changes.

## Parity

Version 1 reproduces the old CSE terminal's `build_tris` (cse/estimates.py, with cse/returns.py) run on its own
prices and corporate actions, for every ordinary share it listed and every traded close: at the audited commit
f263830, 294 shares and 69,300 closes; at e05c6f3, 294 shares and 70,416 closes; every value equal (largest
difference 0). It also matches under an illustrative set of confirmations that puts every complete rights issue in
use (21 at f263830, 22 at e05c6f3), so the rights formula is compared too. 2026-10-05 is left out for the
comparison, because the old terminal never had that session. Reports: `docs/migration/parity-cse-corporate-actions.json`
(f263830) and `docs/migration/parity-cse-corporate-actions-e05c6f3.json`.
