# Architecture

**Status:** Phase 1 proposal, awaiting the owner's approval. Nothing here is built yet.
**Date:** 2026-10-11. Prices were checked on this date; the links are in section 13.
**Reads with:** `docs/audit.md` (what exists today) and `docs/decisions/` (one short record per decision).

---

## 1. The design in one page

The product is one website. It shows Sri Lankan market information (CSE equities and LKR government bonds first) with
free and paid tiers. Behind it are six layers, each with one job:

```
   Sources (cse.lk, treasury.gov.lk, …)
        │  fetch, politely, on a schedule
        ▼
 ┌──────────────────────────────┐   every response saved untouched, named by its fingerprint,
 │ 1. RAW ARCHIVE  (Cloudflare  │   locked against deletion; copied nightly to Backblaze B2
 │    R2, write-once)           │
 └──────────────┬───────────────┘
                │  parse + validate (the same code can re-run on any old file)
                ▼
 ┌──────────────────────────────┐   clean tables, every row carries source, fetched_at and the raw
 │ 2. DATABASE  (Supabase        │   file it came from; nightly export to R2 and B2
 │    Postgres, Mumbai)          │
 └──────────────┬───────────────┘
        ▲       │
        │  3. COLLECTORS: one Python module per source: fetch → archive → parse → validate → store
        │       │
        │       ▼
        │  4. MODELS: one plug-in folder per model: manifest + compute + tests; outputs stored with method version
        │       │
        │       ▼
 ┌──────────────────────────────┐   checks the visitor's tier against the model's manifest on the
 │ 5. API (server routes inside │   server, before any number leaves; free visitors never receive
 │    the web app)              │   paid numbers
 └──────────────┬───────────────┘
                ▼
 ┌──────────────────────────────┐   one mobile-first site, one design system, English first with
 │ 6. WEB APP (Next.js on       │   Sinhala and Tamil ready, pages generated from the model registry
 │    Vercel)                   │
 └──────────────────────────────┘
```

**Where things run.**
- Collectors and models are Python. They run as scheduled jobs on GitHub Actions in the private monorepo.
- The database and logins are on Supabase. The website and its server routes are on Vercel.
- Raw files are on Cloudflare R2, with a second copy on Backblaze B2.
- Healthchecks.io emails you when a scheduled job doesn't check in, or a day of data is missing.

**What it costs** (section 13): about **US$56–68 a month at 0 or 500 users** and **US$77–161 at 5,000**. That is
before payment-provider fees and any data licences. The platform cost barely moves with users, because the data is
small and pre-computed.

**What changed from your default design, and why** (each change has a decision record):

| Default | Proposal | Reason (from the audit) |
|---|---|---|
| Raw archive in "object storage" | **Cloudflare R2 with bucket locks, plus a nightly copy to Backblaze B2** | Raw files are the irreplaceable asset (F2, F3). Two companies, two copies, and the primary refuses deletes. R2 has no download fees, so re-parsing everything costs nothing. |
| Collectors scheduled "somewhere" | **GitHub Actions, several attempts a day, plus an outside dead-man's switch** | The project already runs on it and it is cheap. Its known weakness (late and occasionally skipped runs, F6) is handled by design: collectors catch up on any missed day, and a missing day raises an alert within hours rather than silently. |
| A separate API service | **The API is the web app's own server routes** | One fewer service to run, deploy and pay for. The tier check sits in one server-side module with tests that try to leak paid data. A database-level guard (row-level security) is the second line. |
| Payments behind an interface | Same, **not built** | As instructed. |
| Crypto as one of the three tools | **Crypto deferred** | Most of its free sources prohibit commercial use (audit §7, decision 0009). It returns when licensed sources are budgeted. |
| CSE portfolio lab as a product feature | **Kept as an internal research tool, not published** | Model portfolios with a live trade record are the closest thing in the codebase to investment advice. It waits for a lawyer's view (decision 0010). |

Everything else follows your default.

---

## 2. Principles that decide the details

