# Company figures: earnings, net assets and the ratios built on them (cse_fundamentals)

## What it shows

For every listed company with interim reports: its **earnings per share over the last twelve months** (TTM EPS),
its **net assets per share** (NAV per share), and at each session's price the **P/E**, **P/B**, **return on equity
(ROE)**, **trailing dividends per share** and **dividend yield**, with the report the figures came from.

The CSE does not publish earnings or book values per company, so they are read from the companies' own interim
reports. **A figure is used only if it reconciles inside its own report**; otherwise it is left blank, never
guessed.

## Inputs

- The interim reports' text (`cse.financial_reports`, `cse.report_texts`; see `cse_ownership`).
- Share counts: the company summaries and the trade summary (market capitalisation ÷ close = the CSE's count), and
  each report's own period-end count from its checked shareholder table (`cse_ownership` step 2).
- Each company's financial year end, from its CSE profile (`cse.company_fiscal_years`: `finYearEnd` 1 = 31 March,
  2 = 31 December).
- Closing prices (`cse.prices_daily_current`).
- The cash dividends in use, from `cse_corporate_actions` (`models.cse_corporate_action_used`).

## Method (version 1.0.0)

Version 1 reproduces the old terminal's `cse/fundamentals.py` exactly.

**1. Share counts tried.** First the report's own period-end count (from its verified shareholder table: shares ÷
fraction, voting plus non-voting), then every distinct count the CSE has reported for the company, newest first,
then today's. The first count under which the EPS reconciles is used; failing that, the first under which the NAV
per share does.

**2. EPS.** A line labelled earnings / profit / loss per share (or "Basic EPS"); its numbers may sit on the label
line or on a following "Basic" line. A lone whole number under 100 just after the label is a note reference; years
1990–2040 are dropped. Only the **first numeric column** is used. EPS × shares must equal a profit line in the 60
lines above, in the same first column: "profit attributable to equity holders / owners / shareholders of the
parent / company / bank" first, then "profit (loss) for the period / year / quarter", nearest first. Units tried:
rupees, Rs '000 and Rs mn; the unit that matches is the statement's unit. Tolerance:

|EPS × shares ÷ (profit × unit) − 1| ≤ min(15 %, 2 % + ½ × 10^−max(d, 2) ÷ |EPS|)

where *d* is the number of decimals the EPS is printed with. Signs must agree. Profit used afterwards = profit line ×
unit, in rupees.

**3. NAV per share.** A line labelled net asset (value) per share; group or consolidated lines first, then
company-only ones. NAV × shares must equal "equity attributable to owners …" or "total equity" under the same rule.
Equity used afterwards = that line × unit.

**4. What the first column covers.** The nearest line above the EPS (within 80 lines) naming a period length
decides: "quarter", "three months", "03 months" → the quarter; "six / nine / twelve months", "year ended", "half
year", "cumulative" → the year to date; both on one line → whichever comes first; none → unknown.

**5. Which quarter.** The CSE's period date when it is a quarter end; else the quarter-end date in the title; else
the last quarter end at least 15 days before the CSE's date.

**6. TTM profit.** Quarters are numbered within the financial year (for a March year end, the June quarter is Q1).
Quarterly profit = a quarter column; or a year-to-date column minus the previous quarter's year to date in the same
financial year; Q1 is both (an unknown column counts only for Q1). TTM profit = the sum of the last **four
consecutive** quarters, only when all four are known (otherwise the note names the missing quarter). Nothing is
annualised or estimated.

**7. Ratios**, at the session's last close P of the voting share, with S = today's shares issued (voting plus
non-voting; if the CSE gives none, the latest report's count):

- TTM EPS = TTM profit ÷ S;  NAV per share = latest reconciled equity ÷ S
  (so P/E = market cap ÷ TTM profit and P/B = market cap ÷ equity, as the CSE builds its market PER and PBV, and
  correct across splits and scrip issues; the report's printed EPS and NAV stay in `models.cse_report_figures`);
- earnings yield = TTM EPS ÷ P;  P/E = P ÷ TTM EPS, shown only when the earnings yield is above 0.2 % (a P/E above
  500 is noise; a loss shows no P/E);
- P/B = P ÷ NAV per share, when NAV > 0;  ROE = TTM EPS ÷ NAV per share, when NAV > 0;
- trailing dividends D = cash dividends per share with an ex-date in the 365 days to the session;
  dividend yield = D ÷ P.

**8. One row per session.** Computed as at every session with a trade summary, using only the prices, share counts,
reports (uploaded by then, period not after it), profiles and announced dividends known by then, so a session's row
never changes when later sessions arrive (unless a fact dated earlier arrives late; every change is kept in
`models.revisions`).

## Outputs

- `models.cse_fundamentals`: per company and session: price and its date, shares, financial year end, NAV per share
  and its period, P/B, TTM profit, TTM EPS, the quarter it ends and its note, earnings yield, P/E, ROE, trailing
  dividends, dividend yield, and the company's latest report (id, period, PDF).
- `models.cse_report_figures`: per report: the share count used, EPS, its column, profit and unit, NAV per share,
  equity, the matched lines, and whether each reconciled (`verified` / `not found`), as at the latest session.

## Limits

- Figures are as reported, mostly unaudited; exceptional items are not removed.
- Equity is the latest reported, so after a rights issue NAV per share is understated (and P/B overstated) until
  the next report.
- Many companies publish the fourth quarter only in their annual report, so they have P/B and dividend yield but no
  TTM P/E.
- Banks and finance companies are measured with the same ratios as everyone else.
- An amended dividend announced after a session can still change that session's trailing dividends (the dividends
  come from the corporate-action model's latest view).

## Parity

`docs/migration/parity-cse-ownership-fundamentals.json`: the old code, run on the old repo's files cut off at each of
its sessions, against this model's rows for the same session, and the CSVs the old repo stored on 2026-10-15.
