# Directors' money flows (cse_flows)

## What it shows

Where directors' money moved, from their disclosed share dealings (`cse_dealings`), per company over the last 30
days, 90 days and year: the value of purchases, the value of disposals, the net, how many different accounts made
purchases and how many made disposals, how many dealings there were, and whether there was a **cluster**. Also, for
every dealing, the kind of account that dealt (a person, a company, a listed company, a fund…) and two flags:
**large** (Rs 10 mn or more) and **related party**.

This describes disclosures. It is not a signal and says nothing about where a share's price will go; the order of
the companies on the site is by the total value dealt in either direction, not by direction.

**Names are not published.** Counting different accounts needs their names; the per-account table
(`models.cse_flow_actor`) is served to nobody until the owner's lawyer has reviewed what may be shown.

## Inputs

- `cse_dealings` 1.0.0: the transactions (`models.cse_dealing`), without re-filed notices, and their accounts as
  filed (`models.cse_dealing_as_filed`).
- The CSE's security list (`cse.security_list`): which accounts are listed companies, and their names.

## Method (version 1.0.0)

**The account that dealt** (the "actor") is the notice's account: the director for an own-account dealing, the
related party for a related-account one. If that name is generic ("Shareholders", "N/A", "Nil", "None", "-",
"Please refer…", "See…", "As per…", "As mentioned…", "Attached", "Related party/parties"), the director is used; if
that is generic too, "<company> – directors (see notice)".

The name is then cleaned, as the old terminal's ownership tracker cleans shareholder names:

1. Leading phrases are removed: "Purchase/Disposal/Sale/Acquisition of shares by X", "Directors of X", "Nominee
   Directors of X", "Shares held by X", "On behalf of X" become X; "… are directors of X" becomes X.
2. Descriptions after the name are removed: ". Mr …", " in which …", " where …", " which is …", ", a private
   company …", ", privately held …", ", major/substantial/controlling shareholder …", and suffixes such as
   "- Directors", "- Common Directors", "- Directors / Shareholders", "(Directors …)". A relative keeps their own
   name: "Mrs X (Spouse)" is not Mrs X.
3. Custodian and financed accounts name their owner: "<custodian> S/A <owner>", "<bank> A/C <fund>",
   "<lender>/<owner>" become the owner.
4. Matching key: upper case, without titles (Mr, Mrs, Dr, M/S…), punctuation, "The", account numbers ("A/C No. 2")
   and legal suffixes (PLC, Ltd, (Pvt) Ltd, Private Limited…). Two spellings are the same account only when their
   keys are identical; initials are never matched to full names.
5. Kind of account, first match: a life or policyholders' fund is an institution; a key equal to a listed
   company's (from the security list in force on the dealing date) is that listed company (shown under the CSE's
   name for it); "Estate of…" / "Late…" an estate; a trust (not a trust fund, not a company) a trust; funds, pension
   and provident funds, insurers, development banks, state bodies an institution; a name with a company word (Ltd,
   PLC, Holdings, Investments, Bank…) a company; "X and Y" or "X/Y" a joint account; a person's name an individual;
   anything else a company.

**Per dealing date D** (every date on which a counted dealing is dated), and per window W of 30, 90 and 365 days,
the dealings counted are the purchases and disposals dated after D − W days and on or before D. (Dealings dated
later never change the rows for D; a late notice dated D or earlier, or a re-filing, does.)

- Per company: purchases = the sum of purchase values; disposals = the sum of disposal values (a missing value counts
  as 0); net = purchases − disposals; accounts purchasing / disposing = the number of different accounts (by key) on
  each side; dealings = the number of transactions. **Cluster**: two or more different accounts made purchases and
  net > 0.
- Per account (not published): the same sums over the account's dealings in all companies, the number of
  dealings, and its net value in its six largest companies.
- Per date: the number of dealings dated on or before D (any side), how many of them are purchases or disposals, and
  the median disclosure lag in weekdays.

Per dealing: **large** when the value is Rs 10 mn or more; **related party** when the dealing was through a related
account. Values are added in the order of the old terminal's file (by dealing date, announcement date, announcement
id, then position in the notice), so the totals agree with it to the last digit.

## Outputs

- `models.cse_flow_company`: per dealing date, window and company (published).
- `models.cse_flow_summary`: per dealing date (published).
- `models.cse_flow_dealing`: per dealing (published).
- `models.cse_flow_actor`: per dealing date, window and account, with the account's name (not published).

## Limits

- Windows end on the latest dealing date, not on today: after a quiet spell, "the last 30 days" are the 30 days to
  the latest dealing (the old terminal's rule, kept for version 1).
- The old terminal also matched accounts with the owner's hand-made list of spellings and grouped listed companies
  by who controls them, and it flagged a listed company dealing in its own group's shares ("own group") and the
  owner's personal watchlist. The platform has no ownership facts yet, so version 1 has no list of spellings, no
  groups and neither flag. On the old data the list of spellings changed no number, which the parity test checks.
- The old page also compared consecutive quarterly top-20 shareholder lists (audit C20). That needs the shareholder
  lists, which the platform does not collect yet; it is left out here.
- Different spellings of one person's name are different accounts unless their keys match.

## Parity

Version 1 reproduces the old CSE terminal's money-flow tables (`cse/flows.py` build() at commit e05c6f3), computed on
its `data/dealings/dealings.csv`: per window, every company row (purchases, disposals, net, the distinct accounts on
each side, the cluster flag) and every account row (sums, number of dealings, net by company), the large and
related-party flags of every dealing, the counts and the median lag, exactly, at the old page's date and at earlier
dealing dates (the old code run on the old file cut at each date). The old code is run without its list of
spellings and groups, and the test checks that the list of spellings changes nothing. Report (counts only):
`docs/migration/parity-cse-dealings-flows.json`.
