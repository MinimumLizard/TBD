# 0018 — Corporate actions and total returns (Phase 3b, part 1)

- **Date:** 2026-10-18
- **Status:** Proposed (part of Phase 3b's approval)

## Decisions

1. **The announcement records are facts, kept as served.** `cse.company_announcements` holds each company's list;
   `cse.announcement_details` holds each detail response (one row per announcement, endpoint and distinct response,
   with its SHA-256 and the typed fields exactly as the CSE sent them, as JSON). Reading those fields into dividends,
   ratios and ex-dates is the model's job, so a rule change never needs a re-collection.
2. **The owner's confirmations stay a file in the repository, in the old format**
   (`config/corporate_actions_review.yaml`). Models read only the database, so the models job stores each new
   version of the file in `cse.corporate_action_reviews` (append-only) before it runs, and the model reads the
   latest. A changed confirmation therefore changes the outputs on the next run, every version stays on record,
   and each run's input fingerprint names the version it used.
3. **Collection:** a daily sweep of every company's list over the last 92 days, plus each new corporate-action
   detail once (typed record first, then the general one), as the old tool's one-off collection did. The 2-hourly
   announcements job also keeps its detail responses as facts.
4. **Version 1 reproduces the old CSV and the old code.** The old `corporate_actions.csv` is append-only and keeps
   the first version of each row. 21 rights-issue notes in it were written by an earlier version of the old code;
   the model writes what the old code at the audited commit writes, and parity counts those notes as explained
   only when they differ by exactly that later clause. Numbers are rounded to 8 decimals, as the old CSV stored them,
   so the total returns built from them match the old ones exactly.
5. **Two output tables:** every row with what became of it (`use_status`), and the actions in use with the owner's
   corrections applied. The site lists confirmed actions from the second and those awaiting confirmation from the
   first.
6. **Total returns per traded session**, as the old index; the 1-week, 1-month and 3-month total returns use the
   same windows as the share metrics, so the share page can show them side by side.
7. **An `--as-of` look at the past** sees announcements dated on or before that day, prices up to it, and the
   confirmations stored by then.
8. **Both models are free** (`config/entitlements.yaml`): they are facts the CSE published, combined by a stated
   formula.

## Consequences

- The scrip share-count check uses the latest share count (the old rule), so a later share issue could change an old
  scrip's status and with it past total returns. Recorded as a limit; a later version could use the count as of the
  ex-date.
- Confirming rights issues is a manual task for the owner; until then their total returns leave the rights out.
