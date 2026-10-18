# CLAUDE.md — read this first

Handover notes between sessions. Keep this file current: future sessions rely on it.

## What this is

A tiered retail market-information portal, mainly for Sri Lankan investors. It is being built by consolidating
three existing personal tools (CSE equities, LKR government bonds, crypto) into one platform. The product is
**ZinvestIQ** (decision 0017); the repository is still called TBD. The owner works with a partner, Janu.

Owner background: finance, fluent in R, learning Python, not a professional engineer. Explain decisions in plain
language. Prefer boring, well-documented, managed services over clever or self-hosted ones.

## Current phase

**Phases 2, 3 and 4 (free tier) are built and verified locally and in CI; awaiting the owner's approval and
switch-on.** See `docs/phase3-4-verification.md` (parity results, findings P1–P5, the complete switch-on checklist §6,
the 2026-10-11 audit §9),
`docs/phase2-verification.md` (data foundation, findings V1–V7, switch-on §5) and `docs/roadmap.md` (owner's open
decisions).

- Audit: `docs/audit.md`. Architecture: `docs/architecture.md`. Decisions: `docs/decisions/` (0001, 0012 and 0014
  are the owner's own answers; read them before asking the owner anything).
- Switch-on needs the owner's accounts and secrets. Until then every scheduled workflow skips itself. The repo is
  PUBLIC for now (decision 0012): never commit data or secrets; CI enforces both.
- The owner will approve after seeing the site; a screenshot preview was shared on 2026-10-16 (report §10).
- Retail features requested 2026-10-16 (weekly emails, feedback, FD comparison, rebalancing signals, fewer-name
  portfolios): `docs/plan-retail-features.md`. Model portfolios and rebalancing are NOT to be published before a
  lawyer's view (decision 0010 point 6, hard rule 4); build them as internal research only.
- Next: Phase 3b (proposed order: corporate actions and total returns; risk estimates and the portfolio lab with 10/15-name
  versions, internal; fundamentals; ownership and dealings), Phase 4b (accounts, payments, emails, feedback,
  Sinhala/Tamil, Vercel), Phase 5 (retail education). Each waits for the owner's go-ahead.

## Architecture in brief

Raw archive (Cloudflare R2, write-once, copied to Backblaze B2) → Supabase Postgres (Mumbai) → Python collectors
(one per source; fetch → archive → parse → validate → store; run on GitHub Actions with Healthchecks.io dead-man's
switches and a daily gap check) → model plug-ins (`data_platform/models/<name>/` with manifest, compute, METHOD.md,
tests; outputs carry `method_version`) → API as Next.js server routes (`web/lib/entitlements.ts` is the only tier
check) → Next.js web app on Vercel, all copy in `web/messages/{en,si,ta}.json`.

Data-source rule (owner, decision 0009): use a source only if its terms allow commercial use or are silent. Status
lives in `config/sources.yaml`. Crypto is deferred: most of its free sources prohibit commercial use.

This session may NOT change the existing repos; push access to them was refused by the environment. Give the owner
instructions instead.

## Source repositories (read-only until a migration plan is approved)

| Tool | Repo | Live site |
|---|---|---|
| CSE terminal | github.com/MinimumLizard/CSE (`main`) | minimumlizard.github.io/CSE/ |
| Bonds (Nelson-Siegel) | github.com/MinimumLizard/Nelson-Siegel (`main`) | minimumlizard.github.io/Nelson-Siegel/ |
| Crypto terminal | github.com/MinimumLizard/Crypto (code: `claude/minilizard-crypto-terminal-e6g100`; data: `data`) | minimumlizard.github.io/Crypto/ |

They are public, so they can be cloned without credentials:
`GIT_LFS_SKIP_SMUDGE=1 git clone https://github.com/MinimumLizard/<repo>`. Clone into a scratch folder, never inside
this repo.

## Hard rules (from the owner's brief; do not relax without written approval)

1. **Do not modify, move or delete anything in the existing repos or their data** until the owner approves a migration
   plan. The current sites must keep running and collecting throughout.
2. **Never lose or rewrite historical data.** Every migration is verified by row counts and checksums against the
   source, and must be repeatable. (Baselines: `docs/audit.md` Appendix A.)
3. **No secrets in the repo.** Use environment variables and `.env.example`.
4. **Information, tools and education only.** No buy/sell/hold language, no price targets, no "picks", no personalised
   recommendations anywhere: code, copy or model output labels. Sri Lanka's SEC penalises unlicensed investment advice.
   One place for disclaimers; a copy-lint check fails the build on banned phrases.
5. **Paid data never reaches an unentitled browser.** Tier checks happen on the server, not by hiding things in the
   front end.
6. **Stop at the end of each phase and wait for approval.**
7. When unsure, or when a choice is costly to reverse, ask the owner first.

## Conventions

- Small commits on feature branches, with plain-language messages.
- Tests for every collector and model. Nothing merges with failing tests.
- Update `docs/roadmap.md` and `CHANGELOG.md` at the end of every session.
- Numbers in docs are measured by a command, not typed in; cite the command.

## Commands

```
uv sync                                                        # once (Python 3.12+)
TEST_DATABASE_URL=postgresql://postgres@localhost:5432/postgres uv run pytest -m "not legacy"   # what CI runs
uv run python -m data_platform.compliance                      # copy lint
uv run python -m data_platform.jobs.migrate                    # apply db/migrations (DATABASE_URL)
uv run python -m data_platform.jobs.collect pdmo               # or cse_api | cse_api:announcements | cse_api:history | cbsl | dcs_cpi
uv run python -m data_platform.jobs.gapcheck                   # missing days, unconfirmed closures
uv run python -m data_platform.jobs.backup replicate|export|verify
uv run python -m data_platform.jobs.feedback summary|list|mark|delete   # visitors' feedback (owner only)
uv run python -m data_platform.migration.bonds|cse|legacy|cse_corporate_actions ...  # history migration + reconciliation
uv run python -m data_platform.jobs.models [--market lk_bonds|cse|lk_savings] [--model NAME]   # compute models (--as-of D: in memory only)
uv run python -m data_platform.models.registry check|order|publish|export-web       # manifests; web copy
uv run python -m data_platform.migration.parity bonds|cse|cse_corporate_actions ...   # parity with the old tools
cd web && npm ci && npm run typecheck && npm test && npm run build                 # website
TEST_DATABASE_URL=... uv run python web/tests/leak/seed.py   # then: DATABASE_URL=<printed> ALLOW_TEST_TIERS=1 npx next start -p 3100; wait for it; npm run test:leak
```

Local Postgres in a cloud session: the container has Postgres 16; start it as the `postgres` user
(`initdb` + `pg_ctl` on port 54321, data under /var/tmp), never as root. Settings come from env vars (`.env.example`).

Layout: `data_platform/core` (archive, db, http, collector runner), `collectors/<source>/` (pure `parse*` functions
plus a `Collector`), `models/<name>/` (manifest.yaml, compute.py, METHOD.md, tests/; `_lib/` is shared code),
`migration/` (incl. parity), `jobs/`; `db/migrations/NNNN_*.sql` (never edit an applied one; add a new file; every
new table must enable row-level security, a test checks); `config/` (sources, calendars, datasets, entitlements =
the tier proposal); `compliance/` (disclaimers, banned phrases); `web/` (Next.js; `lib/entitlements.ts` is the only
tier check, `lib/db.ts` the only database access, all text in `messages/`; after changing a manifest, METHOD.md,
disclaimer, calendar or tier, run `registry export-web`).

Model rules: version 1 of a ported model reproduces the old tool exactly (parity report under docs/migration/);
improvements are a new version beside it. Until the first production run, fixes go into the current version; after
it, any output-changing change is a new version (decision 0015 rule 11). Outputs must be point-in-time where
possible: a row for day D should not change when later days arrive (test this, as bond_rv_zscores does). Scheduled
jobs need the repo variable COLLECTION_ENABLED=true (set by the owner after "Migrate history"). The copy lint also scans model and web code, so avoid banned words even in
identifiers and comments (e.g. JavaScript's `.trim()`; use a regex).

One-off safety tools (read-only towards the existing repos and sources):

```
bash scripts/backup_repos.sh <out_dir>                                  # verified bundles of all three repos
python scripts/bond_db_history.py --repo <Nelson-Siegel clone> --out <file.sqlite>   # row history + self-check
python scripts/archive_pdmo_files.py --db <sgcp.sqlite> --out <dir>     # PDMO originals, SHA-256 checked
python scripts/archive_cse_history.py --out <dir>                       # CSE one-year chart history
```

Write archives to the scratchpad, never into this repo; data does not belong in git.
