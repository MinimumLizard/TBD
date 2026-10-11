# Phase 0 audit: the three existing market tools

**Status:** Phase 0 deliverable, read-only. Nothing in the three source repositories was changed.
**Audit date:** 2026-10-11.
**Audited commits:**

| Tool | Repository | Branch audited | Commit |
|---|---|---|---|
| CSE terminal | `MinimumLizard/CSE` | `main` | `f263830` (2026-10-11) |
| Bonds (Nelson-Siegel) | `MinimumLizard/Nelson-Siegel` | `main` | `1c33084` (2026-10-10) |
| Crypto terminal | `MinimumLizard/Crypto` | `claude/minilizard-crypto-terminal-e6g100` (default) and `data` | `4dc446a` (code), `fce882b` (data) |

**How this was done.** Each repository was cloned read-only into a scratch folder. I read the docs, workflows, collectors and
model code; profiled every history file (row counts, date ranges, duplicates, calendar gaps); compared older
versions of the data in git history with today's, to see whether history has ever been rewritten; and ran each test
suite offline. Data-source terms were checked against each provider's published terms on 2026-10-11. Where I could not
find terms, the table says "unknown, needs enquiry". None of this is legal advice: section 7 lists what a lawyer
should confirm.

---

## 1. Summary

You have three working, well-documented, carefully tested tools. Their docs are unusually honest about their limits,
which will make the rebuild much easier. All three test suites pass: CSE 240 tests, bonds 132, crypto 290 (plus one
deliberately skipped parity test).

The things that matter most for the business, most urgent first:

1. **The bond collector stops collecting on 1 January 2027, and nothing will fail.** The PDMO index URLs are
   hard-coded for 2025 and 2026 only (`pipeline/config.py`). In 2027 the 2026 pages will still load, so every run will
   report success while ingesting nothing new. That is 82 days from today. *(Fragility F1.)*
2. **Raw source files are not being kept for bonds or crypto.** The bond pipeline downloads each PDMO Excel/PDF,
   parses it and throws the file away (`data/raw/` is gitignored and the GitHub runner is wiped after each run). The
   PDMO website only goes back to 28 Nov 2025, so if it removes files, the parsed database is the only copy. The parsed
   rows have already been rewritten in place: 724 of the quote rows that existed on 1 Sep 2026 now carry different
   yields, after an ISIN-matching fix. That fix was correct, but the original inputs can only be re-checked while the
   website still serves them. The crypto pipeline has the same gap: `rsync --exclude='raw'` drops its raw response
   cache. *(F2, F3.)*
3. **Some crypto history cannot be re-fetched.** About 16 days of daily snapshots exist: supply, top-100, open
   interest, order-book depth, event odds, news. No free API serves these as history, and the crypto plan proposes
   "squashing" the data branch. *(F3.)*
4. **The CSE terminal has already lost one trading session.** Monday 2026-10-05 has no price rows: the scheduled run
   never started (no run log, no commit). Closes, highs, lows and volumes for that day can still be recovered from the
   CSE's one-year chart endpoint, but that day's turnover is gone for good. The daily job only ever collects "today",
   so every missed run is a permanent loss of turnover. *(F4.)*
5. **The only copy of everything is on GitHub, and all three repositories are public.** No backups exist anywhere
   else. Anyone can clone the full history today, which matters once that history is what you sell. *(F5.)*
6. **The live public pages already use language your hard rules ban.** The bond page prints "Switch candidates …
   buy / sell" and its text readout says "buy the cheap, sell the rich". The CSE page shows a "trade list" with
   "+ add / − trim" sized to a personal portfolio. The crypto engine emits "GET IN / GET OUT" and has a "buy order".
   These are personal tools, so that was reasonable. None of it can carry over into the product as it stands. *(Section 8.)*
7. **Several data sources do not allow commercial redistribution on their free terms.** CoinMetrics community is
   CC BY-NC (non-commercial). Coinbase market data is for personal or research use only. DefiLlama's site terms forbid
   republishing without permission. CoinGecko's free plan does not cover storing history. The two Sri Lankan sources
   that hold most of the value, the CSE and the PDMO, publish no terms at all, so both need an enquiry before launch.
   *(Section 7.)*

The good news: each project already separates fetching, storing and computing; keeps an append-only or versioned
record; and documents every formula. The CSE's `series` label on its model record is exactly the "method version"
idea in the brief. The data is small: under 100k CSE price rows, about 125k bond rows and under 1M crypto rows.
Migrating it is a verification problem, not a scale problem.

---

## 2. CSE terminal (Colombo Stock Exchange)

A Python job fetches the CSE website's own JSON API once per trading day. It validates every response with pydantic,
writes the untouched responses plus append-only CSVs to the repo, and renders four static pages: terminal, ownership,
money flows and fundamentals. A second, weekly job downloads company interim and annual-report PDFs and keeps their
text.

### 2.1 How data is collected