1. **Store first, parse second.** Nothing is parsed until its raw bytes are safely archived. Any database table can
   be rebuilt from the archive.
2. **Append, never overwrite.** Corrections become new rows that supersede old ones, with the reason stated. "What did
   we show on 3 March?" always has an answer. (The bond database could not answer that; audit §3.2.)
3. **Every number knows where it came from.** Each row carries `source`, `fetched_at` and `raw_object_id`. Each model
   output carries `model`, `method_version`, the input data versions and the code version.
4. **Fail loudly, never quietly.** A collector that fetches nothing is a failure. A missing trading day is an alert.
5. **Rights are configuration, not memory.** Each source's commercial-use status is recorded with evidence, and a
   source marked "prohibited" cannot run.
6. **Compliance is enforced by the build.** Banned phrases fail CI. Disclaimers come from one registry. Model output
   labels come from a controlled vocabulary.
7. **Boring tools, few of them.** Python for data, TypeScript only for the website, Postgres for state, plain files
   for config.

---

## 3. Repository layout

One private monorepo (this one, `TBD`, renamed when the brand exists). GitHub holds code only, never the only copy
of data.

```
TBD/
  CLAUDE.md                     handover notes (keep current)
  config/
    sources.yaml                every data source: owner, schedule, rights status + evidence, enabled flag
    entitlements.yaml           tiers (Free, Plus, Pro, Professional) and what each includes
    calendars/                  trading-day calendars (CSE, bond market), confirmed holidays
  compliance/
    disclaimers.yaml            the single place for disclaimer text, keyed (e.g. general, model, bonds)
    banned_phrases.yaml         the copy-lint list, with an allow-list for factual uses
    vocabulary.yaml             allowed words for model output labels
  data_platform/                Python package (uv-managed)
    core/                       shared code: http client, archive, db, validation, calendars, logging
    collectors/<source>/        one module per source (layer 3)
    models/<name>/              one plug-in per model (layer 4): manifest.yaml, compute.py, METHOD.md, tests/
    registry.py                 discovers models; publishes the registry to the database
    jobs/                       entry points the scheduler calls (collect, compute, gapcheck, export)
  db/
    migrations/                 numbered SQL migrations (schema history)
  web/                          Next.js app (layers 5 and 6)
    app/                        pages and server routes
    lib/entitlements.ts         the ONLY place a tier decision is made
    messages/{en,si,ta}.json    every piece of user-facing text
  tests/                        cross-cutting tests: tier leak, copy lint, migration reconciliation
  scripts/                      one-off tools (archiving, backups, migration)
  docs/                         architecture, decisions, audit, roadmap, runbooks
  .github/workflows/            CI and the scheduled jobs
  .env.example                  every environment variable, no values
```

---

## 4. Layer 1: raw archive

**What it stores.** Every response a collector receives, byte for byte: JSON, HTML index pages, Excel, PDF. It also
covers the existing history (the old repos' raw folders, the re-downloaded PDMO originals, the bond database's
version history and the crypto snapshots).

**How it's named.** `raw/<source>/<yyyy>/<mm>/<dd>/<sha256>.<ext>`, with the fingerprint (SHA-256) as the file name.
Identical content is stored once, and a file can't be silently replaced: changed bytes mean a different name. A
database table `raw_objects` lists each one: source, URL, request parameters, fetched_at, fingerprint, size, content
type and HTTP status.

**Where.** Cloudflare R2, with a **bucket lock rule** that forbids deleting or overwriting anything under `raw/`.
Nightly, a job copies new objects to **Backblaze B2** (a different company, a different failure). A monthly job
re-reads a random sample from both copies and checks the fingerprints.

**Why not Supabase Storage?** It would work, but it puts both copies of history in one vendor. R2 charges nothing
for downloads, so "re-parse everything" stays free forever. See decision 0003.

## 5. Layer 2: database

**Supabase Postgres, Pro plan, Mumbai region** (`ap-south-1`, the closest region to Colombo). Supabase also provides
logins, row-level security, daily backups (7 days kept on Pro) and a dashboard you can browse like a spreadsheet.

