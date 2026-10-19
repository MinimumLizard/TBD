# 0021 — Directors' dealings show names

- **Date:** 2026-10-19
- **Status:** Accepted (owner's decision)

## Decision

1. **Names are shown.** The directors' dealings pages show each director's name and the related account's name as the
   company filed them with the CSE, with a link to the CSE's own notice. The money-flows page lists the accounts that
   dealt, by name.

   The owner's reason: the visibility of who dealt is the point of the disclosures. Nothing is public yet, and the
   lawyer will be consulted soon.
2. **What changed in code:**
   - Migration 0015 lets the website's database role read `models.cse_dealing_as_filed` and `models.cse_flow_actor`.
   - Both are removed from `unpublished_outputs`.
   - The tier-leak tests now require the names to appear exactly where each model's tier allows. The dealings, and
     their names, are free. The account names follow the money flows' tier: Plus, with the free tier one week late.
3. **Agreed at the same time:**
   - Dealings are free, and money flows are Plus with a one-week free preview.
   - The 30/90/365-day windows end on the latest dealing date, as in the old tool. The page states that date.

## Before anything is public

Two questions remain with the lawyer (`docs/plan-retail-features.md` §7, item 9):

- Can names be published under the Personal Data Protection Act?
- Could a "cluster" mark, or a list ordered by the value dealt, be read as advice?

If the answer on names is no, revoking the grant in a new migration and restoring the two `unpublished_outputs` entries
hides them again everywhere, including the API.
