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
| Model runs | Deterministic: a second run changes nothing and reads identical inputs (same fingerprints) |
| Portal | Every page and API route renders on the real migrated history, at 375 px and desktop widths, with no sideways scrolling |
| Tier-leak suite | **33 of 33 pass**: every page and route requested as every tier, with the site reading as the restricted `web_reader` role. Shown to **fail** (5 failures) when the tier check was deliberately weakened, then restored |
| Tests | Python: 138 tests (`pytest --collect-only`): the 134 in the fast suite pass, and the 4 legacy tests (both migrations and both parity checks, from an empty database) pass. Web: 50 unit tests and the leak suite. The fast suite and all web tests also run, green, in GitHub Actions CI |
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
- **P4. Model outputs are larger than the facts.** About 120 MB, 73 MB of it pair z-scores (both versions), growing
  by roughly 1,000 pair rows a day. Well inside the Supabase Pro plan; retiring the reference versions after the
  parallel run halves it.

- **P5. Including every quote in the curve must not mean pricing administered quotes elsewhere.** Reviewing the
  site showed carry 1.1.0 giving the sub-1% restructuring bonds (quoted at an administered 13.00/12.00) a
  meaningless "+436 bp per year of duration". Carry now leaves out quotes wider than 50 bp, the old tool's own
  threshold; the recompute removed 3,484 rows, each kept in `models.revisions`. The free bond table marks such
  quotes as wide. The curve itself is unchanged (decision 0014).

## 6. Switch-on: what is added to the Phase 2 checklist

The Phase 2 steps (`docs/phase2-verification.md` §5) still come first. Then:

1. **Healthchecks.io:** add a check with slug `models-all`.
2. After "Migrate history" succeeds it computes every model (a new last step). Check the run's log shows each
   model with `+` rows and no error.
3. **The website's database login**, once, in the Supabase SQL editor (the password never goes in git):
   `alter role web_reader with login password '<a long random password>';`
4. **Vercel:** create a team on the **Pro** plan (the free plan forbids commercial use), import this repo with root
   directory `web`, and set two environment variables: `DATABASE_URL` (the session pooler string with the user
   changed to `web_reader.<project ref>`, as Supabase's pooler names users, and that password) and `APP_ENV=production`. Never set `ALLOW_TEST_TIERS` there.
5. Open the deployment and check the overview shows yesterday's session.

Sign-up, log-in and payments come after that, when you choose the payment provider (decision 0016).

## 7. How to re-run the verification

```bash
uv sync
TEST_DATABASE_URL=postgresql://postgres@localhost:5432/postgres uv run pytest -m "not legacy"
# parity against the old tool (needs the migrated history in DATABASE_URL and read-only clones of the old repos):
uv run python -m data_platform.migration.parity bonds --old-db <NS clone>/data/sgcp.sqlite --old-code <NS clone> \
    --report docs/migration/parity-bonds.json
uv run python -m data_platform.migration.parity cse --old-code <CSE clone> --report docs/migration/parity-cse.json
# or everything from an empty database:
LEGACY_NS_DB=... LEGACY_PDMO_ARCHIVE=... LEGACY_CSE_REPO=... LEGACY_CSE_CHART_ARCHIVE=... LEGACY_NS_CODE=... \
    uv run pytest -m legacy
# the website
cd web && npm ci && npm run typecheck && npm test && npm run build
uv run python tests/leak/seed.py        # prints the DATABASE_URL to start the server with
DATABASE_URL=<printed> ALLOW_TEST_TIERS=1 npx next start -p 3100 &  npm run test:leak
```

## 8. Not done, deliberately

- **The other CSE models** (corporate actions and total returns, ownership and look-through control, directors'
  dealings and flows, fundamentals, risk estimates). They need facts the platform does not collect yet (report
  PDFs, announcement details) and confirmations the owner keeps in the old repo. They are the next model work,
  in an order for the owner to choose.
- **The old terminal's portfolio lab, live record and trade list:** personal tools, not ported (audit §8).
- **Accounts, payments, Sinhala and Tamil text, deployment:** need the owner's accounts or translators
  (decision 0016).
