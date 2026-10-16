# Phase 3 and 4 verification report: models, and the free-tier portal

**Status:** built and verified locally and in CI, **awaiting the owner's approval**. Nothing is live: switch-on
needs the owner's accounts (section 6).
**Date:** 2026-10-11.
**Verified against:** Nelson-Siegel `1c33084`, CSE `f263830` (the audited commits), on the history migrated in
Phase 2.
**Machine-readable reports:** `docs/migration/parity-bonds.json` and `docs/migration/parity-cse.json`, produced by
the commands in section 7.

---

## 1. Summary

| Check | Result |
|---|---|
| Six bond models, version 1, against the old tool | **Exact** on every table: 59 bonds, 11,146 quotes, 210 curves, 13,414 residuals, 9,285 bond z-scores, 86,829 pair z-scores, both reversion figures; and, run against the old code on every curve day, 9,150 liquidity profiles, 209 execution gaps, 209 funding rates, 10,975 carry rows. Largest floating-point difference 1.1e-11 (tolerance 1e-9) |
| Two CSE models, version 1, against the old terminal's code | **Exact** on all 5 sessions it kept raw files for: 120 index levels, 5 market summaries, 200 watchlist share-sessions; the CSE's own rounded percentages agree to their rounding |
| Bond curve version 2 (decision 0014: every two-way quote) | Built and current. Fits 92 quotes a day instead of 52.5; on the bonds both versions fit, the curve moves a median 2.7 bp; it sits slightly closer to executed trades (section 3) |
| Model runs | Deterministic: a second run changes nothing and reads identical inputs (same fingerprints). Stable: every current bond model computed with data to 8 October and again with all data agrees on all 230,000 shared rows (§9) |
| Portal | Every page and API route renders on the real migrated history, at 375 px and desktop widths, with no sideways scrolling |
| Tier-leak suite | **35 of 35 pass**: every page, detail page and API route requested as every tier, with the site reading as the restricted `web_reader` role, including explicit `?date=` requests and the exact last day of the free preview. Shown to **fail** (5 failures) when the tier check was deliberately weakened, then restored |
| Tests | Python: 151 tests (`pytest --collect-only`): the 147 in the fast suite pass, and the 4 legacy tests (both migrations and both parity checks, from an empty database) pass. Web: 55 unit tests and the leak suite (35 checks). The fast suite and all web tests also run in GitHub Actions CI |
| Copy lint | 0 banned phrases, now also scanning the models' code and the web app's code |

Nothing in the three old repositories was changed.

## 2. Phase 3: what was built

| Piece | Where | Notes |
|---|---|---|
| Model framework | `data_platform/models/framework.py` | Manifest schema; inputs restricted to what the manifest declares (and only the pinned version of another model), every row read fingerprinted; the writer keeps every changed value in `models.revisions` |
| Registry | `data_platform/models/registry.py` | Checks every manifest (text keys exist, disclaimer exists, every table exists in a migration, one owner per table, no dependency cycles, a tier for every model); dependency order; publishes to `models.registry`; exports the web app's copy |
| Schema | `db/migrations/0004_models.sql`, `0005_bond_legacy_reference.sql` | Runs, registry, revisions, one table per output shape; the old tool's bond list as a fact |
| Bond models | `data_platform/models/bond_*` | Identity (B1), Nelson-Siegel curve and trade check (B3–B5), residual and pair z-scores with reversion figures (B6, B7, B11), liquidity tiers (B8), execution gap (B9), carry, rolldown and duration (B10) |
| CSE models | `data_platform/models/cse_*` | Market summary (C1) and per-share metrics (C2), for every share and session |
| Job and schedule | `data_platform/jobs/models.py`, `.github/workflows/models.yml` | Runs after each collection and nightly; skips until configured |
| Parity harness | `data_platform/migration/parity.py`, `parity_cse.py` | Section 7 |

Every model has a plain-language `METHOD.md` (shown on the site), a manifest, and tests on hand-made cases and on
the real fixture files.

**Versions now running.** Bonds: `bond_identity` 2.0.0 and `bond_ns_curve` 2.0.0 are current (decision 0014); the
four downstream bond models are at 1.1.0 (same method, reading the new curve). Version 1.0.0 of all six keeps
running beside them as the reference series that reproduces the old tool, for the parallel run. CSE: 1.0.0.

