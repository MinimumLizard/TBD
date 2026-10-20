# Who owns the CSE's listed companies (cse_ownership)

## What it shows

For every listed company, from the list of its twenty largest shareholders that it must print in every interim
report (CSE Listing Rules): how much of the voting shares those holders have between them, split by **type of
owner** (listed companies, unlisted companies, funds and the state, individuals, joint holders, estates, trusts,
unidentified nominee accounts, the company itself); whether one **block** of holders controls the company (more
than 50 % of the voting shares) or has influence over it (20 % to 50 %); the **ownership group** it belongs to; and
an estimate of its **free float**; and the **list itself**: rank, holder, shares, % of the class's issued shares and
type of owner, as the latest report prints it, with each holder named as resolved (step 3).

**Names are shown, individuals included**, on the owner's decision of 2026-10-19 (decision 0021, the same basis as
directors' names). The shareholder lists are in the companies' public reports; the lawyer's answer under Sri Lanka's
Personal Data Protection Act is needed before anything is public (`docs/plan-retail-features.md` §7 item 10). The
owner's confirmations that two spellings are one person stay out of the public repository (a private file).

## Inputs

- The latest interim report of each company (`cse.financial_reports`, `cse.report_texts`): collected weekly from the
  CSE's per-company report list, the newest quarterly report (or, for a company with none, the newest annual
  report), its PDF archived and converted to text with `pdftotext -layout`. The old terminal's 1,387 report texts
  (every quarter since June 2025) are loaded by the history migration.
- The CSE's security list (company names, to recognise listed holders), and the shares issued and market value of
  each share class: the company summaries, and the trade summary's market capitalisation, whose ratio to the close
  is the CSE's own share count.
- The owner's confirmations (`cse.ownership_confirmations`, stored before each run): spellings of one holder that
  the rules do not merge (`config/ownership_aliases.yaml`), and owners of unlisted holders, each with its source and
  quote (`config/ownership_parents.yaml`). Entries about private individuals are kept in a private file outside the
  public repository (environment variable `OWNERSHIP_PRIVATE_FILE`).

## Method (version 1.0.0)

Version 1 reproduces the old terminal's ownership tracker (MinimumLizard/CSE `cse/ownership/`) exactly.

**1. Finding the table.** A heading such as "Twenty largest shareholders", "Top 25 shareholders", "List of
shareholders as at …" starts a table; headings about debentures, directors, key management, related parties,
preference shares, distributions, categories or the public holding are skipped. "Non-voting" in the heading (or a
sub-heading just after a table) marks the non-voting class. A row is an optional rank, a name, the share count and
its percentage (a prior-period pair after them is ignored). Names wrapped over several lines, sub-numbered rows,
one holder's accounts followed by their total, footnote marks and digits split by the PDF are handled. A row whose
current cell is "-", "N/A" or "Nil" is dropped. The table ends at its total line, the next heading or section, or
when ranks restart at 1.

**2. Checking the table.** A table is used only if it has at least 5 rows, its percentages sum to at most 100.5,
and its numbers agree with each other. Each of the ten largest rows implies a class total T = shares × 100 / %;
because the printed % is rounded to *d* decimals, each row gives an interval
[shares × 100 / (% + 10⁻ᵈ), shares × 100 / (% − 10⁻ᵈ)]. The intervals must overlap (0.5 % slack); one row that
disagrees with all the others is set aside as a typo. The implied total is the geometric middle of the overlap.
- `verified`: the implied total is within 10 % of the CSE's share count for that class;
- `verified_total`: otherwise, the overlap contains the report's own printed class total (shares were issued or
  cancelled since the report date);
- anything else is `unverified` and is not used. When the table prints a subtotal, the rows must add up to it.

A table whose heading names the wrong class is moved to the other class when its total matches that class's count.
Each row's **fraction** f = shares / T₀, where T₀ is the report's printed class total if the overlap contains it,
else the CSE's count if the overlap contains it, else the implied total.

