# Changelog

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
  - phone-width method pages.

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