## 3. Decision 0014 in numbers (curve version 2 against version 1)

Measured over the 210 days both versions fitted by `python -m data_platform.models.bond_ns_curve.compare 1.0.0
2.0.0`:

| | version 1 | version 2 |
|---|---|---|
| Quotes in the fit per day (mean) | 52.5 | 92.1 |
| Weighted fit error on its own quotes (median) | 9.48 bp | 26.32 bp |
| Weighted fit error on version 1's quotes (median) | 9.48 bp | 9.84 bp |
| Curve move at version 1's bonds | | median 2.7 bp, 95th percentile 7.1 bp |
| Error against executed trades (median) | 21.39 bp | 19.47 bp |
| Trade bias (median) | 16.01 bp | 13.40 bp |

The administered quotes sit far from any curve, which is why the error on its own quotes rises; their 1/spread²
weight keeps them from moving the curve much. On the site they are drawn as hollow points, labelled as carrying
little weight. Version 2 also keeps the 13.00%2029A quote that version 1 loses every day (finding V1).

## 4. Phase 4: what was built

| Piece | Where | Notes |
|---|---|---|
| Pages | `web/app/` | Overview; stock market; all shares (sortable) and each share; government bonds (yield curve, every quoted bond with its residual and trading activity) and each bond; residual z-scores, trades against quotes, carry (paid tiers); a method page per model; About |
| API | `web/app/api/v1/` | Models catalogue; curve, quotes, liquidity, z-scores, execution gap, carry; market summary, shares, one share's history. `403` with no data below the tier |
| The tier check | `web/lib/entitlements.ts` | The only tier decision. Free previews (a delay in days) supported |
| Data access | `web/lib/db.ts`, `web/lib/data/` | Reads only with a grant from the tier check; only the current version; never an unpublished table; never past a preview's date |
| Database guard | `db/migrations/0006_web_access.sql` | `web_reader` (select on model outputs only), row-level security on every table |
| Text | `web/messages/en.json` | Every word on the site; typed keys; `si.json` / `ta.json` ready for translation |
| Freshness | `web/lib/freshness.ts` | Each page states the session its data is for and warns, computed on the server from the trading calendars, when it is behind |
| Design | `web/app/globals.css`, `web/components/` | Tokens for colour, type and spacing; light and dark; mobile first; ECharts |

Accounts are stubbed: every visitor is anonymous and on the free tier (decision 0016).

## 5. Findings

- **P1. The old bond list holds knowledge no file still teaches.** Some series labels and coupons in the old
  database were learned by earlier versions of its parsers. Replaying today's files without that list ties
  hundreds of quotes to different bonds; with it, all 11,146 match. The list is now a migrated fact, pinned by
  checksum (decision 0015).
- **P2. A quote can be matched to a bond whose coupon is unknown by maturity alone.** It does not happen with the
  old bond list, but it does on a fresh start (the fixture tests show it). Recorded in `bond_identity`'s METHOD
  page as a candidate fix for a later version.
- **P3. The "Migrate history" workflow would have failed on switch-on day** (Phase 2 defect, fixed). It cloned the
  old repos at their latest commit but checked the audit's fingerprints, which belong to the audited commits; the
  old repos change daily. It now checks fingerprints at the audited commits, replays history at the latest
  commit, and takes the bond list from the audited database.
- **P4. Model outputs are larger than the facts.** About 120 MB, of which pair z-scores are about 100 MB (both
  versions), growing by about 1,700 pair rows a day (522 for version 1.0.0, 1,172 for 1.1.0; mean per day since
  1 September, measured with `count(*) ... group by obs_date`). Well inside the Supabase Pro plan; retiring the
  reference versions after the parallel run removes about a third.

- **P5. Including every quote in the curve must not mean pricing administered quotes elsewhere.** Reviewing the
  site showed carry 1.1.0 giving the sub-1% restructuring bonds (quoted at an administered 13.00/12.00) a
  meaningless "+436 bp per year of duration". Carry now leaves out quotes wider than 50 bp, the old tool's own
  threshold; the recompute removed 3,484 rows, each kept in `models.revisions`. The free bond table marks such
  quotes as wide. The curve itself is unchanged (decision 0014).

