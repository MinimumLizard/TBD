# Roadmap

| Phase | What | Status |
|---|---|---|
| 0 | Audit of the three existing repos (`docs/audit.md`) | Done 2026-10-11; owner answers in decision 0001 |
| — | Safety copies of existing data (bundles, bond row history, PDMO originals, CSE chart history) | Done 2026-10-11; handed to the owner to store (decision 0003) |
| 1 | Architecture proposal: `docs/architecture.md`, `docs/decisions/0002–0011` | Done; approved 2026-10-11 (decision 0012) |
| 2 | Data foundation (raw archive, database, collectors, gap check, backups) and migration of all history | **Built and verified 2026-10-11 (`docs/phase2-verification.md`). Awaiting approval and switch-on (owner's accounts).** |
| 2b | Switch-on: accounts + secrets, run "Migrate history", then 20 trading days in parallel with the old sites | Owner actions in phase2-verification §5 |
| 3 | Model plug-ins, bonds first, each passing parity tests | **Built and verified 2026-10-11 (`docs/phase3-4-verification.md`): all six bond models and the CSE market summary and share metrics, exact parity; bond curve version 2 (decision 0014). Awaiting approval.** |
| 3b | The other CSE models: corporate actions and total returns, ownership, dealings and flows, fundamentals, risk estimates | Not started; needs new collectors and the owner's order of priority |
| 4 | Portal: API, auth, entitlements, web app (free tier first) | **Free-tier portal, API, single tier check and tier-leak suite built 2026-10-11. Accounts stubbed (everyone is free) until Supabase exists. Awaiting approval.** |
| 4b | Accounts, payments, Sinhala and Tamil, deployment on Vercel | Needs the owner's accounts and translators |

## Owner actions, in order of priority (updated after the 2026-10-11 audit)

### Done
- **The bond collector's 2027 rollover (audit F1):** fixed in Nelson-Siegel by PR #17 (`12e1d1c`, 2026-10-11). Check
  once that the next "Daily PDMO update" run in that repo is green.

### 1. Approve (or send back) Phases 2, 3 and 4
Reports: `docs/phase2-verification.md`, `docs/phase3-4-verification.md` (§9 is the audit). Nothing goes live
without your approval (hard rule 6).

### 2. Store the safety copies in two places (decision 0003)
The three archives handed over on 2026-10-11 exist only where you saved them. Put them in two separate places
(e.g. an external drive and a cloud drive you control) before anything else changes.

### 3. Decisions that shape the product (each is a short answer)
- **Tiers** (`config/entitlements.yaml`). Note the audit finding: the Plus models (z-scores, trades against quotes)
  can be recomputed exactly from the free data. Make them free, take residual history and trade points out of the
  free tier, or accept it.
- **Carry's funding assumption** ("12-month bill + 5 bp", your old desk figure). Keep it (stated on the page) or
  change it?
- **Reversion statistics** stay hidden from everyone until a legal view. Agree?
- **Bond volume dating (finding V3):** date the 3 disputed volume files by the PDMO index label instead of the data?
- **Which remaining CSE model first** (Phase 3b): corporate actions and total returns, ownership, directors'
  dealings, fundamentals, risk estimates.
- **A product name**, when you have one (`web/messages/en.json`, `site.name`).

### 4. Legal review before anything is public
A Sri Lankan lawyer to read `compliance/disclaimers.yaml`, the method pages and the site's wording against the SEC's
rules on investment advice; and the CSE's data terms (the licence enquiry is still outstanding: `config/sources.yaml`).

### 5. Switch-on (when approved): `docs/phase3-4-verification.md` §6
Accounts (Supabase Pro, Cloudflare R2, Backblaze B2, Healthchecks.io), secrets, "Migrate history", then the
`COLLECTION_ENABLED` variable, then the website on Vercel Pro. About two hours of your time plus the migration run.

### 6. Trading calendars
`config/calendars/cse.yaml` lists closures only up to August 2026 (inferred from data). Add the CSE's published
holidays for the rest of 2026 and for 2027, or the site will warn "behind the market calendar" on those days.

### Later
- Buy GitHub Pro and make all four repos private (decision 0012); then add an `OLD_REPOS_TOKEN` secret (read-only)
  so "Migrate history" can still read the old repos.
- Translators for Sinhala and Tamil, who also add Sinhala and Tamil banned-phrase lists to
  `compliance/banned_phrases.yaml`.
- Choose the payment provider (PayHere expected) for Phase 4b.