Schemas (Postgres name-spaces), so the purpose of each table is obvious from its name:

| Schema | Holds | Examples |
|---|---|---|
| `ops` | how the platform itself is doing | `raw_objects`, `collector_runs`, `gap_checks`, `source_status` |
| `ref` | slowly changing reference data | `securities` (CSE symbols, ISINs), `bonds`, `calendars`, `sectors` |
| `cse` | CSE market facts | `prices_daily`, `indices_daily`, `market_daily`, `announcements`, `corporate_actions`, `dealings`, `report_texts`, `shareholdings` |
| `bonds` | government securities facts | `quotes_daily`, `volumes_daily`, `trades_daily`, `auctions`, `issuances` |
| `models` | model outputs | one table per output shape, each keyed by `(model, method_version, as_of, …)` |
| `app` | users and access | `profiles`, `subscriptions`, `entitlement_overrides` |

**Rules every fact table follows.**
- Every row has `source`, `fetched_at`, `raw_object_id` and `ingested_at`.
- Rows are never updated in place. A correction inserts a new row, and the old one gets `superseded_by`, `superseded_at`
  and a reason. Views named `*_current` show the latest version, which is what models read.
- Keys follow the audit's lessons: one row per (security, session, source). Backfill and daily rows are kept apart, as
  the CSE does now.
- Where a source has two definitions of one quantity, both are stored under explicit names. For example, CSE
  `volume_regular` (excludes negotiated crossings) and `volume_total` (includes them); the old `prices.csv` mixed the
  two at 2026-10-02 (audit addendum, item 4).

**Backups.**
1. Supabase's daily backups.
2. A nightly `pg_dump` from a scheduled job, written to R2 and B2 as `exports/db/<date>.dump`, kept for 90 days, then
   monthly copies kept forever.
3. A monthly restore test into a scratch database, with row counts compared.

## 6. Layer 3: collectors

One Python module per source, all with the same shape:

```python
class Collector:                       # data_platform/core/collector.py
    source_id: str                     # matches config/sources.yaml
    def plan(self, since: date) -> list[Request]      # what to fetch, including any missed days
    def fetch(self, req: Request) -> RawObject        # network → archive (layer 1); nothing else
    def parse(self, raw: RawObject) -> list[Record]   # bytes → typed records; pure, re-runnable on old files
    def validate(self, records) -> list[Record]       # schema + sanity checks; raises with a clear message
    def store(self, records) -> StoreResult           # append to layer 2; idempotent
```