## 6. Switch-on: the complete checklist

This replaces `docs/phase2-verification.md` §5 (updated after the audit in §9). Do the steps in this order.

**A. Accounts and storage**
1. **Supabase:** create an organisation and a **Pro** project `zinvestiq-prod` in **ap-south-1 (Mumbai)**. In Database
   settings, switch on **Enforce SSL**, and download the **SSL certificate** (you need it in step 10). Note the
   project's *session pooler* connection string (port 5432) for GitHub, and its *transaction pooler* string (port
   6543) for the website.
2. **Cloudflare R2:** create a bucket `zinvestiq-raw`. Add a **bucket lock rule on the prefix `raw/`** with retention
   "indefinite" (the archive is kept forever), and a **lifecycle rule on the prefix `exports/`** deleting objects
   after 90 days (database exports). Do not lock the whole bucket. Create an API token with Object Read & Write on
   that bucket only.
3. **Backblaze B2:** create a private bucket `zinvestiq-raw-copy` and an application key limited to it.
4. **Healthchecks.io:** create a project and copy its ping URL (`https://hc-ping.com/<key>`). Create checks with
   the slugs `pdmo-collect`, `cse-api-collect`, `cse-api-announcements`, `cse-api-history` and `models-all`.

**B. Load the history (nothing runs on a schedule yet)**
5. **GitHub → this repo → Settings → Secrets and variables → Actions → Secrets:** add `DATABASE_URL` (the session
   pooler string), `S3_ENDPOINT_URL`, `S3_BUCKET`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`,
   `SECONDARY_S3_ENDPOINT_URL`, `SECONDARY_S3_BUCKET`, `SECONDARY_S3_ACCESS_KEY_ID`,
   `SECONDARY_S3_SECRET_ACCESS_KEY`, `HEALTHCHECKS_BASE_URL` (descriptions in `.env.example`). **Do not add the
   variable in step 7 yet:** until it exists every scheduled job skips itself, so nothing writes to the database
   while the history is being loaded.
6. **Actions → "Migrate history (manual)" → Run workflow.** It takes up to four hours. Check that the three reports
   in the run's artifacts say `"ok": true` and that the last step lists every model with no error.

**C. Switch collection on**
7. **Same settings page → Variables:** add `COLLECTION_ENABLED` = `true`. From the next scheduled time the
   collectors, models, gap check and backups run by themselves.
8. The next morning: Healthchecks shows every check green, and Actions shows the night's runs green, including
   "Backup: database export".

**D. The website**
9. **The website's database login**, once, in the Supabase SQL editor (the password never goes in git):
   `alter role web_reader with login password '<a long random password>';`
10. **Vercel:** create a team on the **Pro** plan (the free plan forbids commercial use). Import this repo with root
    directory `web` and function region **bom1 (Mumbai)**, next to the database. Set these environment variables
    for Production only:
    - `DATABASE_URL`: the *transaction pooler* string (port 6543) with the user changed to
      `web_reader.<project ref>` and that password;
    - `DATABASE_CA_CERT`: the text of the certificate from step 1 (the site refuses to connect to a remote
      database without it);
    - `APP_ENV=production`.
    Never set `ALLOW_TEST_TIERS` there.
11. Open the deployment and check the overview shows the latest session.

**E. Ongoing**
- GitHub pauses scheduled workflows in a public repository after 60 days without a commit. Healthchecks will email
  you if that happens; re-enable them in the Actions tab (or make a commit). This stops once the repo is private.
- Sign-up, log-in and payments come later, when you choose the payment provider (decision 0016).

## 7. How to re-run the verification

```bash
uv sync
TEST_DATABASE_URL=postgresql://postgres@localhost:5432/postgres uv run pytest -m "not legacy"
# parity against the old tool (needs the migrated history in DATABASE_URL and read-only clones of the old repos,
# checked out at the audited commits: git -C <NS clone> checkout 1c33084; git -C <CSE clone> checkout f263830):
uv run python -m data_platform.migration.parity bonds --old-db <NS clone>/data/sgcp.sqlite --old-code <NS clone> \
    --report docs/migration/parity-bonds.json
