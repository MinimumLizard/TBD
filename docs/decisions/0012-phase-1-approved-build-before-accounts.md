# 0012 — Phase 1 approved; build Phase 2 before the accounts exist; repos stay public for now

- **Date:** 2026-10-11
- **Status:** Accepted (owner)

## Owner's words

> "Lets do it on public for now, I'll buy the github membership and make things priavte later"
> "Do i need to create the accounts now? Can't you move ahead with the build first"

## Decisions

1. **The Phase 1 architecture is approved**, and Phase 2 starts.
2. **Phase 2 is built and tested without the cloud accounts.**
   - Every cloud piece sits behind an interface with a local stand-in that behaves the same way:
     - the raw archive has a local-folder store, plus an S3/R2 store tested against an S3 simulator;
     - the database is a local Postgres 16; Supabase is Postgres, and the same SQL migrations run on both.
   - Scheduled workflows are written but skip themselves until their secrets exist.
   - The accounts are needed only for the switch-on step: the 20-trading-day parallel run.
3. **This repository stays public until the owner buys GitHub Pro.** Consequences, enforced in code review and CI:
   - **No data in git**: `.gitignore` blocks databases, archives and bundles; CI fails on large files.
   - **No secrets in git**: CI runs a secret scan.
   - Test fixtures are small, real, public source responses only (the same kind the old public repos already commit).
   - The code itself is visible to anyone. The product's value is the accumulated history and the brand, not the
     code, so this is an accepted, temporary risk.

## Consequence for the old sites

They keep running and collecting, untouched, so delaying the accounts loses no data. The only data risk that cannot
wait is the bond collector's 1 January 2027 rollover. It is the owner's two-minute fix (`docs/roadmap.md`), or the
new bond collector must be switched on by mid-December.