**What the framework does for every collector, so no collector can forget it:**
- **Politeness:** one shared HTTP client with per-host spacing, retries with backoff, an honest User-Agent and timeouts.
  It also detects firewall challenge pages (the bond project's rule).
- **Archive before parse.** `fetch` writes to R2 and records `raw_objects` before returning.
- **Idempotency.** Re-running a day changes nothing if nothing changed upstream. If the upstream file changed (an
  amended report), a new raw object and superseding rows are stored, never overwritten.
- **Catch-up.** `plan(since)` asks "which expected days are missing?", not "what is today?". A skipped scheduled run is
  repaired by the next one, where the source still serves that day. (CSE turnover for a missed day can't be
  recovered from the source, so the collector runs several times a day to make missing it unlikely.)
- **Run log.** Every run writes `ops.collector_runs`: start, end, status, rows added, raw objects added, message.
- **Switch-off.** A source runs only if `config/sources.yaml` says `enabled: true` **and** its `rights.status` is not
  `prohibited`. Turning a source off is a one-line change.

**Daily gap check.** A job compares each dataset against its calendar. Examples: "every CSE trading day since launch has
prices", "every bond business day has quotes, and trades by T+3". It alerts on any hole. Calendars start as the ones
inferred in the audit and are confirmed by hand when an official list is found.

**Schedules** (GitHub Actions, times in Sri Lanka time):

| Job | When | Notes |
|---|---|---|
| CSE end of day | 16:00, 18:30 and 22:00 weekdays | The first run that sees a new session collects it; later runs are no-ops. |
| CSE announcements and dealings | every 2 hours, 08:00–22:00 weekdays | |
| CSE company reports (PDFs) | daily 06:00 | **Keeps the PDFs**, not only their text (audit §2.4). |
| Bonds (PDMO) | 19:00, 01:30 and 07:30 daily | Year pages are derived from the date, never typed in (the F1 lesson). |
| Models | after collectors succeed, and 23:00 | Only recomputes what has new inputs. |
| Gap check | 09:00 daily | Emails a summary only when something is missing. |
| Exports and backups | 03:00 daily | pg_dump, R2 → B2 copy. |

Each scheduled job pings a Healthchecks.io check when it finishes. If a check is not pinged by its deadline,
Healthchecks emails you. This catches the "GitHub never started the run" failure that cost the CSE its 2026-10-05
session.

## 7. Layer 4: model plug-ins

A model is a folder. Adding one never requires editing the core.

```
data_platform/models/bond_ns_curve/
  manifest.yaml
  compute.py
  METHOD.md          the method in plain language, every formula, every assumption (written before code)
  tests/
    test_compute.py
    golden/          parity files from the old implementation (section 15)
```

**`manifest.yaml`:**

```yaml
name: bond_ns_curve
title_key: models.bond_ns_curve.title        # text lives in web/messages, not here
market: lk_bonds
requires:                                    # datasets read, by name; the scheduler orders runs from these
  - bonds.quotes_daily_current
  - bonds.trades_daily_current
  - ref.bonds
outputs:
  - models.curve_fits
  - models.curve_residuals
minimum_tier: professional                   # one of config/entitlements.yaml tiers
method_version: "1.0.0"                      # bump on any change that alters outputs
disclaimer_key: model_general                # from compliance/disclaimers.yaml
label_vocabulary: [above_curve, below_curve, near_curve]   # checked against compliance/vocabulary.yaml
free_preview: { delay_days: 5 }              # optional: free tier sees a delayed version (illustrative)
```

**`compute.py`** exposes one function: `compute(inputs, as_of) -> Outputs`. It reads only what the manifest declares
(the framework passes it in) and returns tables. It never touches the network or writes anything itself. That is what
makes it testable and reproducible.

**Registry.** `registry.py` discovers every `models/*/manifest.yaml` and validates it: the tier exists, the
disclaimer key exists, labels are in the vocabulary, and required datasets exist. It then publishes the manifests to
`models.registry` in the database, so the website and API read the same truth. A broken manifest fails CI.

**Versioning.** Every output row carries `method_version` and the git commit of the code. A method change bumps the
version and starts a new series; the old series stays. This is the CSE lab's `series` idea, generalised. It answers
"history stays comparable" by never mixing versions in one series. Backfilling a new version over past dates is an
explicit, recorded action, never a side effect.

## 8. Layer 5: API and entitlements

The API is a small set of server routes in the web app (`web/app/api/...`). They query only pre-computed tables;
nothing heavy happens per request.

**Every request that returns data goes through one function:**

```ts
// web/lib/entitlements.ts: the only place a tier decision is made
authorize(user, { model: "bond_ns_curve", as_of }) -> Allowed | Denied(reason) | Allowed(delayed_to)
```

It reads the user's tier (from their subscription row, on the server) and the model's `minimum_tier` and
`free_preview` (from the published registry). If it says no, the route returns no data, not hidden data.

**Second line of defence.** Model output tables have row-level security in Postgres. The browser's database key can
read only rows explicitly marked public. The server's privileged key is never sent to the browser (an environment
variable on Vercel only).

**Tier-leak tests** (run in CI on every change):
- For every model in the registry and every tier, request every route as a user of that tier. Assert that no
  restricted value appears in the response body, the page HTML, or the data embedded for the page.