uv run python -m data_platform.migration.parity cse --old-code <CSE clone> --report docs/migration/parity-cse.json
# or everything from an empty database:
LEGACY_NS_DB=... LEGACY_PDMO_ARCHIVE=... LEGACY_CSE_REPO=... LEGACY_CSE_CHART_ARCHIVE=... LEGACY_NS_CODE=... \
    uv run pytest -m legacy
# the website
cd web && npm ci && npm run typecheck && npm test && npm run build
TEST_DATABASE_URL=postgresql://postgres@localhost:5432/postgres uv run python tests/leak/seed.py   # prints a URL
DATABASE_URL=<printed URL> ALLOW_TEST_TIERS=1 npx next start -p 3100 &
until curl -sf http://127.0.0.1:3100/api/v1/models > /dev/null; do sleep 1; done; npm run test:leak
```

## 8. Not done, deliberately

- **The other CSE models** (corporate actions and total returns, ownership and look-through control, directors'
  dealings and flows, fundamentals, risk estimates). They need facts the platform does not collect yet (report
  PDFs, announcement details) and confirmations the owner keeps in the old repo. They are the next model work,
  in an order for the owner to choose.
- **The old terminal's portfolio lab, live record and trade list:** personal tools, not ported (audit §8).
- **Accounts, payments, Sinhala and Tamil text, deployment:** need the owner's accounts or translators
  (decision 0016).

## 9. Audit of 2026-10-11

After the build, the whole codebase was reviewed again in four independent passes (collectors and migrations;
models and parity; the website's security; compliance and documentation), and every finding was checked against
the code before being fixed. The full suites were re-run afterwards (§1).

**Fixed**

| Area | Problem | Fix |
|---|---|---|
| Switch-on | Scheduled jobs would start as soon as the secrets existed, writing live rows while "Migrate history" ran, so its reconciliation would fail and the append-only tables could not be cleaned | Jobs wait for a `COLLECTION_ENABLED` variable, set after the migration succeeds (§6 step 7) |
| Pair z-scores | Each pair row carried the bonds' median maturity over all history, so every new day rewrote about 280,000 past rows and their revision copies (about 240 MB a day) | Version 1.1.0 uses each bond's maturity on the day and pair membership as known on the day; past rows never change. The reference version no longer fills the revision log |
| Models job | `--as-of` would have deleted every later row; one failing model stopped all later ones | `--as-of` computes in memory and never writes; failures are recorded, unrelated models carry on, the site's version runs first |
| Bond identity v2 | A letter-free label match ignored maturity, so 13.00%2029A could be filed under 2029B on a day 2029B was missing | The match must also agree on maturity and coupon (version 2 only; version 1 keeps the old behaviour for parity) |
| PDMO collector | One dead link stopped every newer file behind it; a failed parse was never retried | Each file is fetched on its own and failures are reported at the end; failed parses are retried |
| CSE collector | A failure part-way through the per-company calls left those companies missing for the session for good | Each company is stored as it succeeds; a later run that day finishes any company still missing |
| Backups | A same-day re-run failed; exports were never read back; "verify" passed with nothing to verify; the export needs a `pg_dump` at least as new as Supabase's Postgres | Re-runs complete the day's export; every copy is read back; verify fails on an empty archive or a missing recent export; the export job installs PostgreSQL 18's client |
| Database | Migrations released their lock before committing (two jobs starting at once could collide); auction views could show a file twice after a parser upgrade; the website's login could read the unpublished statistics | Fixed in code and migration 0007 (which also gives the website's login a 10-second query limit) |
| Website | No connection timeouts or TLS settings; free previews showed a false "behind" warning; bad dates and odd addresses gave errors instead of 400/404; a grant could in principle be written by hand anywhere in the code | Timeouts, a small pool, verified TLS required for any remote database; preview-aware freshness; 400/404s; grants can only come from the tier check |
| Wording | The z-score page ranked bonds and pairs by size, like a screen; residuals were coloured green and red | Listed by maturity, pairs shown for one chosen bond; neutral colours; "entry yield" renamed |
| Copy lint | Missed word forms, hyphenated forms, phrases across line breaks and look-alike characters | All four are caught now, with tests |
| Docs | Switch-on steps incomplete (TLS, pooler, region, R2 lock prefix, the new variable); re-run commands that would not run; method pages that disagreed with the code | Corrected (§6, §7, the METHOD pages) |

**Open, for the owner** (also in `docs/roadmap.md`)

- **The two Plus models can be recomputed from free data.** The z-scores and the trades-against-quotes gap are
  exact functions of the residuals and trade points the free tier shows, so a determined user can rebuild them; the
  5-day preview delay protects nothing. Options: make them free; take the residual history and trade points out of
  the free tier; or accept it and charge for the convenience.
- **Trade data is used by the day it describes**, not the day it was published (a day's trade file arrives a day or
  more after its quotes), so a day's liquidity, execution-gap and carry figures change once when that file arrives.
  The revision record keeps the first values. Storing when each file first became available would make this
  point-in-time; it needs the publication dates, which the old tool kept but the migration did not carry over.
- **Before launch, versions are changed in place** (decision 0015, rule 11). From the first production run, any
  change that alters outputs gets a new version number.
- **Not fixed (low impact, documented):** re-running the CSE migration after the old repo moves on adds duplicate
  catalogue rows (never duplicate facts); a malformed `%` sequence in an address gets a bare 500 from Next.js's own
  router (no data, no detail).

## 10. Refresh of 2026-10-16: the collectors against the live sources, and the site's first look

To show the owner the site with current data, the local copy was brought up to date by the platform's own
collectors, run against the live sources for the first time since the audit (local database and archive only).

**What ran** (`uv run python -m data_platform.jobs.collect <job>`, then `jobs.models`):

| Job | Result |
|---|---|
| `pdmo` | 692 files listed, 15 new, 15 parsed, 0 failed, 0 unreachable; 455 rows |
| `cse_api:history` | 1,204 backfill rows for 2026-10-12 to 2026-10-15 (the sessions since the migration) |
| `cse_api:announcements` | 69 new announcements |
| `cse_api` at 12:30 Sri Lanka time | **Refused, but for the wrong reason** (finding R1) |
| models | All versions ran; bond_rv_zscores 1.1.0 added 5,157 rows and changed 1 |

**R1. The open-market guard did not recognise the CSE's trading status (fixed).** While the market is open the API's
status is "Regular Trading". The guard ported from the old tool refused only statuses containing "OPEN" (and not
"CLOSE"), so it let a mid-session run through. That run stopped only because one share's closing price was still
zero. On another day it could have stored intraday prices as the session's close. The guard now accepts only a
closed market (`parse.is_closed`): any other status, including an unknown one, is refused. The history job now
checks it too, as the old `cse/backfill.py` did. Tests cover both jobs. Scheduled runs start after the close, so this
was a risk for manual or very late runs. **The old CSE tool has the same guard** (`cse/fetch.py` line 123,
`cse/backfill.py` line 66). Its scheduled runs are after the close too; the one-line fix is in `docs/roadmap.md`
for the owner.

**R2. A trade file published a month late changed a month of outputs, as the audit predicted.** The PDMO posted a
trade summary for 2026-09-15 between 10-11 and 10-16. Because trades are used by the day they describe (§9, "Open"),
the 09-15 curve fit changed (16 points) and, through rolling windows, these outputs from 09-15 to 10-09 changed too:

| Model | Rows changed |
|---|---|
| Liquidity | 373 |
| Carry | 810 |
| Execution gap | 15 |
| Funding | 5 |

Every old value is in `models.revisions`
(`select table_name, method_version, min(row_key->>'obs_date'), max(row_key->>'obs_date'), count(*) from
models.revisions where revised_at > ... group by 1, 2`). This is the strongest argument so far for storing when each
file became available and using data as of that date. It is the owner's call (roadmap item 3, with V3).

**The site, as the owner will see it.** Screenshots of every page, on a computer and a phone, as a free and as a Pro
visitor, were reviewed before sharing. Fixed:

- the general disclaimer and data line printed twice on model pages;
- chart legends covering the plot on phones;
- sector indices shown as codes ("BNK") instead of names;
- the movers tables squeezed into thirds of the page;
- a session filled in from the price history (no turnover) listing "highest turnover" alphabetically;
- "Rs 0.00 mn" for small amounts;
- a long badge widening the bond table;
- a method page wider than a phone screen.
