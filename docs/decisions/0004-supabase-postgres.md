# 0004 — Supabase Postgres (Pro, Mumbai) as the database and login provider

- **Date:** 2026-10-11
- **Status:** Proposed (the owner's default, confirmed)

## Context

The data is small: about 850k rows across all three tools today (audit Appendix A). It needs transactions, history
tables, user accounts and row-level security.

## Decision

- Supabase Pro ($25/month, which includes a $10 compute credit covering one Micro instance) in region `ap-south-1`
  (Mumbai), the closest to Colombo.
- Supabase Auth for logins: email magic link first.
- A second project for staging (+$10/month Micro). A free project for development: it pauses after a week idle,
  which is acceptable for dev.

## Why

- Postgres is the most boring, best-documented database there is.
- Supabase adds auth, row-level security and a browsable dashboard, with no servers to run.
- Pro includes 8 GB of database, 100 GB of storage, 250 GB of egress and 100,000 monthly active users, far above
  need for years.
- Free projects pause after one week of inactivity, so production must be on Pro.

## Backups

- Supabase's daily backups (7 days on Pro).
- A nightly `pg_dump` to R2 and B2 (decision 0003), kept 90 days, then monthly copies forever.
- A monthly restore test.
- Point-in-time recovery ($100/month per 7 days) is not needed yet: the raw archive means any day can be rebuilt.

## Consequences

Vendor lock-in is low. It is plain Postgres; a `pg_dump` moves it anywhere.
