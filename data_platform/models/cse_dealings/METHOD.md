# Directors' share dealings (cse_dealings)

## What it shows

Every share dealing that a listed company's director disclosed to the Colombo Stock Exchange, one row per
transaction: the company, the director's role, whether the dealing was in the director's own account or a related
party's, the transaction date, whether it was a **purchase**, a **disposal** or **other**, the number of shares, the
price, the value, the date the CSE published the notice, and the lag between the two.

These are disclosures of what happened. They say nothing about what a share's price will do, and a dealing can have
many reasons (personal finances, taxes, estates, share schemes).

**Names are shown as filed.** The notices name the director and the related account (a relative or a company). The
site shows them, with a link to the CSE's notice, as the companies filed them (the owner's decision of 2026-10-19,
decision 0021; the lawyer's review before anything is public covers it). They are kept in their own table
(`models.cse_dealing_as_filed`), so the facts table stays free of free text.

## Inputs

- The CSE's structured dealing notices: the detail record (`getAnnouncementById`) of announcements in the
  categories "DEALINGS BY DIRECTORS" and "RELEVANT INTEREST …", whose type (`dType`) is `DealingsByDirectors`.
  Each record gives the director, the nature of the directorship, own or related account and the related account's
  name, and per transaction its type (free text), date, quantity and price.
- The details are collected by the daily corporate-action sweep (each company's announcement list over the last 92
  days, and the detail of every dealing or corporate-action announcement in it) and by the 2-hourly announcements
  job. The old terminal's notices were loaded by `python -m data_platform.migration.cse_dealings`.
- When the CSE has served a notice more than once with different content, the latest response counts.

## Method (version 1.0.0)

For each notice, one row per transaction, in the notice's order (`transaction_id` = announcement id : position).

- **Dates.** Read as "02 Jun 2025", "2 June 2025", "2025-06-02", "02/06/2025", "02-06-2025" or "02.06.2025".
  The announcement date is the record's `dateOfAnnouncement`, or its `dateOfNotification` when that is missing.
  `deal_date` is the transaction date, or the announcement date when the notice gives none.
- **Value** = quantity × price (rupees). Commas in numbers are ignored; a missing quantity or price leaves the value
  empty.
- **Lag** = the number of weekdays after the transaction date up to and including the announcement date (public
  holidays are not removed). Negative if the notice is dated before the transaction.
- **Side**, from the free-text transaction type, case ignored:
  1. `other` if it mentions a gift, transfer, inheritance, bequest, transmission or donation;
  2. `purchase` if it matches a purchase word and no disposal word. Purchase words: "purchase" and misspellings
     such as "puchase" or "purchse", "acquisition" (also "aquisition", "acquistion"), "buy…", "bought",
     "subscri…", an allotment of rights or a rights-issue allotment or subscription;
  3. `disposal` if it matches a disposal word and no purchase word: "sale", "sell…", "sold", "dispos…";
  4. `other` otherwise (neither, or both). An `other` row is never counted as a purchase or a disposal.
- **Account**: `related` when the notice ticks the relevant-interest account, else `own`.
- **Re-filed notices count once.** A later notice (by announcement date, then id) for the same company, director
  and account (names compared without case) that repeats every transaction of an earlier one (the same side,
  quantity and price, counted with repeats) with at least one transaction also on the same date, replaces it: the
  earlier notice's rows stay in the table with `superseded_by` set to the later notice, and are not counted
  anywhere. Identical lines inside one notice are separate transactions.
- **Role** (new in this platform, so the published table needs no free text, which sometimes names people). The
  "nature of directorship" text is first made uniform ("Non - Executive", "Non Executive" and "Non- Executive" all
  become "non-executive"; "Board of Directors" is ignored), then the first rule that matches gives the role:
  1. `several`: the text speaks of more than one director: "directors" or "executives" in the plural, two or more
     titles (Mr, Mrs, Ms, Miss, Dr), "respectively", "same directors", both an executive and a non-executive role,
     or two chair roles;
  2. `chair`: chairman, chairperson or chair;
  3. `chief_executive`: managing director, chief executive or CEO;
  4. `independent_non_executive`: "independent" (not "non-independent"), with no executive role;
  5. `non_executive`: non-executive;
  6. `executive`: executive (also misspelt "exaecutive"), finance director, director - finance;
  7. `not_stated`: anything else ("Please refer attachment", "Director", empty).

Numbers are stored as the old terminal's CSV stored them: whole numbers exactly, others rounded to 8 decimal places.

An `--as-of` look at the past sees only the notices announced on or before that day; a re-filing announced later
does not yet replace anything.

## Outputs

- `models.cse_dealing`: the facts above, without names or free text.
- `models.cse_dealing_as_filed` (shown beside each dealing): per transaction, the director, the role and the account exactly as
  filed, the transaction type as filed, and the link to the notice's PDF.

## Limits

- Only notices the CSE publishes as structured records are read; a dealing disclosed only in a PDF is not found.
- The side and the role are read from free text by fixed rules. An unusual wording becomes `other` or
  `not_stated`, never a guess.
- A notice covering several directors or accounts at once is one director and one account in the CSE's record; its
  role is `several`.
- The record has no share class, so a dealing is shown for the company (both its voting and non-voting shares).
- The lag counts weekdays, not market days.

## Parity

Version 1 reproduces the old CSE terminal's `data/dealings/dealings.csv` at commit e05c6f3: every row, every column,
as text, with the side labels mapped (the old file's two trading verbs to `purchase` and `disposal`). The old file
left out re-filed notices; their rows are here, marked `superseded_by`, and the rows not superseded equal the file.
Report (counts only): `docs/migration/parity-cse-dealings-flows.json`. The facts' reconciliation with the old files:
`docs/migration/cse-dealings-reconciliation.json`.
