# Changelog

## 2026-10-18 — Feedback, the weekly e-mail, calendars to 2027, data rights

- Feedback (Phase 4b, no accounts needed): "Was this page useful?" on every page and a short form at `/feedback`.
  The website can only call `community.submit_feedback()` (migration 0012), which checks every field and limits
  senders (30 a sender an hour, 5 messages; 2,000 an hour in all); it cannot read the table. Addresses are never
  stored, only a keyed hash (`FEEDBACK_KEY_SECRET`) kept seven days. The owner reads it with
  `python -m data_platform.jobs.feedback`.
- The weekly e-mail per market, built once per tier through the tier check (`web/lib/email/`), with HTML and plain
  text; preview at `/email/cse` and `/email/bonds`; the leak suite checks the bond e-mail. Sending waits for accounts.
- Both trading calendars list every bank holiday to the end of 2027 from the CBSL's published lists; every past
  closure was checked against the data by query. 1 and 7 January 2026 (CSE only) stay unexplained.
- The CSE's terms re-read in a browser: both clauses quoted in `config/sources.yaml`; the lawyer's list and the
  roadmap cover why a third-party copy (e.g. TradingView) does not help, the licence fallback and a bonds-first launch.
- The static preview exporter can limit the Pro copies of bond pages (`--pro-details N`), so the preview fits the
  511-file limit of a published page; republished 2026-10-19 with every section (439 pages).

## 2026-10-18 — Crypto section (prototype, decision 0019)

- Bitstamp collector: daily candles for ten US-dollar pairs and ETH/BTC, full backfill from 2011-09-14 (29,329
  candles, 66 requests), finished UTC days only, append-only, a daily schedule gated on `COLLECTION_ENABLED`.
  The source stays `permission_required` (a launch blocker) until its Data License Agreement is signed.
- Migration 0010: the `crypto` schema and the crypto model outputs, all with row-level security.
- Models: `crypto_market` (returns, drawdown from the high, volatility), `crypto_cycle` (long averages, Mayer
  multiple, Pi cycle lines and crossings, halvings, the cycle table, monthly returns), `crypto_trend_bands` (log
  regression and power law, re-fitted point in time, with bands). Every row is point-in-time (tested).
- Cross-checks against public reference points: 30 checks, all met (`docs/research/crypto-crosscheck.md`).
- Website: /crypto and /crypto/<asset>, three API routes, Crypto in the navigation, five glossary terms, a
  `crypto_risk` notice citing the CBSL at the top of every crypto page; the leak suite covers it (51 tests).
- The gap check understands a market that trades every day (`config/calendars/crypto.yaml`).

## 2026-10-18 — Phase 3b, part 1: CSE corporate actions and total returns

- New facts: each company's announcement list and every corporate-action detail record, kept as the CSE served
  them (migration 0009). New daily collector job `cse_api:corporate_actions` (the last 92 days of every company's
  announcements; each new detail fetched once), scheduled weekdays at 21:37 Sri Lanka time behind
  `COLLECTION_ENABLED`; the 2-hourly announcements job now keeps its detail responses as facts too.
- The old terminal's caches load from the raw archive and reconcile with its folders exactly: 281 company lists
  (6,211 rows), 529 cached and 192 session-folder detail files, same SHA-256 each side
  (`python -m data_platform.migration.cse_corporate_actions --old-repo <clone at f263830>`; report
  `docs/migration/cse-corporate-actions-reconciliation.json`). Added to "Migrate history".
- The owner's confirmations stay in `config/corporate_actions_review.yaml` (copied from the old repo, same format);
  the models job stores each new version in the database before it runs (`python -m data_platform.jobs.reviews`).
- Model `cse_corporate_actions` 1.0.0 reproduces the old `corporate_actions.csv` (392 rows at f263830, 395 at
  e05c6f3), every column; 21 notes the old append-only file kept from an earlier version of its code match the old
  code instead. Model `cse_total_returns` 1.0.0 reproduces the old `build_tris` for 294 shares and every traded close
  (69,300 at f263830, 70,416 at e05c6f3) with no difference at all, also under an illustrative set of confirmations
  that puts the rights issues in use (`python -m data_platform.migration.parity cse_corporate_actions --old-code
  <clone>`; reports `docs/migration/parity-cse-corporate-actions*.json`). Both free. Decision 0018.
- Share pages: a table of dividends and other corporate actions (confirmed or awaiting confirmation, with the PDF),
  a total-return line beside the price, and total returns in the returns table; JSON routes for both models;
  glossary entries for "ex-date" and "total return". Leak suite: 45 tests pass.

