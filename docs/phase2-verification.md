# Phase 2 verification report: data foundation and history migration

**Status:** Phase 2 built and verified locally, **awaiting the owner's approval and the switch-on**.
**Date:** 2026-10-11.
**Verified against:** CSE `f263830`, Nelson-Siegel `1c33084`, Crypto `4dc446a` (code) / `fce882b` (data).
**Machine-readable reports:** `docs/migration/bonds-reconciliation.json`, `cse-reconciliation.json` and
`legacy-archive.json`. They are produced by the commands in section 6; this page summarises them.

---

## 1. Summary

Layers 1–3 of the architecture are built:
- the raw archive;
- the database, with migrations, append-only guards and current views;
- collectors for the PDMO and the CSE, plus the gap check and backups.

**All existing history has been migrated and reconciled exactly**, in a local Postgres 16 standing in for
Supabase and a local folder standing in for Cloudflare R2. Both use the same code paths as production.

| Check | Result |
|---|---|
| Bond facts rebuilt from the 678 PDMO originals vs the old database | **Exact** for trades (3,204), volumes (2,698), auctions (125) and every stored quote (11,146) |
| CSE facts rebuilt from the old raw responses vs the old CSVs | **Exact** for prices (69,312), indices (5,382), market (7) and announcements (203) |
| Audit Appendix A fingerprints, recomputed from the archived bytes | **20 of 20 match** |
| Running every migration a second time | **Adds nothing** (identical row counts in every table) |
| Value conflicts (a re-read disagreeing with stored history) | **0** |
| Missed CSE session 2026-10-05 | **Restored**: 277 prices and 22 indices from the CSE's chart history (turnover cannot be recovered) |
| Gap check over the whole migrated history | **0 open problems**, 6 acknowledged with reasons (section 4) |
| Live smoke test against the real sites | PDMO and CSE collectors ran cleanly; nothing new on a Sunday, as expected |
| Tests | 79 test functions; all pass locally and in GitHub Actions CI (Postgres 16) |

Nothing in the three old repositories was changed. They keep running.

## 2. What was built

| Piece | Where | Notes |
|---|---|---|
| Raw archive | `data_platform/core/rawstore.py` | Named by SHA-256, write-once, verified on read; a local folder and an S3/R2 implementation (tested against an S3 simulator) |
| Database schema | `db/migrations/0001–0003` | `ops`, `bonds`, `cse` schemas. **Fact and raw tables refuse UPDATE and DELETE in the database itself.** A disagreeing re-fetch is recorded in `ops.value_conflicts`, never applied |
| Source register | `config/sources.yaml` | Rights status and evidence per source; a prohibited source cannot be enabled (CI checks) |
| Collector framework | `data_platform/core/collector.py`, `http.py` | Archive before parse, run log, rights gate, Healthchecks.io pings, polite HTTP with firewall-challenge detection |
| PDMO collector | `data_platform/collectors/pdmo/` | The old parsers, ported unchanged. Every row of every file is stored **as published**: nothing filtered, no ISIN guessing at ingest. Index years derived from the date (the 2027 time bomb is gone here) |
| CSE collectors | `data_platform/collectors/cse/` | End of day (every ordinary share, not only a watchlist), announcements, and a weekly history job that fills any missed session |
| Gap check | `data_platform/jobs/gapcheck.py`, `config/calendars/`, `config/datasets.yaml` | Tells a real gap from an unlisted holiday; acknowledged holes carry their reason |
| Backups | `data_platform/jobs/backup.py` | Nightly copy of the archive to a second store; nightly write-once database export to both; monthly sample verification |
| Compliance scaffold | `compliance/`, `data_platform/compliance.py` | One disclaimer registry; copy lint fails the build on advice language, with an allow-list that needs a reason per entry |
| Scheduling | `.github/workflows/` | CI on every push; scheduled collectors, gap check and backups, which **skip themselves until the secrets exist**; one-click "Migrate history" |
| Migration | `data_platform/migration/` | Replays old raw data through the new parsers and reconciles; archives every old file; all repeatable |

