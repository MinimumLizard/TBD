# Directors' money flows (cse_flows)

## What it shows

Where directors' money moved, from their disclosed share dealings (`cse_dealings`), per company over the last 30
days, 90 days and year: the value of purchases, the value of disposals, the net, how many different accounts made
purchases and how many made disposals, how many dealings there were, and whether there was a **cluster**. Also, for
every dealing, the kind of account that dealt (a person, a company, a listed company, a fund…) and three flags:
**large** (Rs 10 mn or more), **related party** and **same ownership group** (the account that dealt belongs to the
company's own ownership group). Each account also carries the name of its ownership group.

This describes disclosures. It is not a signal and says nothing about where a share's price will go; the order of
the companies on the site is by the total value dealt in either direction, not by direction.

**Names are shown.** Counting different accounts needs their names; the per-account table (`models.cse_flow_actor`)
is shown on the money-flows page under the same tier and preview as the rest of this model (decision 0021).

## Inputs

- `cse_dealings` 1.0.0: the transactions (`models.cse_dealing`), without re-filed notices, and their accounts as
  filed (`models.cse_dealing_as_filed`).
- The CSE's security list (`cse.security_list`): which accounts are listed companies, and their names.
- The owner's confirmed aliases (`cse.ownership_confirmations`: `config/ownership_aliases.yaml` and the private file,
  the same list `cse_ownership` uses for shareholders): spellings the owner has confirmed are one holder.
- `cse_ownership` 1.0.0: each company's ownership group, by session (`models.cse_ownership_detail`).

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
   keys are identical, or when the owner's aliases list them as one holder (the aliases always win); initials are
   never matched to full names automatically.
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
account; **same ownership group** when the account's group equals the company's group. Groups are `cse_ownership`'s
as at the dealing date (its latest session on or before that date; before its first session, the first): a
company's group is the holder at the top of its chain of largest voting blocks of 20 % or more; a listed account's
group is its company's group; any other account is its own group, so a holding company at the top of a group matches
the companies under it. A company with no shareholder table is its own group. The account's **group name** is its
group's name (the account's own name when it heads no group).

Values are added in the order of the old terminal's file (by dealing date, announcement date, announcement id, then
position in the notice), so the totals agree with it to the last digit.

## Outputs

- `models.cse_flow_company`: per dealing date, window and company (published).
- `models.cse_flow_summary`: per dealing date (published).
- `models.cse_flow_dealing`: per dealing, with the three flags (published).
- `models.cse_flow_actor`: per dealing date, window and account, with the account's name and its group's name (shown
  under the model's tier, decision 0021).

## Limits

- Windows end on the latest dealing date, not on today: after a quiet spell, "the last 30 days" are the 30 days to
  the latest dealing (the old terminal's rule, kept for version 1).
- The old page also flagged the old owner's personal watchlist; that list is personal and is not ported.
- The old page also compared consecutive quarterly top-20 shareholder lists (audit C20); not ported yet.
- Different spellings of one person's name are different accounts unless their keys match or the owner's aliases
  join them. A change to the aliases changes the rows of every date on the next run (as for `cse_ownership`).
- The groups are only as complete as the shareholder lists: a company whose top-20 table could not be checked is its
  own group, so a dealing by its parent is not flagged.

## Parity

Version 1 reproduces the old CSE terminal's money-flow tables (`cse/flows.py` build() at commit e05c6f3), computed on
its `data/dealings/dealings.csv` with its own aliases file and ownership groups: per window, every company row
(purchases, disposals, net, the distinct accounts on each side, the cluster flag) and every account row (its group's
name, sums, number of dealings, net by company), the large, related-party and same-ownership-group flags of every
dealing, the counts and the median lag, exactly, at the old page's date and at earlier dealing dates (the old code run
on the old file cut at each date). Report (counts only): `docs/migration/parity-cse-dealings-flows.json`.
