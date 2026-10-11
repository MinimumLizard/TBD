# Changelog

## 2026-10-11 — Phase 1: architecture proposal, and safety copies of existing data

- Recorded the owner's answers to the audit (`docs/decisions/0001`): the old sites stay personal tools; a source is
  used only if its terms allow commercial use or are silent; data must also live outside GitHub.
- Added `docs/architecture.md` and decision records 0002–0011. They cover: the raw archive on R2 + B2, Supabase,
  collectors on GitHub Actions with dead-man's switches, model plug-ins, the API in server routes, Next.js on Vercel,
  the data-rights policy, compliance by construction, and monitoring. Also costs at 0/500/5,000 users, the migration
  and parity plans, the two extensibility walkthroughs and what not to build yet.
- Added `scripts/` tools, all read-only towards the existing repos and sources' servers:
  - `backup_repos.sh`: complete, verified git bundles of the three repos (every branch);
  - `bond_db_history.py`: rebuilds every row version of the bond database from its 62 committed versions and
    verifies the result against all of them (1,112 overwritten quote values recovered);
  - `archive_pdmo_files.py`: re-downloads every PDMO file the bond database parsed and checks it against the SHA-256
    recorded at the time;
  - `archive_cse_history.py`: saves the CSE's one-year chart history for every share and index, including the missed
    2026-10-05 session.
- Results: all 678 PDMO originals re-downloaded and matched their recorded SHA-256 (one needed a retry after a
  transient 404). The CSE chart archive holds 302 shares and 22 indices, 277 of the shares with a 2026-10-05 bar. The
  bond row history covers 62 versions with 0 mismatches. These were handed to the owner as three archives:
  - `pdmo-originals-part1-excel-…` (SHA-256 `49036bce…`)
  - `pdmo-originals-part2-pdf-…` (`3ed06b48…`)
  - `cse-history-and-bond-db-history-…` (`7a01a7c2…`)
  They are not in git.
- Roadmap: instructions for the owner to fix the bond collector's 2027 rollover (this session may not change the old
  repos).

## 2026-10-11 — Phase 0: audit

- Added `docs/audit.md`: a read-only audit of the CSE, Nelson-Siegel and Crypto repositories. It covers data
  collection, stored history and its gaps, every model, duplication, fragility, data-source terms, advice language and
  open questions. No changes were made to the source repositories.
- Added `CLAUDE.md` (handover notes and hard rules), `docs/roadmap.md` and this changelog.
