# CSE dividends and other corporate actions (cse_corporate_actions)

## What it shows

For every listed share: its cash dividends, share sub-divisions, scrip dividends and rights issues, with the
ex-date, the amount or ratio, and whether the figure is **confirmed** (read from the CSE's own numeric fields) or
**awaiting confirmation** (read from text, or incomplete, so it is not used until checked by hand).

## Inputs

- Each company's announcement list (`getAnnouncementByCompany`), collected daily for the last 92 days, and the
  CSE's daily list of new announcements.
- For each announcement in a corporate-action category, its detail record: the typed record
  (`getAnnouncementById`: dividend per share, share counts, proportions) or, where the CSE has none, the general
  "(DATES)" record (`getGeneralAnnouncementById`: the ex-rights date, the date trading resumes after a split).
- The CSE's security list (which shares each company has: voting `.N0000`, non-voting `.X0000`) and the number of
  shares issued (company summaries and the trade summary's market capitalisation ÷ close).
- The owner's confirmations, `config/corporate_actions_review.yaml` (stored in the database before each run).

A corporate-action category is one whose name contains DIVIDEND, SUB-DIVISION, SUBDIVISION, SUB DIVISION, RIGHTS,
SCRIP, CAPITALI, CONSOLIDATION or BONUS, and not DEBENTURE.

## Method (version 1.0.0)

Amounts and ratios come only from numeric fields, or from text that states them explicitly. **Nothing is
inferred.**

| Type | Amount or ratio from | Ex-date from | Status |
|---|---|---|---|
| Cash dividend | `votingDivPerShare` / `nonVotingDivPerShare` (one row per share class) | `xd` | confirmed (needs review if there is no XD date) |
| Scrip dividend | `votingPropotion` = existing shares per 1 new share (N); ratio 1 new per N | `xd` | confirmed when there is an XD date and the proportion is a number the share-count check does not contradict, or text of the form "1 for N" that passes the check |
| Sub-division | resulting ÷ existing share counts = F; ratio F − 1 new per 1 | `tradingCommencement` of the "(DATES)" record | confirmed once the dates record exists |
| Rights issue | ratio read from the text ("Three (3) new … for every Fifty (50) …"); price S from `votingShareConsideration` of the latest earlier typed record | `xr` of the "(DATES)" record | **always needs review** |
| Bonus, consolidation, unrecognised records | none | none | needs review, numbers left blank |

- **Share-count factor** F for a scrip of 1 new per N: F = (N + 1) / N. For a sub-division, F = resulting ÷
  existing shares.
- **Share-count check** (scrip): shares issued × N ÷ the latest shares outstanding must lie between 0.85 and 1.05.
  A scrip whose check fails needs review.
- A dividend or scrip announced without dates is listed for review only if no dated record of the same kind exists
  within 120 days either side.
- A ratio such as "1:5" does not say which side is new, so it is never read.
- **Superseded:** when a split's dates arrive after its ratio, the complete row (its id includes the dates record)
  replaces the earlier incomplete one.
- **One event per share, type and ex-date:** a repeated or amended announcement replaces the earlier one (the later
  announcement id counts); the earlier row is shown as *replaced*.
- **Confirmations:** `confirm` accepts a row awaiting confirmation, optionally correcting its fields; `reject` drops
  a row. A confirmed row must have an ex-date (YYYY-MM-DD) and its figures (a dividend's amount; a split's or scrip's
  factor, or its ratio, from which F = (held + new) / held; a rights issue's ratio and price), or the run stops and
  says which field is missing.

Each row's `use_status` says what became of it: `used` (in the total returns), `awaiting_confirmation`, `rejected`,
`superseded` or `replaced`. Figures are stored as the old terminal stored them: rounded to 8 decimal places.

## Limits

- Only what the CSE publishes in structured form: a corporate action announced only in a PDF is not found.
- Rights issues always wait for a person: the ratio is text.
- The scrip share-count check uses the latest share count, so a later share issue could turn an old scrip's check,
  and with it its status. This is the old terminal's rule, kept for version 1.
- The detail record of an announcement is read once; a later correction by the CSE arrives as a new announcement.

## Parity

Version 1 reproduces the old CSE terminal's `data/history/corporate_actions.csv` at the audited commit (f263830:
392 rows) and at the latest commit checked (e05c6f3: 395 rows): every row and every column, as text. The old file
is append-only and keeps the first version of each row, so 21 rights-issue notes written by an earlier version of
the old code lack the clause "; terms in announcement N" that the old code itself now writes; on those, the model
matches the old code (run on the same files: every row, every column). The actions in use and the rows awaiting
confirmation equal the old `effective()` and `pending_review()`, also under an illustrative set of confirmations.
Reports: `docs/migration/parity-cse-corporate-actions.json` (f263830) and
`docs/migration/parity-cse-corporate-actions-e05c6f3.json`; the facts' reconciliation with the old caches:
`docs/migration/cse-corporate-actions-reconciliation.json`.