### Where the build differs from the architecture text, and why

- **Corrections are new rows plus "current" views**, rather than a `superseded_by` column. Each fact row
  points at the exact archived file it came from. Views pick the winning file per day: the latest posted, so
  amendments win. This keeps every table strictly insert-only, which the database enforces.
- **Collectors expose `collect()` plus pure `parse_*()` functions** rather than four separate methods. The CSE flow
  is a chain of dependent calls (the session date decides what to fetch next). The parse functions are what the
  migration replays, so they are the part that had to be separate.
- **Re-fetches with a blank value are not conflicts.** The CSE repeats the previous session without its change
  figure; a blank means "not provided here", not a disagreement.

## 3. Reconciliation detail

### Bonds (`docs/migration/bonds-reconciliation.json`)

All 678 files the old database had parsed were re-downloaded on 2026-10-11. **Every one matched the SHA-256 the old
pipeline recorded when it first parsed it**, so the PDMO has not altered any published file. All 678 parse with the
ported parsers.

| Table | Old | New current | Missing | Extra | Differ |
|---|---|---|---|---|---|
| Trades | 3,204 | 3,204 | 0 | 0 | 0 |
| Volumes | 2,698 | 2,698 | 0 | 0 | 0 |
| Auctions (results + announcements) | 125 | 125 | 0 | 0 | 0 |
| Quotes | 11,146 stored | 19,507 as published | **0** | 8,361 (explained below) | 0 |

The 8,361 additional quotes are rows the old pipeline did not keep, all accounted for day by day:
- **8,151** were left out deliberately, matching the old parse notes exactly. They are the administered
  restructuring bonds and one-way quotes. They are now kept, flagged by `n_coupon_steps`, and models can decide
  what to use.
- **210** were lost to a defect (finding V1).

### CSE (`docs/migration/cse-reconciliation.json`)

1,330 raw responses from the old repo's five session folders and the one-off backfill were replayed in the order
the old jobs ran.

| Table | Old CSV | New | Missing | Extra (expected) | Differ |
|---|---|---|---|---|---|
| Prices | 69,312 | 69,589 | 0 | 277 (2026-10-05 restored) | 0 |
| Indices | 5,382 | 5,404 | 0 | 22 (2026-10-05 restored) | 0 |
| Market | 7 | 7 | 0 | 0 | 0 |
| Announcements | 203 | 203 | 0 | 0 | 0 |

New tables with no old CSV equivalent: security list (1,636 rows), per-company snapshots (462), company profiles
(302). The old CSV "volume" column is mapped to `volume_regular` for daily rows and `volume_total` for backfill rows,
which is the mix the audit found (addendum item 4); both are now stored under their own names.

### Everything else (`docs/migration/legacy-archive.json`)

Every file at the audited commits is archived individually: CSE 5,139; Nelson-Siegel 60; Crypto code 116; Crypto
data 587. So is each repo's full history as a verified bundle. This covers what the replays don't:
- the CSE models' outputs (corporate actions, dealings, ownership, fundamentals, the portfolio record), which
  Phase 3's parity tests will use as golden files;
- your hand-written confirmations in `config/`;
- the whole crypto history store.

All 20 Appendix A fingerprints recompute exactly from the archived bytes.

## 4. Findings