**3. Who the holder is.** Names are compared after removing case, punctuation, titles, "The", account designations
("A/C No. 2") and legal suffixes. Custodian and trustee accounts ("<bank> S/A <owner>", "BNYM SA/NV-<owner>",
"<…> as trustee for <fund>") and margin accounts ("<lender>/<owner>") are credited to the owner. Insurers' life and
policyholder funds are funds in their own right. Each owner gets a type: `listed` (its name is a listed company's),
`estate`, `trust`, `institution` (funds, pension and provident funds, the Treasury and state bodies), `company`,
`joint`, `individual` or `nominee`. Two people are never merged automatically: only the owner's confirmed aliases
merge spellings.

**4. Control.** Using each company's latest report and its usable voting table, votes are added up by **block**: a
holder's own accounts, plus the votes of every listed company it controls, plus (when the owner confirmed it) an
unlisted holder's votes with its owner's. The largest block, leaving out nominees and the company's own shares, makes
the company `controlled` when it is above 50 % and `influence` when it is 20 % to 50 %. Because a block can include
companies that are themselves controlled, this is repeated until nothing changes.

**5. Look-through value** (stored, not shown). With W[c′, c] the fraction of company c owned by listed company c′
(whose own register is covered) and D[o, c] the fraction owned by every other owner o, each owner's ultimate
fraction through chains of listed holding companies is F = D (I − W)⁻¹, and its value F × market capitalisation.

**6. Ownership group.** Start from a company and follow its largest voting block upward while that block is at
least 20 % and its owner is not a fund, the state or a nominee; when the owner is a listed company, continue from it;
stop at an unlisted owner, at a company with no such block, or at a loop. Companies that end at the same owner form
one group (a group is wider than control: a 43 % owner runs a company in practice). On the site a group is named
after its head; its identifier is the head's code when the head is a listed company, else its first company's code
(`G:<code>`).

**7. Free float (an estimate, new in this platform).** Of the voting shares:

free float % = 100 − (the company's own shares) − (shares of companies it controls) − Σ (blocks of 10 % or more)

where a block is counted as in step 4. The CSE's public-holding rule also leaves out directors' and their families'
smaller holdings, which a top-20 list does not identify, so this is an upper bound.

**8. Shares by owner type.** The voting table's percentages added up by owner type (the company's own shares
separately).

**9. One row per session.** All of the above is computed as at every session for which the CSE published a trade
summary, using only what was known then: the security list, share counts and market values up to that session,
and the reports uploaded by then whose period is not after it. A session's row therefore never changes when later
sessions arrive. It can change only when a fact dated on or before it arrives late (a report collected after its
upload date), or when the owner corrects a confirmation; every such change is kept in `models.revisions`.

## Outputs

- `models.cse_company_ownership`: per company and session, the report used and its period, the table check,
  `top20_pct`, `pct_<owner type>`, `pct_own_shares`, the controlling block's type, name, % and level, `group_id`, the
  group head's type and name, `group_size`, `free_float_pct`, market capitalisation and the report's PDF.
- `models.cse_ownership_detail`: the old companies list, with the controller and the chain of holders.
- `models.cse_holding`: every parsed row of every report, as checked at the latest session (the share page shows the
  latest report's rows whose table passed the checks).

## Limits

- Only the published top 20 (sometimes 25 or 30) holders are visible; owners of unlisted holders only when the owner
  confirmed them.
- Holdings are as at each report's period end, usually the last quarter end; prices and share counts are the
  session's.
- Scanned reports without a text layer (`no_text`), reports without a recognisable table (`no_table`) and tables
  that fail the checks (`unverified`) get no figures; nothing is estimated for them.
- Statutory caps on voting rights (for example under the Banking Act) are not applied.
- Each run recomputes every session from the start: about half a second per session, plus about half a minute to
  read every report once.

## Parity

`docs/migration/parity-cse-ownership-fundamentals.json`: the old code, run on the old repo's own files cut off at
each of its sessions, against this model's build for the same session (holdings, companies, owners, groups), the
model's output tables at the latest session, and the CSVs the old repo stored.
