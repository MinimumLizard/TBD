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

## Owner actions, in order of urgency

### 1. Before 1 January 2027: stop the bond collector going silent (audit F1)

This session isn't permitted to change your existing repositories, so this is a change for you to make. It takes
about two minutes in GitHub's web editor.

Open `pipeline/config.py` in **Nelson-Siegel**, click the pencil icon, and replace the four `*_INDEX_URLS = {…}`
blocks (the ones listing `2025:` and `2026:`) with:

```python
import datetime as _dt

# One index page per year, from 2025 to the current year. Derived from today's date, so a new year is
# picked up automatically: typing the years in would silently stop collection every 1 January.
_YEARS = range(2025, _dt.date.today().year + 1)
PDMO_INDEX_URLS = {y: f"{PDMO_BASE}/web/report-daily-report/section/{y}" for y in _YEARS}
TRADE_SUMMARY_INDEX_URLS = {y: f"{PDMO_BASE}/web/reports-secondary-market-trade-summary/section/{y}" for y in _YEARS}
BOND_AUCTION_INDEX_URLS = {y: f"{PDMO_BASE}/web/result-treasury-bonds/section/{y}" for y in _YEARS}
BOND_ISSUANCE_INDEX_URLS = {y: f"{PDMO_BASE}/web/treasury-bonds-issuances/section/{y}" for y in _YEARS}
```

Leave `PDMO_EXTRA_INDEX_URLS` as it is (only the diagnostics tool uses it). Commit to `main`. Then, in the Actions tab,
run **Daily PDMO update** once by hand and check that it is green.

Why this is safe in January: the pipeline already treats one empty index page as survivable. Early in January the
2027 page will be empty, log a warning and the run carries on. `section/2027` already exists today and answers with
a normal page. If the PDMO changes the address pattern for 2027, the run log will show it.

Alternative: leave the old repo alone, and the new bond collector must be live in parallel by mid-December.

### 2. Store the safety copies in two places (decision 0003)

### 3. Switch-on: create the accounts and add the secrets, then run "Migrate history"

Steps: `docs/phase2-verification.md` §5, then the website steps in `docs/phase3-4-verification.md` §6.

### 4. Decisions on Phases 3 and 4 (docs/phase3-4-verification.md)

- Bond volumes dating (finding V3): date the 3 disputed volume files by the PDMO index label instead of the data?
- Tiers: is the proposal in `config/entitlements.yaml` right (free: market summary, shares, bond list, curve, bond
  activity; Plus: z-scores with a 5-day-delayed free preview, trades against quotes; Pro: carry)?
- The carry page uses the old tool's "bill + 5 bp" funding assumption. Keep it (stated on the page), or change it?
- The pair reversion statistics are computed but shown to nobody until a legal view. Agree?
- Which of the remaining CSE models first (Phase 3b)?
- A product name, when you have one (the site says "TBD" in one place: `web/messages/en.json`, `site.name`).

### Later: buy GitHub Pro and make all four repos private (decision 0012)