| # | Finding | Impact | Status |
|---|---|---|---|
| V1 | **The old bond matcher filed 13.00%2029A (matures 2029-01-01) under the ISIN of 13.00%2029B (2029-05-01)** through its "ignore the series letter" fallback. The genuine 2029B quote then overwrote it, so a real, tightly quoted bond was silently missing from every curve on all 210 days. The stored 2029B values were correct. | The old curves lacked one bond. | Both bonds are kept now. Phase 3's identity-resolution model reproduces the old behaviour as version 1 (for parity) and fixes it as version 2. |
| V2 | 8,151 administered and one-way quotes were never stored by the old pipeline. | Information loss, now ended. | Stored as published. |
| V3 | **Three bond-volume files are dated one business day late** by the old "date from the data" rule (2025-12-11, 12-26, 12-30); the PDMO index labels them correctly. Their figures sit under the following day. | Volumes for three days carry the wrong date. | Acknowledged in `config/datasets.yaml`. **Decision for you:** date volumes by the index label when the two disagree? The old pipeline trusted the data because some labels have typos. A fix needs a new parser version and review. |
| V4 | **Two days of bond volumes were never published** (2026-01-05, 2026-05-11): the PDMO's index row links a copy of another day's file. | Unrecoverable from the source. | Acknowledged; worth raising with the PDMO. |
| V5 | **The PDMO has already removed a link**: the duplicate 2026-09-29 trade-summary file the old pipeline fetched is no longer listed. | Evidence that files do disappear. | The file is in the archive. |
| V6 | CSE 2026-10-05 restored: 277 prices and 22 indices from chart history; no turnover. | Gap closed as far as the source allows. | Done. The weekly history job now does this automatically. |
| V7 | 2026-01-26 has no trade-summary file while 2026-01-29 has two (audit §3.2). | One day of trades probably mislabelled at source. | Acknowledged; enquiry with the PDMO. |

## 5. What switch-on needs (owner actions)

Phase 2 is complete as code. To start collecting into the cloud (the 20-trading-day parallel run in
architecture §14), please do these steps in order. About an hour, once.

1. **Supabase:** create an organisation, then a Pro project named `tbd-prod` in region **ap-south-1 (Mumbai)**.
   Copy the *session pooler* connection string.
2. **Cloudflare R2:** create a bucket `tbd-raw`. Add a **bucket lock rule** with no prefix, retention "indefinite".
   Create an API token with Object Read & Write on that bucket only.
3. **Backblaze B2:** create a private bucket `tbd-raw-copy` and an application key limited to it.
4. **Healthchecks.io:** create a project and copy its *ping key* URL (`https://hc-ping.com/<key>`). Create checks
   with these slugs: `pdmo-collect`, `cse-api-collect`, `cse-api-announcements`, `cse-api-history`. (Checks must
   exist before pings register; schedules are in the workflow files.)
5. **GitHub → this repo → Settings → Secrets and variables → Actions**, add: `DATABASE_URL`, `S3_ENDPOINT_URL`,
   `S3_BUCKET`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `SECONDARY_S3_ENDPOINT_URL`, `SECONDARY_S3_BUCKET`,
   `SECONDARY_S3_ACCESS_KEY_ID`, `SECONDARY_S3_SECRET_ACCESS_KEY`, `HEALTHCHECKS_BASE_URL`. The descriptions are in
   `.env.example`.
6. **Actions → "Migrate history" → Run workflow.** Check the three reports in the run's artifacts say `"ok": true`.
7. From then on, the scheduled jobs run by themselves.

Vercel and Resend aren't needed until Phase 4 (the website).

## 6. How to re-run the verification

```bash
uv sync
TEST_DATABASE_URL=postgresql://postgres@localhost:5432/postgres uv run pytest -m "not legacy"   # fast suite
# the full migration against real old data (needs local clones and the safety archives):
LEGACY_NS_DB=... LEGACY_PDMO_ARCHIVE=... LEGACY_CSE_REPO=... LEGACY_CSE_CHART_ARCHIVE=... uv run pytest -m legacy
# or the production path, end to end: the "Migrate history" workflow
```

## 7. Not done in Phase 2, deliberately

- **CSE interim and annual report PDFs (ownership, fundamentals).** The old text extracts and indexes are archived,
  so nothing is lost. A collector that also keeps the PDFs belongs with the models that read them (Phase 3).
- **Crypto collection.** Deferred under the data-rights rule (decision 0009). Its history is archived complete.
- **Bond ISIN resolution, curves and all other models:** Phase 3, bonds first, each passing parity tests against
  the golden outputs now in the archive.