- Assert the browser bundle contains no privileged keys.
- Assert that statically generated pages contain only free data. Paid pages must render on the server per request.

**Tiers** (`config/entitlements.yaml`): `free < plus < pro < professional`. They are ordered, so "minimum tier" is a
single comparison. Which features sit in which tier is a business decision, so the file starts with a proposal for you
to edit.

**Payments.** A `PaymentProvider` interface (create checkout, handle webhook, cancel) is defined and nothing is
implemented. PayHere is the expected first provider. Until then, tiers are granted by hand
(`app.entitlement_overrides`), for example to test users.

## 9. Layer 6: web app

- **Next.js (App Router, TypeScript) on Vercel Pro.** Vercel's free Hobby plan forbids commercial use.
- **Design system:** a small set of shared components and design tokens: colours, type scale, spacing, number
  formatting, plus one charting library, Apache ECharts (Apache-2.0). Mobile-first: every page is designed at 375 px
  wide first.
- **Text ready for Sinhala and Tamil.** No user-facing string is written in code. All copy lives in
  `web/messages/en.json`, with `si.json` and `ta.json` alongside, using `next-intl`. Number and date formatting is
  per locale. Fonts include Sinhala and Tamil scripts (Noto Sans Sinhala and Noto Sans Tamil, open licence). Launch
  is English only; the structure means translation is adding files, not changing code.
