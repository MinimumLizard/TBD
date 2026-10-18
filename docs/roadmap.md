# Roadmap

| Phase | What | Status |
|---|---|---|
| 0 | Audit of the three existing repos (`docs/audit.md`) | Done 2026-10-11; owner answers in decision 0001 |
| — | Safety copies of existing data (bundles, bond row history, PDMO originals, CSE chart history) | Done 2026-10-11; handed to the owner to store (decision 0003) |
| 1 | Architecture proposal: `docs/architecture.md`, `docs/decisions/0002–0011` | Done; approved 2026-10-11 (decision 0012) |
| 2 | Data foundation (raw archive, database, collectors, gap check, backups) and migration of all history | **Built and verified 2026-10-11 (`docs/phase2-verification.md`). Awaiting approval and switch-on (owner's accounts).** |
| 2b | Switch-on: accounts + secrets, run "Migrate history", then 20 trading days in parallel with the old sites | Owner actions in phase2-verification §5 |
| 3 | Model plug-ins, bonds first, each passing parity tests | **Built and verified 2026-10-11 (`docs/phase3-4-verification.md`): all six bond models and the CSE market summary and share metrics, exact parity; bond curve version 2 (decision 0014). Awaiting approval.** |
| 3b | The other CSE models. Proposed order (`docs/plan-retail-features.md` §8): corporate actions and total returns; risk estimates and the portfolio lab, internal only, with 10- and 15-name versions; fundamentals; ownership, dealings and flows | Not started; waiting for the owner's go-ahead on the order |
| 4 | Portal: API, auth, entitlements, web app (free tier first) | **Free-tier portal, API, single tier check and tier-leak suite built 2026-10-11. Accounts stubbed (everyone is free) until Supabase exists. Awaiting approval.** |
| 4b | Accounts, payments, weekly email updates, a feedback feature, Sinhala and Tamil, deployment on Vercel | Needs the owner's accounts and translators |
| C | Crypto section (owner's request, 2026-10-18; decision 0018): Bitstamp prices, three models, two pages, cross-checked | **Built 2026-10-18 as a prototype for the owners' preview. Public only after Bitstamp's Data License Agreement is signed and a lawyer has read it** |
| 5 | Retail education (new, 2026-10-16): FD vs bills and bonds, FD vs the market, a calculator; model portfolios published only in the form the lawyer allows | Proposed in `docs/plan-retail-features.md` |

## Owner actions, in order of priority (updated after the 2026-10-11 audit)

### Done
- **The bond collector's 2027 rollover (audit F1):** fixed in Nelson-Siegel by PR #17 (`12e1d1c`, 2026-10-11), and
  confirmed working: that repo's daily data updates ran every day from 2026-10-11 to 2026-10-16
  (`git log origin/main` of a fresh clone).
- **The name:** ZinvestIQ (decision 0017).

### 0. Ask the CSE for permission to use its data (new, 2026-10-18: a launch blocker)
The CSE's terms, at https://www.cse.lk/disclaimer, forbid commercial use of cse.lk data without the CEO's written
permission (`docs/research/data-sources-2026-10-18.md`). Development and our private preview can continue, but the
site cannot launch with CSE data until permission or a market-data licence is on file. A draft letter is in
`docs/letters/data-permission-requests.md`, with drafts for Bitstamp (crypto prices), the CBSL (FD rates) and the
statistics department (inflation).

### 0b. Crypto: sign Bitstamp's Data License Agreement, and three decisions (new, 2026-10-18)
The crypto section runs on Bitstamp's prices, whose commercial use needs its signed agreement (draft request in
`docs/letters/data-permission-requests.md`; fee unknown). Until then it is a launch blocker. Decisions for you:
- **Tiers** as proposed: prices free, cycles Plus (free a week late), bitcoin's trend bands Pro?
- **The band position (0 to 1):** publish it at all before the lawyer's view? It is labelled descriptively, but
  readers may treat it as a signal (`docs/research/crypto-itc-review.md`, point 4).
- **Which assets:** ten US-dollar pairs plus ETH/BTC (`data_platform/collectors/bitstamp/parse.py`). Add or remove?
The lawyer's review (item 4) should include the crypto pages, given the CBSL's 2023 wording on promotion.

### 1. Look at the site, then approve (or send back) Phases 2, 3 and 4
You asked to see the site before approving. A visual preview (every page, on a computer and a phone, free and paid
views) was published on 2026-10-16 from a local copy with real data; the real site needs the switch-on (item 5).
Reports: `docs/phase2-verification.md`, `docs/phase3-4-verification.md` (§9 is the audit, §10 the 2026-10-16
refresh). Nothing goes live without your approval (hard rule 6).

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
- **The retail features (2026-10-16):** six short decisions in `docs/plan-retail-features.md` §9, including the
  Phase 3b order (proposed: corporate actions and total returns first).

### 4. Legal review before anything is public
A Sri Lankan lawyer to read `compliance/disclaimers.yaml`, the method pages and the site's wording against the SEC's
rules on investment advice; and the CSE's data terms (the licence enquiry is still outstanding: `config/sources.yaml`).
Add the questions in `docs/plan-retail-features.md` §7: model portfolios and rebalancing, the FD comparison,
user discussion, the name, and personal data. The answer decides how much of the portfolio work can be published.

### 5. Switch-on (when approved): `docs/phase3-4-verification.md` §6
Accounts (Supabase Pro, Cloudflare R2, Backblaze B2, Healthchecks.io), secrets, "Migrate history", then the
`COLLECTION_ENABLED` variable, then the website on Vercel Pro. About two hours of your time plus the migration run.

### 6. Trading calendars
`config/calendars/cse.yaml` lists closures only up to August 2026 (inferred from data). Add the CSE's published
holidays for the rest of 2026 and for 2027, or the site will warn "behind the market calendar" on those days.

### Small fix for the old CSE tool (any time)
The CSE says "Regular Trading" while the market is open, and the old tool's guard (`cse/fetch.py` line 123 and
`cse/backfill.py` line 66: "OPEN in status and CLOSE not in status") lets that through. Its scheduled runs start after
the close, so it has not mattered, but a manual run during trading could store intraday prices as the day's close.
The fix is to snapshot only when the status says "Market Closed"; this platform's version is
`data_platform/collectors/cse/parse.py: is_closed`.

### Later
- Buy GitHub Pro and make all four repos private (decision 0012); then add an `OLD_REPOS_TOKEN` secret (read-only)
  so "Migrate history" can still read the old repos.
- Translators for Sinhala and Tamil, who also add Sinhala and Tamil banned-phrase lists to
  `compliance/banned_phrases.yaml`.
- Choose the payment provider (PayHere expected) for Phase 4b.
