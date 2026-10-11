# 0013 — Phase 2 implementation choices

- **Date:** 2026-10-11
- **Status:** Proposed (part of the Phase 2 approval)

## Decisions

1. **Facts are stored as published.** Collectors keep every row of every source file. Interpretation (e.g. matching
   a bond quote's series label to an ISIN, deciding which quotes are "administered") is a versioned model, not an
   ingest step. *Why:* the old pipeline's ingest-time matching silently lost a real bond every day (finding V1) and
   discarded 8,151 quotes.
2. **Corrections are new rows; views choose.** Every fact row points at the archived file it came from and the parser
   version that read it. `*_current` views pick the winning file per day (latest posted, so amendments win; then
   newest parser). The database refuses UPDATE and DELETE on fact and raw tables. *Why:* "never rewrite history"
   becomes a property of the database, not a convention.
3. **Disagreements are recorded, not applied.** A re-fetch that disagrees with a stored fact under the same key goes
   to `ops.value_conflicts`. A blank incoming value is not a disagreement.
4. **Gap repair is automatic where the source allows.** The CSE history job fills any session the daily job missed
   (prices only). Gaps the source cannot fill are reported by the gap check every day until acknowledged with a
   reason.
5. **Migration is replay, not copy.** Where the old repos kept raw data, it is replayed through the new parsers and
   reconciled with the old tables, so the migration and the new collectors are proven together.
6. **Collectors on GitHub Actions skip themselves until configured**, so the schedules can sit in the repo safely
   before the accounts exist.

## Consequences

- The bond quotes table has about 75% more rows than the old one; models filter explicitly.
- The parity tests in Phase 3 compare numbers produced from the same facts, with the old behaviour reproduced as
  each model's version 1.