| Item | Detail |
|---|---|
| Source | `https://www.cse.lk/api/`: the **undocumented** JSON API behind cse.lk. No login, no key. Mostly `POST` with form fields; six endpoints are `GET` only. PDFs come from `https://cdn.cse.lk/`. |
| Daily endpoints | `marketStatus`, `allSecurityCode`, `dailyMarketSummery`, `tradeSummary`, `allSectors`, `aspiData`, `snpData`, `marketSummery`, `companyInfoSummery` (watchlist only), `companyProfile` (new listings only), `approvedAnnouncement`, then `getAnnouncementById` / `getGeneralAnnouncementById` per new announcement, and `getFinancialAnnouncement`. About 67–83 calls a day. |
| One-off backfills | `companyChartDataByStock` (period 5 = 240 sessions, the API's maximum) for all 302 ordinary shares; `chartData` (period 5) for 22 indices; `getAnnouncementByCompany` (back to 2012) for corporate actions and directors' dealings. |
| Weekly endpoints | `financials` per company (281), then the latest interim and annual report PDFs from cdn.cse.lk, converted with `pdftotext -layout`. |
| Schedule | `daily.yml`: weekdays at 11:23 UTC (16:53 Sri Lanka). Actual starts have been 16:39–17:50 UTC, about 5–6 hours late. `ownership.yml`: Saturdays at 02:00 UTC. Both share one concurrency queue. |
| Politeness | Sequential calls, a 1-second pause, 3 retries (2/4/8 s) on 429/5xx, 30 s timeout, an honest User-Agent naming the GitHub repo (`cse/http.py`). |
| Validation | Every response goes through a pydantic model (`cse/models.py`). The session date comes from the API (`dailyMarketSummery[0][0].tradeDate`), never the clock. The run refuses an open market, refuses an older session, and checks that `tradeSummary`'s latest trade falls on the session date. |
| Failure handling | Any fetch or validation error aborts before anything is written. The failure is logged to `data/runs.csv` and the previous site stays up. The lab, ownership, flows and fundamentals steps may fail without blocking the deploy; the job is marked failed at the end. A page banner warns when data is a session behind (computed in the browser, and unaware of holidays). |
| Idempotency | Re-running is safe: appends are keyed on (date, symbol, source) etc., and "no new session" writes nothing. |

### 2.2 Where history is stored

All data lives in the repository's `main` branch: CSV files plus raw JSON/text. The working tree is 121 MB; the git
pack is 25 MB.

| File | Rows | Range | Notes |
|---|---|---|---|
| `data/history/prices.csv` | 69,312 | 2025-10-07 → 2026-10-09 | 67,900 `backfill` rows (294 symbols, to 2026-10-01) + 1,412 `daily` rows (5 sessions). Unadjusted prices. Backfill rows have `turnover` empty and `turnover_est = close × volume`. |
| `data/history/indices.csv` | 5,382 | 2025-10-07 → 2026-10-09 | ASPI, S&P SL20, 20 sector indices, ASTRI and S&P SL20 TRI (TRI daily only, from 2026-10-01). |
| `data/history/market.csv` | 7 | 2026-10-01 → 2026-10-09 | Market turnover, trades, foreign buy/sell, P/E, P/BV, DY. Only exists from the daily job. |
| `data/history/announcements.csv` | 206 | 2026-09-27 → | Rolling feed since the first run. |
| `data/history/corporate_actions.csv` | 392 | 2025-06 → | 316 cash dividends, 26 sub-divisions, 25 scrip and 23 rights issues; 28 rows `needs_review`. |
| `data/dealings/dealings.csv` | 2,243 | trades 2025-05-27 → 2026-10-08 | Rebuilt every run from 830 raw notices. |
| `data/raw/<session>/` | 6 session folders | 2026-10-02 → 2026-10-09 | Untouched API responses. 2026-10-02 holds the backfill (13 MB). |
| `data/raw/ownership/` | 1,387 report texts + 281 annual-report extracts | report periods 2019 → 2026 | 82 MB. **Only the extracted text is kept; the PDFs are not.** |
| `data/ownership/*.csv` | holdings 27,779; owners 2,929; companies 281 | latest quarter | Rebuilt weekly from the report text. |
| `data/fundamentals/*.csv` | reports 1,328; latest 277 | — | Rebuilt daily, offline. |
| `data/lab/<session>.json`, `record/*.csv` | nav 20, holdings 1,444, trades 732 | since inception 2026-10-07 | The forward-only model-portfolio record. Series `v0-52w`, then `v1-52w-grp20`. |
| `data/runs.csv` | 51 | 2026-10-04 → | One row per job run. |

**Gaps and duplicates found:**

- **Missing session 2026-10-05 (Monday).** The market traded that day (`market.csv` has turnover of Rs 3.16 bn, taken
  from the next day's "previous session" row). But `prices.csv` and the sector indices have nothing for that date, and
  `runs.csv` has no run. The git log shows no bot commit between 2026-10-04 and 2026-10-06 17:09 UTC. Price, high, low
  and volume are recoverable from `companyChartDataByStock` until about October 2027; turnover is not.
- The other 19 weekdays missing from the ASPI calendar since Oct 2025 match Sri Lankan market holidays (Poya days,
  Christmas, New Year and so on). That conclusion comes from cross-checking against the bond data, not from an
  official calendar.
- No duplicate (date, symbol) or (date, symbol, source) rows. No null or non-positive closes.
- **Has history been rewritten?** I compared every committed version of each history file with the one before it. `prices.csv`,
  `indices.csv`, `market.csv`, `announcements.csv` and the record files are strictly append-only. `corporate_actions.csv`
  was regenerated once, during development on 2026-10-04, before the daily job used it; 40 rows were replaced by
  corrected ones. `dealings.csv` is rebuilt by design. `runs.csv` shows reorderings caused by rebases.
- Source data errors are visible in the CSE's own records. For example, report 35920 (SLTL) and 36898 (TESS) carry a
  period date of 2030 for 2020 reports. The fundamentals code skips them correctly.

### 2.3 Every model and calculation

`docs/METHODS.md` in the CSE repo states every formula exactly as implemented. This table is the inventory, so Phase 3
can plan a parity test for each line. "Inputs" are datasets; "assumptions" are the choices that would change the
answer.

| # | Model / calculation | Code | Inputs | Outputs | Key assumptions |
|---|---|---|---|---|---|
| C1 | Market tape (Panel A): index levels and changes, TRI % change, activity vs 20-session average, breadth, foreign net flow, valuation, top turnover, gainers/losers, sectors | `metrics.py`, `build.py` | tradeSummary, dailyMarketSummery, allSectors, market.csv | Panel A | 20-session averages need 21 real sessions (decision D5). Gainers/losers need turnover ≥ Rs 1 mn. |
| C2 | Watchlist metrics (Panel B): price, day change, 52-week position, volume vs average, return vs ASPI over 5/21/63 sessions, market cap, CSE beta | `metrics.py` | prices, indices, companyInfoSummery | Panel B | Price-only returns. A one-bar move > 40% is flagged as a likely unadjusted corporate action. The 52-week high/low come from the CSE and are unadjusted. |
| C3 | Disclosure tagging | `tags.py` | announcements | tag per item | Keyword rules, first match wins. |
| C4 | Sector normalisation | `sectors.py`, `config/sector_overrides.yaml` | companyProfile.sector | 20 S&P/CSE industry groups | Hand overrides, then label normalisation, then a sub-industry map; otherwise "Unclassified". |
| C5 | Whole-market liquidity screen | `scripts/screen_watchlist.py` | 1-year backfill | Tier A/B/C | Thresholds 95%/Rs 10 mn and 80%/Rs 1 mn. |
| C6 | Corporate-action extraction | `corpactions.py` | getAnnouncementById / General | `corporate_actions.csv` | Amounts are never inferred. Rights ratios are parsed from text and always `needs_review` until confirmed in `config/corporate_actions_review.yaml`. |
| C7 | Total return | `returns.py` | prices, confirmed corporate actions | daily TR, TRI | R = (P₁·F + D·(1−withholding)) / base − 1. Rights use TERP. Applied on the first traded close on or after the ex-date. `check_adjustment` stops the run if a split doesn't show up in the price. |
| C8 | Universe filter | `estimates.py` | prices, CA, sectors | universe + reasons | `.N0000`/`.X0000` only; ≥ 52 weekly returns; traded on ≥ 80% of sessions; median turnover ≥ Rs 1 mn (estimated where needed). |
| C9 | Weekly returns, Ledoit-Wolf covariance, Dimson beta, CAPM expected return, volatility, Amihud illiquidity | `estimates.py` | TRI, ASPI | estimates | Wednesday sampling. ASPI price index as market proxy (D4). `risk_free_annual` = **9.9%, typed in by hand**. ERP = **6% (assumption)**. |
| C10 | Model portfolios: minimum variance, risk parity (Spinu log-barrier), maximum Sharpe, equal weight, market, "my book"; efficient frontier | `optimize.py` (cvxpy + Clarabel) | estimates, caps | weights, risk contributions, Sharpe | Caps of 10% per stock, 30% per sector, 20% per ownership group, plus a liquidity cap from `portfolio_size_lkr` (Rs 5 mn, personal). |
| C11 | Live record and rebalancing | `record.py`, `lab.py` | weights, prices, CA | `record/*.csv` | Whole shares, cost per side **1.12%** (marked "VERIFY"), quarterly rebalance, drift bands, rights always taken up. Append-only, versioned by `series`. |
| C12 | Trade list | `lab.py`, template | record, `portfolio_size_lkr` | "+ add / − trim" rows | Scaled to a personal portfolio size. **Personalised trade instruction; see section 8.** |
| C13 | Ownership table parsing | `ownership/parse.py` | report text | parsed top-20 tables | Consistency checks against the CSE share count and the report's printed totals; one typo row tolerated. |
| C14 | Beneficial owner resolution | `ownership/names.py`, `config/ownership_aliases.yaml` | parsed rows | owner, type, via | Custodian and margin stripping. Individuals never merged automatically. |
| C15 | Look-through ownership and control | `ownership/analyse.py` | holdings, market caps | `owners.csv`, `companies.csv` | F = D(I−W)⁻¹. Control at > 50%, influence at 20–50%. Statutory vote caps not applied. |
| C16 | Ownership groups (for C10's group cap) | `ownership/groups.py` | companies.csv, `ownership_parents.yaml` | group per stock | ≥ 20% block, not a fund or nominee. Deliberately wider than "control". |
| C17 | Parent-company evidence | `ownership/annual.py`, `parents.py` | annual reports | evidence sheet | Suggestions only; a link is used only when you confirm it in YAML. |
| C18 | Directors' dealings | `dealings.py` | DealingsByDirectors records | `dealings.csv` | Side from free-text regex. Re-filed notices de-duplicated. Lag counted in weekdays, holidays not removed. |
| C19 | Money flows: per actor, per company, clusters, flags | `flows.py` | dealings, ownership | `flows.html` | Windows 30/90/365 days; "large" ≥ Rs 10 mn. |
| C20 | Quarter-to-quarter list changes | `flows.py` | consecutive top-20 lists | entered/left/bought/sold | Four-step name pairing. Values use today's market cap. |
| C21 | Fundamentals: EPS and NAV extraction with reconciliation | `fundamentals.py` | report text, share counts | `reports.csv` | A figure counts only if EPS × shares reconciles to a profit line (2% + rounding tolerance, max 15%). |
| C22 | TTM profit, P/E, earnings yield, P/B, ROE, dividend yield; market-level cross-check | `fundamentals.py` | reports, prices, CA | `latest.csv` | Four consecutive quarters or nothing. Today's share count. P/E is shown only when earnings yield > 0.2%. |
| C23 | Stale-data banner | template JS | build date | banner | **Computed in the browser.** Knows weekends, not holidays. |

### 2.4 What is fragile

- **The API is undocumented** and could change shape or close at any time. The project handles this well: validation
  fails loudly, and the README has a runbook. Any change in access policy (rate limits, a login, Cloudflare) would stop it.
- **Only "today" is collected.** A missed day permanently loses turnover, foreign flow and the TRI levels for that day;
  prices are recoverable for one year only. 2026-10-05 is the proof (F4).
- **The PDFs behind ownership and fundamentals are not kept**, only their text. If a re-parse ever needs a table
  `pdftotext` mangled, the PDF has to be fetched again from cdn.cse.lk while it still exists.
- **Hard-coded numbers.** Risk-free 9.9%, ERP 6%, cost per side 1.12%, withholding 0%, portfolio size Rs 5 mn,
  liquidity and drift thresholds (`config/portfolio.yaml`). The risk-free rate is typed by hand even though the bond
  database already measures the 12-month bill: 9.93% on 2026-10-09.
- **GitHub cron is late every day** (5–6 h). This is harmless now because the API serves the session until the next
  open. If a run slips past 09:30 the next morning in Colombo, that day is lost.
- **One person's settings are built in**: watchlist, excluded names (conflict of interest), `my_book`, and portfolio size.
- **No holiday calendar.** Holidays are inferred from the ASPI calendar; the banner and the dealings lag ignore them.
- **Two of five session-level fields exist only for the current session** (TRI level, market turnover). History began
  on 2026-10-01 and cannot be backfilled.

---

## 3. Bond relative value (Nelson-Siegel)

A Python pipeline scrapes the Public Debt Management Office (PDMO) pages on treasury.gov.lk, downloads daily Excel
and PDF reports, parses them into one SQLite file, fits a Nelson-Siegel curve each day, scores each bond's distance
from the curve against its own history, and writes a static page (`docs/index.html`, served by GitHub Pages from
`/docs`) plus a text readout.

### 3.1 How data is collected

| Item | Detail |
|---|---|
| Source | `https://www.treasury.gov.lk`: four index pages per year. Daily report (`/web/report-daily-report/section/<year>`), trade summary, bond auction results and bond issuance announcements. Files are served from `/api/file/<uuid>`. |
| Files | Daily Summary Report (legacy `.xls`, despite "PDF" links): dealers' average bid/offer by series label. Outright Transactions Volumes (`.xls`): volume per ISIN, dated T+2. Secondary Market Trade Summary (PDF): executed trades per ISIN, OHLC + weighted average yield. Auction results and issuance announcements (PDF): ISIN ↔ series label, auction yields, amounts, coupon dates. Auction releases are also published in Sinhala and Tamil; only English is parsed. |
| Schedule | `daily-update.yml` runs twice daily on purpose, at 20:00 and 02:00 UTC. Observed commits: about 22:00–00:06 UTC and 07:34–08:33 UTC. Each run re-scrapes the index pages and processes only files not yet parsed `ok`. |
| Politeness | Sequential, 1.5 s apart, 4 retries (2/4/8/16 s), 60 s timeout, honest User-Agent (`pipeline/fetch.py`). |
| Failure handling | The site sits behind a **Sucuri firewall** that sometimes serves a JavaScript challenge with HTTP 307. `polite_get` treats that as an error rather than content. An index page that parses to zero entries counts as a failure; the run only aborts if *every* index fails. A file that fails to parse is recorded in `files.parse_status='failed'` and retried next run. There is no alert beyond GitHub's failure email. |
| Idempotency | Upserts keyed on (obs_date, isin, source) etc. Amended reports overwrite the original, because files are processed oldest-posted first. |

### 3.2 Where history is stored

One SQLite file, `data/sgcp.sqlite` (22 MB), committed to `main` by the bot after every run that changes it. The
git pack is already **144 MB after about six weeks** of daily commits, because each commit stores a new copy of the
binary database. At this rate the repository passes 1 GB within about a year.

| Table | Rows | Range | Notes |
|---|---|---|---|
| `bonds` | 59 | — | Includes 10 `SYN:<maturity>:<coupon>` keys for bonds no source names by ISIN. |
| `observations` | 11,160 | 2025-12-01 → 2026-10-09 (210 days) | 11,146 dealer quotes (`pdmo_daily`) + 14 auction yields. About 52–54 bonds a day. |
| `trade_summary` | 3,204 | 2025-12-01 → 2026-10-08 (208 days) | 2,391 bond rows + 813 bill rows. |
| `auctions` | 125 | 2025-12-11 → 2026-10-13 | 17 auction dates. |
| `curve_fits` | 210 | 2025-12-01 → 2026-10-09 | One per day. |
| `curve_residuals` | 13,414 | same | Quotes in the fit plus held-out trades. |
| `bond_signals` / `switch_signals` | 9,285 / 86,829 | 2026-01-14 → 2026-10-09 | **Rebuilt in full on every run.** |
| `files` | 678 | report dates 2025-12-01 → 2026-10-13 | URL, sha256, parse status and note for every file. All 678 parsed `ok`. |
| `fills` | 0 | — | For your own executions; never used. |

**Gaps and duplicates found:**

- Quotes exist for every weekday from 2025-12-01 to 2026-10-09 except 15 days, all of which match market holidays.
- **2026-01-26 has quotes but no trade summary,** while 2026-01-29 has two trade-summary files. That points to a
  mislabelled file at the source (one of the two "29th" files may really be the 26th). It cannot be checked without
  re-downloading, because the raw file was not kept. 2026-09-29 also has two files.
- No duplicate keys.
- **History has been rewritten in place.** Comparing the first committed database (2026-09-01) with today's: 724 of
  the 8,069 quote rows from that date now have different bid/offer/mid yields, and 14 have a different volume. The
  example I checked was a genuine fix. Bond LKB00931E153 was first matched to the administered 13.00/12.00 quote of a
  restructuring bond; it was later re-matched to its real ~10% quote after the ISIN-join fix of 2026-09-02. Normal
  operation also changes recent rows, because volumes arrive two business days after quotes (13 rows from 2026-09-18
  changed). Neither change is recorded anywhere: the database cannot say what it showed on a given past day.
- **Quotes are filtered out at ingest, not just at fitting.** About 38 quotes a day for restructuring-era bonds
  (step-coupon, administered) are left out of `observations` entirely. The only record of them is a count in the
  parse note. With the raw files thrown away, those quotes exist only on the PDMO website.
- Coverage starts on 2025-12-01 because the PDMO website publishes nothing older in these sections.

### 3.3 Every model and calculation

| # | Model / calculation | Code | Inputs | Outputs | Key assumptions |
|---|---|---|---|---|---|
| B1 | Bond identity resolution (ISIN by series label, letter-insensitive label, maturity, or synthetic cash-flow key) | `pipeline/ingest.py`, `series.py`, `isin.py` | quote sheet, auction/issuance releases | `bonds`, ISIN on each quote | A synthetic key may split a bond into two but never merge two. Step-coupon and administered bonds are excluded. |
| B2 | Volume dating (derived from maturity − remaining years × 365) | `parse_daily.py` | volumes file | `observations.volume_lkr` | The free-text titles are unreliable, so the date is derived from the data. |
| B3 | Daily Nelson-Siegel fit | `curves/nelson_siegel.py`, `curves/fit.py` | dealer quote mids, maturities | `curve_fits`, `curve_residuals` | Fixed λ; weighted least squares with weights 1/spread² (spread floored at 1 bp, capped at 300 bp); τ = years to maturity (yield vs maturity, not cash-flow based); τ ≥ 0.08; ≥ 6 bonds; step-coupon excluded. |
| B4 | λ calibration | `curves/fit.py --calibrate` | all history | `curve_settings.lambda_years` = 2.82 y | The smallest λ within 2% of the best pooled error. **Chosen using the whole sample**, which means look-ahead for any backtest. Recalibrating **refits all history in place**. |
| B5 | Trade check (held out of the fit) | `curves/fit.py` | trade summary | `trade_bias_bp` (median), `trade_rmse_bp` | Trades are not in the fit; they measure it. |
| B6 | Bond z-score ("rich/cheap") | `signals/zscore.py` | residuals | `bond_signals` | Trailing 60 days, excluding the scored day, ≥ 30 observations. |
| B7 | Switch-pair z-score | `signals/zscore.py` | residuals, auctions | `switch_signals` | Maturities within 2 years, unless both bonds were auctioned. |
| B8 | Liquidity tiers (core / active / wider) | `signals/liquidity.py` | trades, auctions | tier per bond | Core = auctioned within 120 days and traded on ≥ 8 of 60 days; active = ≥ 10 of 60. Trade-feed lag handled separately, with a 7-day cap. |
| B9 | Execution gap (trades vs quote mid) | `signals/execution.py` | residuals | gap estimate | Trailing 20 days (chosen out of sample), ≥ 8 observations, not split by tenor. |
| B10 | Carry, rolldown, modified duration, carry per duration | `signals/carry.py` | curve, quotes, bill trades | core-book columns | Funding = 12-month bill (240–380 days, 5-day volume-weighted) **+ 5 bp "per the desk"**. 3-month rolldown horizon. Semi-annual coupons. Flat-yield pricing, no day count. Tax ignored. |
| B11 | Reversion statistics and "expected capture" | `signals/run.py`, `validate.py`, `report.py` | z-scores, forward changes | `signal_stats`; "verdict" column | 10-day horizon, \|z\| > 2 and > 3. **In-sample on one 9-month regime**, as the README itself says. |
| B12 | Auction-cycle study | `signals/validate.py` | residuals, auctions | printed table, `post_auction` flag (14 days) | 47 events; "suggestive, not established". |
| B13 | Dashboard carry-forward of the last trade | `dashboard/build.py` | trades | hollow markers | Dropped after 10 days. |

### 3.4 What is fragile

- **F1: hard-coded years.** All four `*_INDEX_URLS` in `pipeline/config.py` list 2025 and 2026 only. From
  1 January 2027 the 2026 pages still parse to non-zero entries, so "zero entries means failure" will not fire. The
  tool will look healthy and collect nothing.
- **F2: no raw archive** (see section 3.2). `files.sha256` makes a re-download verifiable, but only while the PDMO
  still serves the file.
- **Scraping HTML index pages** whose markup is hand-edited: split anchors, stray spaces in dates, links pointing at
  the wrong row. `DATA_NOTES.md` documents dozens of quirks the parser survives. A template change on treasury.gov.lk
  breaks it.
- **The Sucuri firewall.** A stricter bot rule would block GitHub's US runners entirely.
- **Rewriting in place** (B4 recalibration, signals rebuilt wholesale, ingest overwriting upserts). There is no method
  version on stored outputs, so today's database cannot reproduce what the page showed last week.
- **Hard-coded values:** four "watched" ISINs in the workflow file; the 5 bp funding spread; λ fallback 2.5;
  thresholds throughout `signals/`.
- **Repository bloat** from committing the binary database (144 MB pack and growing by about 1–2 MB a commit).
- `signals.txt` has a formatting fault: when the traded-age field is wide, columns run together (`12.0512.16/23d`).

---

## 4. Crypto terminal

A Python pipeline (uv, polars) fetches from about 20 free APIs, stores normalised Parquet on a separate orphan `data`
branch, computes metrics and signals, and writes JSON artefacts. A Vite + TypeScript site renders 13 pages, and the
daily workflow deploys it to GitHub Pages. The project is roughly half built: P1–P4 and P6 are live; portfolio (P5)
and validation (P7) are not started.

### 4.1 How data is collected

| Dataset family | Source and endpoint | Key? | Notes |
|---|---|---|---|
| Daily and hourly OHLCV | `data-api.binance.vision` (Binance's market-data host; `api.binance.com` returns 451 from US runners), Coinbase Exchange candles, Hyperliquid `candleSnapshot` | no | Stored **per venue, never merged**. CoinMetrics `PriceUSD` supplies BTC 2010–2017. |
| Caps, supply, rank, top 100, global | CoinGecko `/coins/markets` etc. | Demo key | 429s within seconds without a key. |
| Protocol fees, revenue, TVL, stablecoins, hacks | DefiLlama (`api.llama.fi`, `stablecoins.llama.fi`) | no | `/emissions` and `/treasuries` are paid (402); unlocks are hand-kept in `config/unlocks.yaml`. |
| BTC/ETH on-chain | CoinMetrics community API | no | 31 metrics free; realised cap and others are derived (D005). |
| Funding, OI, mark, depth | Hyperliquid `metaAndAssetCtxs`, `predictedFundings` (also returns Binance and Bybit rates), `fundingHistory`, `l2Book` | no | OI from Hyperliquid only (D021). |
| Options, DVOL, basis | Deribit public API | no | |
| Macro (32 series) | FRED API | yes (set) | Stored with `vintage_fetched_at`, so revisions are traceable. |
| Sentiment | alternative.me Fear & Greed; Wikimedia pageviews | no | |
| Geopolitics | GDELT doc API (8 s spacing, time budget), GPR index `.xls` (matteoiacoviello.com), EPU CSV (policyuncertainty.com), Polymarket Gamma, Kalshi | no | |
| Governance, news, calendar | Snapshot GraphQL, Aave Discourse RSS, CoinDesk RSS, SEC RSS, Federal Reserve FOMC page, GitHub API | no | |
| **Schedule** | `daily.yml` at 00:20 UTC (observed 05:46–06:48 UTC, ~5 h late); `keepalive.yml` weekly; `ci.yml` on push | | The planned 2-hourly `light.yml` was never built, so "snapshots" are taken once a day. |
| **Failure handling** | Every fetch writes a `source_health` row (8,800 so far: 8,038 ok, 330 needs_key, 186 http_error, 163 skipped, 83 empty). One failing source never fails the build; the fetch step ends `|| echo …`. Last good values carry forward with a stale flag. | | No alerting. Failures are visible only on `/source-health`. |

### 4.2 Where history is stored

The orphan `data` branch holds 585 Parquet files, about 9 MB. It is checked out into `data/` during the build and
committed back after it. The code branch's git pack is 71 MB.

| Group | Files | Rows | Range | Re-fetchable? |
|---|---|---|---|---|
| `ohlcv/{sym}/{venue}/{year}` | 292 | 89,110 daily + 2,865 hourly | 2010 → 2026-10-10 | Yes, from the venues (while their history endpoints last). |
| `onchain/btc`, `onchain/eth` | 33 | 177,736 | 2010 → 2026-10-10 | Yes (CoinMetrics). |
| `onchain/cg_*` (market cap, supply) | 52 | 19,484 | 2025-09-27 → | Partly: CoinGecko history is capped at 365 days on free plans. |
| `onchain/funding_*` | 21 | 2,854 | 2026-05-29 → | Yes (Hyperliquid funding history). |
| `fundamentals/{protocol}` | 76 | 111,075 | 2011 → 2026-10-11 | Yes (DefiLlama). |
| `macro/{series}` | 32 | 137,250 | 1990 → 2026-10-09 | Values yes; **vintages no**. |
| `snapshots/*`: supply, top100, global, perp_contexts, depth, funding_by_venue, event_markets, feeds, governance, stablecoins | ~30 | ~25k | **2026-09-26 → 2026-10-11** | **No.** These are the irreplaceable crypto data. |
| `snapshots/funding_hourly_*` | 42 | 127,559 | 2026-05-29 → | Yes (Hyperliquid funding history). |
| `snapshots/risk_gpr`, `risk_epu`, `security_incidents`, `gdelt_themes`, `calendar` | 10 | ~128k | 1985 → | Mostly yes (full files re-downloaded). |
| `source_health.parquet` | 1 | 8,800 | — | No (operational log). |

**Gaps and duplicates found:**

- None of the 66 daily OHLCV series (symbol × venue) has a missing day; no duplicate (symbol, venue, date, interval).
- **2026-09-29: no CoinGecko snapshot** (`supply`, `top100`). Every other snapshot table has all 16 days. That was the
  day the repo went private and the site was taken down. Supply history for that day is derived from market cap ÷ price
  instead.
- **Writes are upserts, not appends** (`pipeline/store.py`): a re-fetch replaces rows with the same key. A venue
  restating a candle would silently overwrite the stored one.
- **Raw responses are not kept.** The HTTP cache (`data/raw`) works within a run, but the commit step excludes it
  (`rsync … --exclude='raw'`).
- **The plan proposes squashing the data branch** (`docs/PLAN.md` §3.1, D008). The mitigation it describes, "a
  monthly immutable Parquet archive kept unsquashed", has not been built.

### 4.3 Every model and calculation

| # | Model / calculation | Code | Inputs | Outputs | Key assumptions |
|---|---|---|---|---|---|
| X1 | Pine Script v6 indicator semantics (RMA, EMA seeding, RSI, ATR, DMI/ADX, CCI by mean absolute deviation, StochRSI, MFI, Supertrend, Ichimoku, VWAP, OBV, CVD) | `signals/indicators.py` | OHLCV | indicator series | Follows TradingView's definitions, not textbook ones. |
| X2 | **MiniLizard regime score** | `signals/minilizard.py` | Binance daily bars (substitute venue for 5 names); hourly bars for CVD | score ±100, BULL/NEUTRAL/BEAR, **"GET IN" / "GET OUT"** | Blocks: structure ±35, trend ±30 (×1.4 when ADX > 25), momentum ±20, volume ±15; 10-point hysteresis; 300-bar warm-up. **Parity with the Pine source is unverified**: no reference values exist, and the test is skipped. |
| X3 | BTC quantile bands | `signals/quantile.py` | BTC price 2010 → | 7 quantile curves | log₁₀ price on (ln t − μ) with tail-shared quadratic curvature; 17 parameters; LP via HiGHS. A "replication gate" must reproduce μ ≈ 7.9914, b_HI ≈ −0.326, b_LO ≈ −0.024. |
| X4 | Normalised risk (0–1) and composites | `metrics/risk.py`, `config/composites.yaml` | any metric | risk series, composites | Detrended against a refitted log trend; expanding percentile excluding the scored day; 2-year warm-up. Weights in config. |
| X5 | Cycle analogs and risk scorecard | `metrics/cycle.py` | BTC price, on-chain | ROI-from-peak and from-bottom bands, days since, midterm tables | Cycles detected from all-time highs (four cycles, D034). "ROI" means a price ratio. |
| X6 | Key levels and the 50-week rule | `metrics/levels.py` | daily bars → weekly | levels, confirmations | Two consecutive weekly closes above the 50-week SMA; the open week is excluded (D033). |
| X7 | Valuation: multiples (30/90/365 days), net holder yield, dilution, grades, reverse DCF | `metrics/valuation.py` | CoinGecko caps and supply, DefiLlama fees | screen, grades A–F | Supply = cap ÷ price (D014). Supply-spike cleaning (D015). A grade is judged on the current window. |
| X8 | Derivatives: annualised funding per venue, OI change and z-score, OI/cap, basis, DVOL | `metrics/derivs.py` | Hyperliquid, Deribit | derivatives page | Each venue annualised by its own funding interval (D017). OI is Hyperliquid only. |
| X9 | Breadth: dominance (ex-stables), forward-built A-D line, % above MA, correlations | `metrics/breadth.py` | snapshots, OHLCV | breadth page | Measured over the tracked universe, not the top 100. Not backfilled, to avoid survivorship bias. |
| X10 | Sector indices (equal and cap weight), fee growth, relative rotation graph | `metrics/sectors.py` | OHLCV, caps, fees | sectors page | RRG is an open approximation (N = 10, M = 4 weeks), not the proprietary JdK method. |
| X11 | Macro: net liquidity and 13-week change, policy path, own-history percentiles, 0–1 composites | `metrics/macro.py` | FRED | macro page | Unit conversion (millions vs billions) pinned by a test. |
| X12 | Geopolitics: theme spike z-score, oil chain, GPR threat/act, EPU, event odds | `metrics/geopolitics.py` | GDELT, GPR, EPU, Polymarket, Kalshi | geopolitics page | Baseline excludes the recent window. |
| X13 | Catalyst radar and low-cap screener | `metrics/radar.py` | snapshots, feeds | ranked list | Liquidity gate before ranking; bounded components, plain sum; "ranks attention, not return". |
| X14 | News tagging, governance, security incidents | fetchers + `radar.py` | RSS, Snapshot, DefiLlama hacks | tagged items | Whole-word match with crypto context (D025). |
| X15 | Deployment tracker, buy order, tiers, drift, next buy (P5, partly scaffolded) | `registry.py`, `config/assets.yaml`, `weights.yaml` (secret) | your target weights | "unplaced in buy order", "next buy" | **Personal portfolio management.** |

### 4.4 What is fragile

- **~20 free APIs**, several unofficial or rate-limited: GDELT per-IP limits, CoinGecko 429s, Binance geoblocked from
  the US, Bybit 403, Stooq unreachable, Farside blocked (so no ETF flows), beaconcha.in now needs a key.
- **The irreplaceable snapshots exist once, on one GitHub branch**, with no raw responses and a plan to squash.
- **Hand-maintained YAML is market data**: `config/unlocks.yaml`, `calendar.yaml` and treasuries.
- **The repository's visibility controls the site.** Taking the repo private on 2026-09-29 unpublished the site, and
  the workflow now re-enables Pages on each run.
- **A stuck run blocks every later run** through the concurrency group (seen 2026-09-27).
- **Unverified parity** for the headline MiniLizard signal.
- **Personal configuration is public.** The buy order and tier structure sit in the committed `config/assets.yaml`.
  Target weights come from a GitHub secret, but if set they feed panels on a publicly served site.

---

## 5. What is duplicated across the three repositories

| Concern | CSE | Bonds | Crypto | Consolidation opportunity |
|---|---|---|---|---|
| Polite HTTP client (User-Agent, pause, retry, backoff, timeout) | `cse/http.py` | `pipeline/fetch.py` (+ firewall detection) | `pipeline/http.py` (+ per-host spacing, raw cache) | One shared client with per-source rate limits, challenge detection and raw capture. |
| Storage layer | append-only CSV (`storage.py`) | SQLite upserts (`db.py`) | Parquet upserts (`store.py`) | One database, plus one raw archive. |
| Run log / health | `data/runs.csv` | `files` table | `source_health.parquet` | One `collector_runs` table plus a gap check. |
| Static site builder | Jinja2 + Chart.js | Python f-strings + inline SVG | Vite + TypeScript | One web app and one design system. |
| Palette and styles | template CSS | `dashboard/palette.py` | `styles.css` | Shared tokens. |
| Staleness logic | browser banner | feed-lag notes | cadence-aware badges | One server-side freshness model per dataset. |
| GitHub Actions "fetch → commit to repo → deploy Pages" | yes | yes | yes | Replace with a scheduler writing to a database. |
| Trailing z-score / percentile helpers | — | `signals/zscore.py` | `metrics/risk.py`, `derivs.py`, `geopolitics.py` | Shared stats library with one documented convention (exclude the scored point). |
| Liquidity gate before ranking | universe filter | `signals/liquidity.py` | `radar.py` (explicitly copied from bonds) | A common pattern for all screens. |
| Sri Lankan business calendar | inferred from ASPI | none (weekday counts) | — | One holiday table (CSE and bond market days differ; for example 2026-01-01 and 2026-01-07 had bond quotes but no CSE session). |
| Risk-free / T-bill | typed in by hand (9.9%) | measured from bill trades | FRED for US rates | CSE models should read the bond layer's measured bill rate. |
| Method documentation | `METHODS.md`, `API_NOTES.md` | README, `DATA_NOTES.md` | `PLAN.md`, `DECISIONS.md`, `SOURCES.md` | A per-model doc inside each plug-in, plus one decisions folder. |
| Hard rules (no fabrication, append-only, no look-ahead) | yes | yes | yes | Already consistent: carry over as tests. |

---

## 6. Fragility register

Severity reflects the cost to the business if the issue fires, not effort to fix. "Fix where" says whether it needs a
change to an existing repo (which needs your approval under the hard rules) or can wait for the new platform.

| ID | Issue | Tool | Severity | When it bites | Fix where |
|---|---|---|---|---|---|
| F1 | Index URLs hard-coded to 2025/2026; collection silently stops | Bonds | **Critical** | 1 Jan 2027 | **Old repo, before year end** (or the new collector must be live in parallel by then) |
| F2 | Raw PDMO files discarded; parsed rows rewritten in place; administered quotes dropped at ingest | Bonds | **High** | Whenever PDMO removes old files | New raw archive (could start immediately as a separate read-only archiver) |
| F3 | Crypto raw responses discarded; irreplaceable snapshots on one branch; squash planned | Crypto | **High** | Any accidental force-push or squash | New raw archive; do not squash |
| F4 | Daily-only collection; missed run = permanent loss of turnover; 2026-10-05 already lost | CSE | **High** | Every missed run | Backfill 2026-10-05 prices now; new collector with a gap check |
| F5 | Only copy of all history is three public GitHub repos | All | **High** | Account or repo loss; anyone can copy the history | Second-location backup; decide on visibility (Q3) |
| F6 | GitHub cron runs 5–6 h late; a skipped run is not detected | All | Medium | CSE: if a run slips past the next open | Managed scheduler plus a gap alert |
| F7 | Undocumented CSE API / scraped PDMO pages / firewall | CSE, Bonds | Medium | Any site change | Validation exists; add alerting; seek formal data access (Q4) |
| F8 | Stored model outputs not versioned (bond signals rebuilt, λ recalibration rewrites history; crypto artefacts recomputed) | Bonds, Crypto | Medium | Any method change | Method version on every stored output |
| F9 | Hard-coded parameters (risk-free 9.9%, ERP, costs, 5 bp funding, watched ISINs, unlock YAML) | All | Medium | Silently stale | Config with owners and dates; derive what can be derived |
| F10 | Bond repo pack 144 MB and growing ~1–2 MB per commit | Bonds | Medium | ~1 GB within a year | Database leaves git |
| F11 | Crypto source failures never fail the job; no alerting anywhere | Crypto (all) | Medium | Silent decay | Alerting on health and gaps |
| F12 | Static sites publish full data as files; nothing can be gated | All | Medium (for the business) | At launch | Server-side API (Layer 5) |
| F13 | Personal settings in code/config (watchlist, `my_book`, portfolio size, buy order, weights, "the desk") | All | Medium | At launch | Strip from product; per-user settings later |
| F14 | Source data errors (CSE period dates 2030; PDMO 2026-01-26 missing / 01-29 doubled) | CSE, Bonds | Low | Already present | Data-quality checks; enquiry with source |
| F15 | Stuck run blocks the concurrency queue | Crypto, CSE | Low | Occasionally | Timeouts on every step |
| F16 | Holiday-unaware staleness and lag counts | CSE | Low | Every holiday | Official holiday calendar |
| F17 | Repo visibility flip unpublishes Pages | Crypto | Low | On visibility change | Moot once hosting moves |
| F18 | Browser-only computation | CSE (stale banner, per-owner cumulative chart) | Low | — | Little logic lives in browsers today; good for migration |

---

## 7. Data sources and commercial redistribution

**Read this as a to-do list for an enquiry, not as clearance.** "Free to call" is not the same as "free to resell".
A paid product that shows the data, stores its history or derives numbers from it needs the rights to do so. Rows
marked "unknown" need a written enquiry; I would not launch on them without one.

| Source | Used by | What its terms say (as found 2026-10-11) | Status |
|---|---|---|---|
| CSE API (`cse.lk/api`) and announcement PDFs (`cdn.cse.lk`) | CSE | No published API or website terms found. The API is undocumented. The CSE distributes market data commercially through vendors (for example, ICE lists a CSE feed), which suggests a vendor/redistribution licence is the normal route. Announcement PDFs are company filings. | **Unknown, needs enquiry: likely requires a CSE market-data licence.** The most important enquiry. |
| PDMO / treasury.gov.lk (daily reports, trade summaries, auction releases) | Bonds | No terms page found. Government publication. | **Unknown, needs enquiry** (PDMO / Ministry of Finance). Ask also for an official feed and older archives. |
| Binance (`data-api.binance.vision`) | Crypto | The Binance Vision dataset terms PDF is titled "Terms of Use (Non-Commercial)" and is subject to Binance's general terms. | **Likely non-commercial; needs enquiry.** |
| Coinbase Exchange candles | Crypto | Market Data Terms: licence "solely for you", "personal or research purposes", not "to build an application intended for use by end users outside your own organization". Coinbase runs an authorised redistribution partner programme. | **Not permitted as-is.** Use a licensed redistributor or drop. |
| Hyperliquid API | Crypto | No data licence found. | Unknown, needs enquiry. |
| CoinGecko | Crypto | API Terms (5 Sep 2025): licence depends on plan; paid plans may "charge for your services and products that incorporate" the API; attribution "Powered by CoinGecko" required; storage discouraged, refresh caches within 24 h; no redistribution of API access. | **Needs a paid plan**, and storing history needs explicit confirmation. |
| CoinMetrics community API | Crypto | Creative Commons **BY-NC 4.0**. | **Not permitted for commercial use.** Pro licence or replace. |
| DefiLlama | Crypto | Terms (24 Jun 2025): site licence is "personal, non-commercial"; prohibits "republish the data in any form without permission" and commercial exploitation "without prior written consent"; liquidated damages up to USD 100,000 per breach. | **Not permitted without written permission** (or its paid API terms). |
| FRED (St. Louis Fed) | Crypto | Must display "This product uses the FRED® API but is not endorsed or certified by the Federal Reserve Bank of St. Louis" and link the terms. Third-party copyrighted series need the owner's permission for anything beyond personal use. At least one stored series, `BAMLH0A0HYM2` (ICE BofA high yield spread), is third-party owned. | **Permitted with notice, except third-party series**: each of the 32 series must be checked for a copyright note. |
| alternative.me Fear & Greed | Crypto | "Commercial use is allowed as long as the attribution is given right next to the display of the data." | **Permitted with attribution.** |
| GDELT | Crypto | "Unlimited and unrestricted use for any academic, commercial, or governmental use"; redistribution with citation and link. | **Permitted with citation.** |
| GPR index (Caldara–Iacoviello) | Crypto | Academic dataset; citation requested; no licence found. | Unknown, needs enquiry (likely fine with citation). |
| EPU (policyuncertainty.com) | Crypto | No licence found. | Unknown, needs enquiry. |
| Deribit public API | Crypto | No data licence found. Exchanges typically licence redistribution separately. | Unknown, needs enquiry. |
| Polymarket Gamma, Kalshi | Crypto | Not reviewed in detail. | Unknown, needs enquiry. |
| Snapshot, Aave Discourse, CoinDesk RSS, SEC RSS, Federal Reserve FOMC page, Wikimedia pageviews, GitHub API | Crypto | Headlines and links from news RSS are third-party copyright (showing headlines with links is common, but check). SEC and Federal Reserve publications are US public-sector material. Wikimedia pageview data is believed to be public domain (CC0). Snapshot and Discourse: unknown. | Mixed; low priority, confirm before launch. |
| TradingView Lightweight Charts (library) | Crypto | Apache-2.0; attribution required. | Permitted with attribution. |

**Two further intellectual-property questions (not data feeds):**

- **The "Cowen memos"** (`docs/DECISIONS.md` D011) are confidential third-party research. They shaped the crypto
  scorecard and liquidity composites. The project was careful not to copy text, names or branding, but a commercial
  product built on a paid service's confidential material carries risk. A lawyer should confirm this, and you may want
  to rebuild those modules from public literature only.
- **The quantile-band "replication gate"** (X3) reproduces specific published parameters. Whose model is it, and is
  it under a licence?

---

## 8. Advice language already in the tools

The brief's hard rule is "information, tools and education only". Below is what exists today. All of it was
reasonable in a personal tool; none of it can be copied into the product as is. Each item needs a decision in
Phase 1 (rename and reframe, keep as education, or drop). Phase 1's copy lint will need a way to allow factual uses
such as "directors bought Rs 12 mn" while blocking imperatives such as "buy the cheap".

| Where | What it says or does | Why it is a problem |
|---|---|---|
| Bonds dashboard (live) | "Switch candidates" table with columns **buy / sell** and a **verdict**; "where a decision can be executed in size"; "Cheap / Rich" lists | Reads as a trade recommendation. |
| Bonds `signals.txt` (public in repo) | "SWITCH CANDIDATES — both legs in the core book; **buy the cheap, sell the rich**" | Imperative. |
| Bonds README | "what you trade", "Read those against costs before trading" | Personal-desk framing. |
| CSE Panel D (live) | "Rebalance flags and **trade list** · scaled to Rs 5.0 mn": "**+ add / − trim**" with share counts | A personalised order list. |
| CSE Panel D | Model portfolios (max Sharpe etc.) maintained as a live track record with trades | A model-portfolio service may count as advice; needs legal view. |
| CSE flows (live) | "Where insiders are buying", "Who is buying and selling" | Factual (disclosed dealings), but needs the lint's allow-list and a clear "disclosed transaction" framing. |
| Crypto engine | "**GET IN**" / "**GET OUT**" signals; "drawdown filter" framing | Imperative trading signals. |
| Crypto config/site | "buy order", "next buy", "deployment tranches", "exit mechanism" (P5, partly built) | Personal portfolio management. |
| All three | Disclaimers exist but differ ("Not investment advice", "Nothing here is a recommendation to buy or sell anything") and live in each template | Needs the single disclaimer registry the brief asks for. |

---

## 9. What this means for Phase 1 (preview, not decisions)

Phase 1 will justify each of these properly. I list them now so you can react early:

- **The default design fits the evidence well.** All three tools already separate fetch, store and compute, so the
  layer model maps across cleanly.
- **The raw archive (Layer 1) is the most valuable new piece**, given F2/F3, and probably the first thing to stand up,
  even before the database.
- **GitHub Actions cron should not be the production scheduler** (F6). It is fine for CI.
- **Scale is small.** All structured history fits comfortably in a small managed Postgres. The CSE report texts
  (82 MB) and the raw files belong in object storage.
- **Data rights may decide which crypto features survive.** Several free sources cannot be resold. Phase 1 will price
  the paid alternatives at 0/500/5,000 users and will likely propose launching with CSE and bonds first.
- **Method versioning already exists in the CSE lab** (`series`). The plug-in manifest's `method_version` generalises it.
- **The CSE model record and the bond signals both need re-framing** before any public tier; see section 8.

---

## 10. Questions for you

Grouped by urgency. The first three affect data being collected right now.

**Urgent: data safety before Phase 2 (each needs your explicit approval because it touches the old repos or their sources)**

1. **Bond collector year rollover (F1).** May I make a minimal change to the Nelson-Siegel repo to add 2027 index URLs
   (or derive the year automatically) before 1 January 2027? If not, the new bond collector must be running in
   parallel by mid-December.
2. **Recover CSE session 2026-10-05 (F4).** May I backfill its prices from the one-year chart endpoint (marked as
   backfill, turnover left empty)? It can be done any time before about October 2027, but sooner is safer.
3. **Start a raw archive now (F2, F3).** May I set up, in this new repo, a small read-only archiver that downloads and
   stores the PDMO files and crypto snapshot responses, without touching the old repos? Alternatively, do you or the
   co-founder have any local copies of the bond `data/raw/` folder from the original backfill?

**Business and legal**

4. **Data licences.** Are you willing to approach the CSE (market-data licence) and the PDMO (permission and an
   official feed) before launch? Is there a budget ceiling for paid data, especially crypto?
5. **Legal advice.** Will you engage a Sri Lankan lawyer on: (a) the SEC Act 2021 and investment-adviser registration
   for model portfolios, bond relative value and screens; (b) the CBSL position on offering crypto analysis to Sri Lankan
   retail; (c) the Cowen-memo and quantile-model IP questions?
6. **Where is the company incorporated, and where are you based?** Commit timestamps are mostly UTC+10/+11, and the
   crypto docs mention Melbourne and an AUD toggle. This affects payments (PayHere needs a Sri Lankan business),
   regulator, hosting region and privacy law.
7. **Employment conflicts.** The bond code mentions a funding spread "per the desk", and the CSE config excludes NTB as
   a conflict of interest. Does either founder's employer restrict publishing market research or running this business?

**Product scope**

8. **Crypto scope.** Which parts of the crypto terminal are product rather than personal tools? The deployment plan,
   buy order, target weights and GET IN/OUT engine look personal. Who owns the MiniLizard Pine script, and is it yours
   to commercialise?
9. **CSE portfolio lab.** Keep the model portfolios as education (no trade lists, no personal sizing), keep them only
   for Professional, or drop them from the product?
10. **Bond tiers.** The brief puts "bond analytics" in the Professional tier. Which parts: the curve, residuals,
    carry, or switch analysis? Do you expect professional users to be institutions (dealers, fund managers), whose
    rules may differ from retail?
11. **Repository visibility.** All three repos and their histories are public today. Should they go private once
    the new platform takes over (which ends their GitHub Pages sites on a free plan), or stay public as a free showcase?

**Practical**

12. **Accounts.** Will the business own a GitHub organisation and the cloud accounts (Supabase etc.), with you and the
    co-founder as members? Who should receive alerts?
13. **Holiday calendar.** Do you know an official source for CSE and bond-market holidays, or should we keep inferring
    them from the data?
14. **Private files.** The crypto repo's `private/` folder (full spec, reference memos, Pine source if any) is not in
    the repo. Will any of it be needed for the parity tests in Phase 3?
15. **Language.** For Sinhala and Tamil, is there a preferred glossary of market terms? The PDMO's own trilingual
    auction releases could be a starting point.

---

## Appendix A. Baseline checksums for migration verification

These are the reference values Phase 2's migration report will reconcile against. They are SHA-256 hashes (first 16
hex characters) at the audited commits. "Rows" means lines minus the header; quoted fields with line breaks would make
a true row count differ, and Phase 2 will count rows with a CSV parser.

| Tool | File | Rows | SHA-256 (16) |
|---|---|---|---|
| cse | `data/history/announcements.csv` | 206 | `14c3a29dbba276ae` |
| cse | `data/history/corporate_actions.csv` | 392 | `5e057486d5645da8` |
| cse | `data/history/indices.csv` | 5,382 | `89dcfd3c8ebff51c` |
| cse | `data/history/market.csv` | 7 | `434a3d9b04ca3623` |
| cse | `data/history/prices.csv` | 69,312 | `7b72e1c8540e3499` |
| cse | `data/dealings/dealings.csv` | 2,243 | `1ca96bc44597272d` |
| cse | `data/fundamentals/latest.csv` | 277 | `d0e765389912a392` |
| cse | `data/fundamentals/reports.csv` | 1,328 | `5e076da582cc8fbc` |
| cse | `data/ownership/companies.csv` | 281 | `3590633966fb1173` |
| cse | `data/ownership/holdings.csv` | 27,779 | `8b331e1da828e3f7` |
| cse | `data/ownership/owners.csv` | 2,929 | `efadefd82ac7c8fa` |
| cse | `data/raw/ownership/annual_reports.csv` | 281 | `a9853f17ce57eb4b` |
| cse | `data/raw/ownership/reports.csv` | 1,387 | `aaa0a57508a82ec2` |
| cse | `record/holdings.csv` | 1,444 | `3502b393706d6964` |
| cse | `record/nav.csv` | 20 | `77013c928eb1fae3` |
| cse | `record/trades.csv` | 732 | `dbee4fa1712f9e5e` |
| cse | `data/runs.csv` | 51 | `389384458ef01f3a` |
| cse | `data/raw/` (all files, sorted, hash of hashes) | 4,924 files | `414cd7d24b457932` |
| bonds | `data/sgcp.sqlite` | 59 bonds / 11,160 observations | `34ec862c837f334d` |
| crypto | `data` branch, 585 Parquet files (sorted, hash of hashes) | 846,530 rows | `50653dc65730bb56` |

## Appendix B. Test suites at the audited commits

| Tool | Command | Result (run offline, 2026-10-11) |
|---|---|---|
| CSE | `python -m pytest -q` | 240 passed |
| Bonds | `pytest -q` | 132 passed |
| Crypto | `uv run pytest -q` (against the `data` branch snapshot) | 290 passed, 1 skipped (MiniLizard parity: no reference values) |