- **Pages generated from the registry.** Each model gets a standard page: title, description, chart or table, method
  link, disclaimer, "data as of" stamp and attribution. All of it comes from the manifest and message files. Bespoke
  pages (market overview, a security's page) compose several models.
- **Freshness is shown, and computed on the server:** each page states the session its data is for, and warns when it
  is behind the calendar.

## 10. Compliance by construction

The rule: information, tools and education only. No buy/sell/hold, no price targets, no picks, no personalised
recommendations. Decision 0010 has the detail; the mechanisms are:

1. **One disclaimer registry** (`compliance/disclaimers.yaml`). Pages and model manifests refer to disclaimers by key.
   CI fails if a model page has no disclaimer.
2. **Copy lint.** A test scans every message file, manifest, template, Markdown method page, and the rendered HTML of
   a sample of pages. It fails on banned phrases: imperatives and evaluations such as "buy", "sell", "hold", "strong
   buy", "accumulate", "get in", "price target", "undervalued", "top picks", "you should", "recommended". Factual
   past-tense uses that the product needs, such as "directors bought Rs 12 mn", are allowed only through an explicit
   allow-list entry with a reason. Adding a phrase to the allow-list therefore needs a deliberate commit you can see.
3. **Controlled vocabulary for model labels.** Model outputs use descriptive words from `compliance/vocabulary.yaml`.
   For example, the bond residual is "above the fitted curve by 7 bp", not "cheap". A pair is "spread 1.9 standard
   deviations above its 60-day average", not "buy A, sell B".
4. **Nothing personalised.** No feature takes the user's holdings or circumstances and returns an action. Watchlists
   (later) only filter what everyone can see.
5. **Methods are public.** Every model page links its METHOD.md, including its limits. That is what makes it
   education rather than a tip.

These reduce risk; they don't replace legal advice. The lawyer questions in the audit (§10, question 5) still stand.

## 11. Environments, CI and secrets

| Environment | Database | Website | Used for |
|---|---|---|---|
| local | the **dev** Supabase project (free; pauses when idle, which is fine) | `npm run dev` on your machine | building and trying things |
| staging | **staging** Supabase project (second project on the Pro organisation, Micro compute) | Vercel preview deployment | every pull request gets a preview link |
| production | **prod** Supabase project (Pro, Mumbai) | Vercel production, your domain | users |

Secrets live only in GitHub Actions secrets, Vercel environment variables and your password manager. The repo has
`.env.example` listing every variable with no values. A secret-scanning check runs in CI.

**CI on every pull request:** Python tests (collectors with recorded real responses, models with golden files),
TypeScript type-check and tests, copy lint, tier-leak tests, registry validation and a migration dry-run. Nothing
merges red.

## 12. Monitoring and alerting

- **Healthchecks.io:** one check per scheduled job; it emails if a job doesn't report in.
- **Gap check:** a daily email only when data is missing or late.
- **Collector failures:** the job fails, GitHub emails, and `ops.collector_runs` shows the message. An internal
  `/status` page (owner only) shows every source's last success and any gaps.
- **Website errors:** Vercel's logs at launch. A dedicated error tracker is in "not yet" (section 18).

---

## 13. Cost estimate (US$ per month, checked 2026-10-11)

| Item | 0 users | 500 users | 5,000 users | Basis |
|---|---|---|---|---|
| Supabase Pro (prod), incl. $10 compute credit | 25 | 25 | 25–75 | $25 base; Micro compute covered. At 5,000, budget a Small ($15) or Medium ($60) instance. Data stays well under 8 GB, users under 100k MAU. |
| Supabase staging project (Micro) | 10 | 10 | 10 | Second project on the same organisation. |
| Vercel Pro (1 developer seat) | 20 | 20 | 20–40 | 1 TB transfer included; 5,000 users of a data site should stay inside it. Margin for function usage. |
| Cloudflare R2 (raw archive + exports) | 0–1 | 0–1 | 1–3 | $0.015/GB-month after 10 GB free; years of raw data are a few GB; downloads free. |
| Backblaze B2 (second copy) | 0 | 0 | 0–1 | $6.95/TB-month after 10 GB free. |
| GitHub (private repo, Actions) | 0–5 | 0–5 | 0–5 | 2,000 free minutes/month on Free; estimated use about 1,500–2,500; extra at $0.006/min. |
| Healthchecks.io | 0–5 | 0–5 | 0–5 | Free tier 20 checks; the $5 Supporter plan if commercial use needs it. |
| Resend (email: login links, alerts) | 0 | 0 | 20 | Free 3,000/month, max 100/day; Pro $20 for 50,000. |
| Domain | ~1–2 | ~1–2 | ~1–2 | Unverified estimate; a `.lk` domain costs more than `.com`. |
| **Total** | **≈ $56–68** | **≈ $56–68** | **≈ $77–161** | |
| Not included | | | | PayHere fees (per transaction, later); legal advice; any CSE/PDMO data licence (unknown, enquiry needed); crypto data when it returns (CoinGecko Analyst $129/month is the cheapest plan with long history and a commercial licence). |

Sources: supabase.com/pricing, vercel.com/pricing, developers.cloudflare.com/r2/pricing,
backblaze.com/cloud-storage/pricing, docs.github.com (Actions billing), healthchecks.io/pricing, resend.com/pricing,
coingecko.com/en/api/pricing.

---

## 14. Migration plan

The old sites keep running, untouched, until you switch.

**Step 0 (now, done in this session):** read-only safety copies.
- Bundles of all three repos (every branch and commit).
- The bond database's full row history, rebuilt from git and verified against all 62 versions.
- The PDMO originals re-downloaded and fingerprint-checked against the bond database's own record.

**Step 1: load history into the new platform (Phase 2).** For each dataset, a migration script reads the old files
at a pinned commit and writes to the new tables. Every migrated row gets `source = migration:<repo>@<commit>`, and its
raw input is archived. Each script is **repeatable**: run it twice and the second run adds nothing. It is
**reconciled**:
- Row counts per table and per day must equal the old data.
- A checksum is computed both sides: SHA-256 over a canonical sort of key and value columns.
- Counts and checksums are compared with the baselines in `docs/audit.md` Appendix A.
- The CSE `prices.csv` keeps both backfill and daily rows, exactly as stored.
- The bond history migrates as its full version history, not just the latest values.
- The missing CSE 2026-10-05 session is filled from the chart endpoint (prices only) and marked as a backfill.

**Step 2: parallel run, at least 20 trading days.** The new collectors run on their own schedule beside the old ones.
A daily comparison job pulls the old repos' latest data (read-only) and compares it with the new tables, key by key.
- Raw facts (prices, quotes, trades, announcements) must match exactly.
- Each difference is classified: (a) old missed it, (b) new missed it, or (c) both have it but values differ. It is
  emailed to you.
- Expected differences, such as rows the old bond ingest dropped on purpose, are listed in advance so they don't
  raise false alarms.

**Step 3: cut-over checklist** (you approve each source separately):
- 20 consecutive trading days with zero unexplained differences.
- The gap check has been clean for 20 days.
- A restore test from backup has passed.
- Every model fed by the source passes parity (section 15).

**Step 4: after cut-over.** The old repos stay as they are, private and archived read-only. Nothing is deleted.
Their workflows can be disabled once you're happy, which is your call.

**Rollback:** until step 4, the old pipelines are untouched and remain the reference. If the new platform has a bad
day, nothing is lost and nothing needs repairing on the old side.

## 15. Parity test plan

**Goal:** prove each ported model reproduces the old one, before anything changes.

**How golden files are made.** For each model, run the **old** code at a pinned commit on a frozen copy of its
historical inputs, and save its outputs as golden files (CSV/Parquet) with the commit and input fingerprints. The new
plug-in runs on the same inputs, now loaded through the new database, and must match within the stated tolerance:
- text, counts and dates: exact;
- floating point: absolute 1e-9 or relative 1e-9, unless a model states otherwise with a reason;
- optimisers: weights within 1e-6.

Port first, improve second. Known flaws found in the audit (for example the bond curve's look-ahead λ) are fixed as
method **version 2** after version 1 passes parity. Version 2 then documents how and why its outputs differ.

| Model | Golden dataset | Tolerance / notes |
|---|---|---|
| **Bonds** (ported first) | | |
| B1 identity resolution | ISIN assignment for every quote row, all 210 days | exact |
| B3 daily NS fit | betas, λ, RMSE, n, per day | 1e-9 |
| B5 trade check | bias and RMSE per day | 1e-9 |
| B6/B7 bond and pair z-scores | every stored row | 1e-9 |
| B8 liquidity tiers | tier per bond per day | exact |
| B9 execution gap | per day | 1e-9 |
| B10 carry, rolldown, duration | core book per day | 1e-9 |
| **CSE** | | |
| C1/C2 market tape and watchlist metrics | Panel A/B values for each stored session | exact / 1e-9 |
| C6 corporate actions | the full `corporate_actions.csv` | exact |
| C7 total returns | TR series for every stock | 1e-9 |
| C13–C17 ownership | `holdings.csv`, `owners.csv`, `companies.csv` | exact (text), 1e-9 (values) |
| C18–C20 dealings and flows | `dealings.csv`, the flows JSON | exact |
| C21–C22 fundamentals | `reports.csv`, `latest.csv` | exact / 1e-9 |
| C8–C11 portfolio lab (internal only) | `data/lab/*.json`, `record/*.csv` | weights 1e-6 |

Models that are **not** ported because they are personal tools (trade list C12, crypto X15) get no parity test; they
are recorded as dropped.

## 16. Walkthrough: adding a new model

Example: **"CSE dividend yield history"**, the trailing 12-month cash dividend divided by price for every stock, daily.

1. Create `data_platform/models/cse_dividend_yield/` by copying `models/_template/`.
2. Write `METHOD.md` first. Inputs: confirmed cash dividends with ex-dates in the trailing 365 days, and the close
   on each session. Output: yield per stock per session. Limits: special dividends included, withholding tax ignored.
3. Fill `manifest.yaml`: requires `cse.corporate_actions_current` and `cse.prices_daily_current`; outputs
   `models.security_daily_metric`; `minimum_tier: plus`; `method_version: "1.0.0"`; `disclaimer_key: model_general`;
   label vocabulary `[yield_pct]`.
4. Write `compute(inputs, as_of)`. It only transforms the tables it's given.
5. Write tests: one hand-checked stock against a real dividend, plus edge cases (no dividend; a split in the window).
6. Add the title and description to `web/messages/en.json`.
7. Open a pull request. CI validates the manifest, runs the tests and the copy lint, and the tier-leak test now covers
   this model automatically. The preview deployment shows the new page, generated from the manifest.
8. Merge. The model scheduler sees the new manifest and computes it after the next CSE collection. A one-off
   `jobs.backfill_model cse_dividend_yield --from 2025-10-07` fills history as version 1.0.0.

**Core files touched: none.**

## 17. Walkthrough: adding a new data source

Example: **CBSL daily exchange rates** (USD/LKR).

1. **Check rights first.** Read the source's terms and record them in `config/sources.yaml`: `rights.status` (allowed /
   silent / prohibited), the evidence URL, a quote and the date checked. If prohibited, stop: the platform won't run it.
2. Create `data_platform/collectors/cbsl_fx/` from the template. Implement `plan`, `fetch` (via the shared client),
   `parse`, `validate`. The framework handles archiving, run logs, retries and idempotency.
3. Save two or three real responses into `tests/fixtures/` and write parser tests against them, including one
   "the page came back empty or changed shape" test that must fail loudly.
4. Add a migration in `db/migrations/` for the new table (`fx.rates_daily`) with the standard columns.
5. Add the source's calendar and schedule to `config/sources.yaml`, plus a Healthchecks check. The gap check picks up
   the new dataset from config.
6. Pull request → CI → merge. The first scheduled run backfills as far as the source allows, archiving every
   response.
7. Turning it off later is `enabled: false`, and history stays.

**Core files touched: none** (one migration file and one config entry, by design).

## 18. What not to build yet, and why

| Not yet | Why |
|---|---|
| Payments (PayHere integration) | As instructed. The interface is defined; grant tiers by hand until there are paying users. |
| Crypto | Most current sources prohibit commercial use (decision 0009). It needs a licensed price/market-cap source (from $129/month) and a rebuild of the features those sources fed. |
| Publishing the CSE portfolio lab (model portfolios, live record) | Closest to regulated advice. It keeps running privately as research until a lawyer says how, or whether, to present it. |
| Personal portfolios, holdings import, alerts on holdings | Personalisation is exactly what the advice rule forbids. Revisit with legal advice. |
| Native mobile apps | A mobile-first website serves phones. Apps add store reviews and two more codebases. |
| Sinhala and Tamil translations themselves | The structure is ready from day one; translation is cheap to add once English copy settles. |
| Real-time or intraday data | Sources are end-of-day, and intraday redistribution almost certainly needs a licence. |
| A separate API service or public API for third parties | Server routes are enough. A public API is a licensing question (we would be redistributing). |
| Error tracker, analytics, A/B testing | Add once there is traffic to observe. Vercel logs suffice at launch. |
| Self-hosted anything | Against your preference, and nothing here needs it. |
| AI-generated commentary | High risk of drifting into advice; needs its own compliance design. |

## 19. What you need to set up (owner actions before Phase 2)

These need your identity, card or legal acceptance, so I can't do them for you:

1. **Make all four repos private**, including this one (`TBD` is public today, and the audit is in it). Note: GitHub
   Pages sites from private repos need a paid plan (GitHub Pro, $4/month). Without it, the three personal sites will go
   offline when made private.
2. **Create accounts**, ideally under a shared business email: Supabase (Pro organisation), Vercel (Pro), Cloudflare
   (R2), Backblaze (B2), Healthchecks.io, Resend. Add your co-founder to each.
3. **Create the API keys** each account needs and put them into GitHub Actions secrets and Vercel. The names are in
   `.env.example`, written in Phase 2.
4. **Decide the region question** (audit §10, Q6): the company's country affects PayHere and privacy law (Sri Lanka's
   Personal Data Protection Act No. 9 of 2022, or Australian privacy law).
5. **Store the safety copies** made in this session (bundles, bond history, PDMO originals) in at least two places
   (decision 0003).
