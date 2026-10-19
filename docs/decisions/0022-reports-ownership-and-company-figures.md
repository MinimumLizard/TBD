# 0022 — Interim reports, ownership and company figures (Phase 3b, part 3a)

- **Date:** 2026-10-19
- **Status:** Proposed (part of Phase 3b's approval)

## Decisions

1. **Report texts are facts, kept whole in the database.** `cse.financial_reports` indexes every report collected
   (with the SHA-256 of its PDF, archived from now on, and of its text); `cse.report_texts` holds each distinct
   text (`pdftotext -layout`), which is also archived under its SHA-256. Models read only the database, so the text
   must be there: about 70 MB for the old terminal's 1,387 reports. The old terminal kept the text and not the PDF;
   its texts are loaded from the archive as they were.
2. **Collection is weekly** (`cse_api:reports`): each company's report list and the newest quarterly report (else
   annual) not yet collected, one request a second per host. Earlier quarters come from the old terminal's history;
   a later version can add a history pass if quarters are missed.
3. **Both models run as at every session**, each time with only the facts known by then (reports uploaded by then;
   share counts, prices and profiles up to then; dividends announced by then). The old terminal computed everything
   as at its latest session; doing the same for every session gives one row per company and session that later
   sessions never change, and equals the old code's output on the day it would have run. Parsing a report does not
   depend on the session, so it is done once per run. Per-report rows (`models.cse_holding`,
   `models.cse_report_figures`) are as at the latest session, as the old CSVs were.
4. **No individual is named on the site.** The shareholder lists, controllers and chains are stored in two
   unpublished tables the website's login cannot read (migration 0013 revokes the grant). The published table names
   a controller or group head only when it is a listed company, or an unlisted company or institution whose name
   reads as one (legal suffix or fund word, and no personal title). The lawyer's list gains item 10.
5. **The owner's confirmations that name individuals live outside the public repository.** The old aliases file
   named two individuals; the repository keeps only the institution entry. A private file (environment variable
   `OWNERSHIP_PRIVATE_FILE`; in GitHub Actions the secret `OWNERSHIP_PRIVATE_YAML`) carries the rest; a run without
   it keeps the last stored version, so the merges are never undone by accident. The reviews job refuses an entry
   about an individual, joint holder, estate or trust in the public files.
6. **Free float is a new, labelled estimate** (the old tool had none): 100 % less the company's own shares, the
   shares of companies it controls, and every block of 10 % or more. It is an upper bound (directors' small holdings
   cannot be told apart).
7. **The parents evidence sheet (C17) is not ported**: it is a document of suggestions quoting annual reports, which
   name people; the confirmed parents it leads to are ported (`config/ownership_parents.yaml`, empty today). The old
   annual-report passages and report lists are archived, not loaded as facts.
8. **Both models are free**: company-level facts the companies published, combined by stated rules.

## Consequences

- A models run reads every report once (about half a minute per model) and then costs about half a second per
  session, so its time grows by about two minutes a year; a later version can compute only new sessions.
- An amended dividend announced after a session can still change that session's trailing dividend yield (the
  dividends come from the corporate-action model's latest view). Recorded as a limit.