## 2026-10-18 — Fixed deposits, treasury bills and inflation (Phase 5, first part)

- Two new collectors, both rights "silent" and switched on, weekly, waiting for `COLLECTION_ENABLED`:
  - `cbsl`: the Central Bank's interest-rate tables 4.04 (monthly, January 2003 to August 2026) and 4.03 (annual,
    1990 to 2025), and the weekly treasury bill auction file (1996 to November 2025). Links are read from the
    statistical-tables pages (file names carry the update date); columns are found by their headers.
  - `dcs_cpi`: the Colombo Consumer Price Index from the DCS's PDF tables, base years 2021, 2013, 2006/07 and 2002
    (January 2003 to September 2026). Every index number is checked against the changes printed beside it.
- New schema `rates` (migration 0011): facts as published, append-only, `*_current` views, row-level security.
- New model `lk_savings_compare` 1.0.0 (free): Rs 100,000 in a 12-month fixed deposit renewed yearly and in 12-month
  bills rolled yearly, before and after the advance income tax, and after inflation, for every start month and 1 to
  10 years, with a summary for 1, 3, 5 and 10 years. Point in time (tested). The CBSL prints bill yields for May
  2002 to March 2018 after a 10% withholding tax; the model adds it back (a question for the owner, roadmap 3a).
- New page `/learn/savings` with a calculator that works without JavaScript; five glossary terms; linked from Learn
  and the home page. A new `savings` disclaimer; the site-wide data-sources line names the CBSL and the DCS.
- `openpyxl` added to read .xlsx files.

## 2026-10-16 — ZinvestIQ, retail-features plan, site preview fixes

- The product is named ZinvestIQ (decision 0017): site, package, collectors' user agent, switch-on account names.
- `docs/plan-retail-features.md`: weekly emails, feedback, an FD comparison, rebalancing signals and fewer-name model
  portfolios. What each needs, what waits for a lawyer, the proposed order, and six decisions for the owner.
  `scripts/research/fewer_names.py` measures 10–25-name versions of the old lab's portfolios.
- Collectors run against the live sources for the first time since the audit. Fixed: the CSE jobs now snapshot only
  a closed market; "Regular Trading" used to pass the old guard (finding R1, `docs/phase3-4-verification.md` §10).
  The CSE end-of-day job treats a market summary that is not out yet as a quiet retry, and runs later in the day (R3).
- Site fixes from the first visual review:
  - no repeated disclaimers;
  - legends clear of the charts;
  - sector names instead of codes;
  - movers laid out to fit;
  - no "highest turnover" without turnover;
  - small amounts shown as "< Rs 0.01 mn";
  - phone-width method pages;
  - a shorter legend label for wide bond quotes.
- The owner's visual preview of every page (computer and phone, free and Pro) was published, on data to the 2026-10-16 close.

## 2026-10-11 — Audit of Phases 2–4, and fixes

- Four independent review passes; every finding verified, then fixed or recorded
  (`docs/phase3-4-verification.md` §9).
- Data safety: scheduled jobs wait for `COLLECTION_ENABLED` (set after "Migrate history"); the PDMO collector
  survives a dead link and retries failed parses; the CSE collector finishes missing companies; migrations lock
  correctly; auction views cannot double a file; backups re-run cleanly, read every copy back and verify
  meaningfully, with a current `pg_dump`.
- Models: pair z-score rows are point-in-time and never change once computed (no more daily rewrite of history);
  `--as-of` never writes; one failure no longer stops other models; bond identity v2 checks maturity on letter-free
  labels; carry uses the absolute spread; method pages corrected.
- Website: verified TLS and timeouts for the database, grants that can only come from the tier check, 400/404 for
  bad input, preview-aware freshness, an error page, the z-score page listed by maturity, neutral colours; the
  leak suite now covers detail pages, `?date=` and the preview's last day (35 tests).
- Copy lint catches word forms, hyphenated forms, phrases across lines and look-alike characters.
- Migration 0007. Switch-on checklist rewritten as one ordered list.

## 2026-10-11 — Phases 3 and 4: models, and the free-tier portal

- Model framework: manifests with several versions (current, reference, retired), inputs restricted to what a
  model declares and fingerprinted, outputs written idempotently with every changed value kept in
  `models.revisions`, a registry that validates every plug-in, and a scheduled models job.
