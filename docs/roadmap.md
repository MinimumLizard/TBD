# Roadmap

| Phase | What | Status |
|---|---|---|
| 0 | Audit of the three existing repos (`docs/audit.md`) | **Done 2026-10-11. Awaiting approval.** |
| 1 | Architecture proposal: `docs/architecture.md`, `docs/decisions/`, costs at 0/500/5,000 users, migration and parity plans, extensibility walkthroughs | Not started |
| 2 | Data foundation (raw archive, database, collectors) and migration of all history, run in parallel with the old sites | Not started |
| 3 | Model plug-ins, bonds first, each passing parity tests | Not started |
| 4 | Portal: API, auth, entitlements, web app (free tier first) | Not started |

## Time-sensitive items found in Phase 0

These need a decision from the owner whatever happens with Phase 1 (`docs/audit.md` §10, questions 1–3):

- **Before 1 Jan 2027:** the bond collector's hard-coded 2025/2026 index URLs (F1).
- **Before ~Oct 2027, ideally now:** backfill CSE session 2026-10-05 prices (F4).
- **As soon as possible:** start keeping raw PDMO files and crypto snapshot responses (F2, F3).
