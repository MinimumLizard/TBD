# 0020 — Two products, two companies: ZinvestIQ is the Sri Lankan markets product

- **Date:** 2026-10-19
- **Status:** Accepted (owner and Janu's decision to split; the choice of which product keeps the name was left to
  the builder and is recorded here with its reasons)

## Decision

1. **Two products, run by two separate companies.**
   - **ZinvestIQ (ZIQ):** Sri Lankan markets only. That means the CSE share market, LKR government bonds and
     treasury bills, the FD comparison and other Sri Lankan retail education. It lives in this repository.
   - **A crypto and global markets terminal:** a separate company, repository, brand, domain and set of accounts.
     Its name is still to be chosen. It does not use the name ZinvestIQ or anything that suggests a link.
2. **ZinvestIQ keeps the name**, for three reasons:
   - **The plan is to approach the CSE.** The point of the split is that the CSE request and any CSE or SEC
     conversation come from a company with no crypto association. The name that approach uses should already be
     clean, and that is the established one.
   - **The work is already done for ZinvestIQ.** Its first checks were made for a Sri Lankan investor-information
     business (decision 0017). It is also already wired into this product: the site name, the account names, and
     the user agent the collectors announce to the CSE and the PDMO.
   - **The other product is new.** It is aimed at a global audience, and its name is best chosen for that market,
     with its own domain and trademark checks. Nothing in it has to be renamed.
3. **Crypto is removed from this repository.** Removed: the Bitstamp collector, the three crypto models, the crypto
   schema (migration 0010), the crypto pages and API routes, the crypto disclaimer, sources and calendar, and the
   research notes.
   - Migration 0010 was only ever applied to development and test databases, never to a production database, so
     deleting the file is safe. A fresh database simply has no migration 0010.
   - The old Crypto terminal (github.com/MinimumLizard/Crypto) also goes with the other product. "Migrate history"
     and `scripts/backup_repos.sh` no longer archive it here. The other project archives its own history.
   - Hard rule 1 still applies to that repository until its owner says otherwise.
4. **Where the crypto code is now.** Commit `ca7e44c` on branch `claude/eloquent-thompson-npmejp` of
   MinimumLizard/TBD is the last commit that still contains it. It holds:
   - the crypto section, which was cross-checked and passed every test;
   - its research notes, including the review of a paid crypto-research subscription and its terms;
   - the platform it runs on.

   The other product starts from that commit. Keep the branch, or merge it, so the commit stays reachable. A tag is
   safer still; one can be added on GitHub (Releases, then a new tag on that commit).

## Consequences

- **Lankan sources only.** ZinvestIQ's data sources are the CSE (permission being requested), the PDMO, the CBSL and
  the DCS. Nothing it publishes mentions crypto.
- **A shared starting platform.** Both products start from the same platform code: the collector framework, the
  model plug-ins, the tier check and the tier-leak tests. That code was written for the owners.
- **Ownership of that code.** Before either company takes outside money or users, the lawyer should set down who
  owns that shared code and how the other company may use it, for example an assignment to one company and a licence
  to the other. This is added to the lawyer's questions (`docs/plan-retail-features.md` §7).
- **Separate operations.** Separate GitHub repositories, cloud accounts, domains, e-mail senders and payment accounts.
  No cross-links between the two sites, and no shared mailing list.
