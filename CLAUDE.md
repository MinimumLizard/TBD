# CLAUDE.md — read this first

Handover notes between sessions. Keep this file current: future sessions rely on it.

## What this is

A tiered retail market-information portal, mainly for Sri Lankan investors. It is being built by consolidating
three existing personal tools (CSE equities, LKR government bonds, crypto) into one platform. Working name: TBD
(no brand yet).

Owner background: finance, fluent in R, learning Python, not a professional engineer. Explain decisions in plain
language. Prefer boring, well-documented, managed services over clever or self-hosted ones.

## Current phase

**Phase 1 (architecture proposal) is done; awaiting the owner's approval before Phase 2.** See `docs/roadmap.md`.

- Audit: `docs/audit.md` (findings, fragility register, data rights, questions).
- Owner's answers: `docs/decisions/0001-owner-answers-to-phase-0.md`. Read it before asking the owner anything.
- Architecture: `docs/architecture.md`; one record per decision in `docs/decisions/`.
- Phase 2 is blocked on owner actions (architecture §19): repos private, accounts created (Supabase, Vercel,
  Cloudflare R2, Backblaze B2, Healthchecks.io, Resend), keys in GitHub/Vercel secrets.

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

No product code yet. One-off safety tools (read-only towards the existing repos and sources):

```
bash scripts/backup_repos.sh <out_dir>                                  # verified bundles of all three repos
python scripts/bond_db_history.py --repo <Nelson-Siegel clone> --out <file.sqlite>   # row history + self-check
python scripts/archive_pdmo_files.py --db <sgcp.sqlite> --out <dir>     # PDMO originals, SHA-256 checked
python scripts/archive_cse_history.py --out <dir>                       # CSE one-year chart history
```

Write archives to the scratchpad, never into this repo; data does not belong in git.