- Bond models ported from the old tool, version 1 reproducing it exactly on every table and against its own code:
  identity, Nelson-Siegel curve, residual and pair z-scores, liquidity tiers, execution gap, carry. The old tool's
  bond list migrated as a fact (finding P1).
- Decision 0014 delivered: bond curve version 2 fits every two-way quote; measured effect in its method page.
- CSE market summary and per-share metrics for every share and session, matching the old terminal's Panels A and B.
- The portal (Next.js): overview, stock market, shares, government bonds, paid bond analyses (locked for free
  visitors), method pages and a JSON API. One server-side tier check, a read-only database role with row-level
  security, and a tier-leak suite run in CI. Accounts stubbed until Supabase exists.
- Fixed: the "Migrate history" workflow now checks the audit fingerprints at the audited commits (finding P3).
- Copy lint extended to model and web code. Decisions 0015 and 0016. Report: `docs/phase3-4-verification.md`.

## 2026-10-11 — Phase 2: data foundation and history migration

- Platform core: content-addressed write-once raw archive (local and S3/R2), Postgres schema with database-enforced
  append-only fact tables, source register with rights gate, polite HTTP client, collector runner with run log and
  Healthchecks.io pings.
- Collectors: PDMO bonds (old parsers ported unchanged; every row stored as published; index years derived from the
  date), CSE end of day, announcements, and a weekly history job that repairs missed sessions.
- Migration by replay: all bond facts rebuilt from the 678 PDMO originals and all CSE facts from the old raw
  responses, reconciled exactly against the old tables; the missed 2026-10-05 CSE session restored; every old file
  and full-history bundle archived; all 20 audit baselines match from archived bytes; every migration is repeatable.
- Gap check with inferred trading calendars, backups (replicate, export, verify), copy lint and disclaimer registry,
  repo rules (no data, no secrets), CI on GitHub Actions (green), scheduled jobs that skip until configured, and a
  one-click "Migrate history" workflow.
- Findings: 13.00%2029A lost every day by the old matcher; three mis-dated and two never-published bond-volume days;
  a PDMO link already removed since it was first fetched (docs/phase2-verification.md §4).
- Decisions 0012 (Phase 1 approved, build before accounts, repo public for now) and 0013 (Phase 2 choices).

## 2026-10-11 — Phase 1: architecture proposal, and safety copies of existing data

- Recorded the owner's answers to the audit (`docs/decisions/0001`): the old sites stay personal tools; a source is
  used only if its terms allow commercial use or are silent; data must also live outside GitHub.
- Added `docs/architecture.md` and decision records 0002–0011. They cover: the raw archive on R2 + B2, Supabase,
  collectors on GitHub Actions with dead-man's switches, model plug-ins, the API in server routes, Next.js on Vercel,
  the data-rights policy, compliance by construction, and monitoring. Also costs at 0/500/5,000 users, the migration
  and parity plans, the two extensibility walkthroughs and what not to build yet.
- Added `scripts/` tools, all read-only towards the existing repos and sources' servers:
  - `backup_repos.sh`: complete, verified git bundles of the three repos (every branch);
  - `bond_db_history.py`: rebuilds every row version of the bond database from its 62 committed versions and
    verifies the result against all of them (1,112 overwritten quote values recovered);
  - `archive_pdmo_files.py`: re-downloads every PDMO file the bond database parsed and checks it against the SHA-256
    recorded at the time;
  - `archive_cse_history.py`: saves the CSE's one-year chart history for every share and index, including the missed
    2026-10-05 session.
- Results: all 678 PDMO originals re-downloaded and matched their recorded SHA-256 (one needed a retry after a
  transient 404). The CSE chart archive holds 302 shares and 22 indices, 277 of the shares with a 2026-10-05 bar. The
  bond row history covers 62 versions with 0 mismatches. These were handed to the owner as three archives:
  - `pdmo-originals-part1-excel-…` (SHA-256 `49036bce…`)
  - `pdmo-originals-part2-pdf-…` (`3ed06b48…`)
  - `cse-history-and-bond-db-history-…` (`7a01a7c2…`)
  They are not in git.
- Roadmap: instructions for the owner to fix the bond collector's 2027 rollover (this session may not change the old
  repos).

## 2026-10-11 — Phase 0: audit

- Added `docs/audit.md`: a read-only audit of the CSE, Nelson-Siegel and Crypto repositories. It covers data
  collection, stored history and its gaps, every model, duplication, fragility, data-source terms, advice language and
  open questions. No changes were made to the source repositories.
- Added `CLAUDE.md` (handover notes and hard rules), `docs/roadmap.md` and this changelog.
