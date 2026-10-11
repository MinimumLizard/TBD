# Roadmap

| Phase | What | Status |
|---|---|---|
| 0 | Audit of the three existing repos (`docs/audit.md`) | Done 2026-10-11; owner answers in decision 0001 |
| — | Safety copies of existing data (bundles, bond row history, PDMO originals, CSE chart history) | Done 2026-10-11; handed to the owner to store (decision 0003) |
| 1 | Architecture proposal: `docs/architecture.md`, `docs/decisions/0002–0011` | **Done 2026-10-11. Awaiting approval.** |
| 2 | Data foundation (raw archive, database, collectors, gap check) and migration of all history, run in parallel with the old sites | Blocked on the owner's accounts (architecture §19) and approval |
| 3 | Model plug-ins, bonds first, each passing parity tests | Not started |
| 4 | Portal: API, auth, entitlements, web app (free tier first) | Not started |

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

### 3. Make all four repos private (TBD included), then create the accounts in architecture §19
