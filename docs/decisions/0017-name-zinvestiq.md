# 0017 — The product is called ZinvestIQ

- **Date:** 2026-10-16
- **Status:** Accepted (owner and Janu's decision)

## Decision

The company and the site are called **ZinvestIQ**. The site's name lives in one place, `web/messages/en.json`
(`site.name`); the Sinhala and Tamil files fall back to it until translated. The accounts in the switch-on checklist
are named `zinvestiq-prod` (Supabase), `zinvestiq-raw` (R2) and `zinvestiq-raw-copy` (B2). The collectors identify
themselves to the CSE and the PDMO as `zinvestiq-market-data`.

## Not changed

- The repository is still `TBD`; renaming it on GitHub is optional and harmless (GitHub redirects).
- Code comments marked "TBD:" are this platform's change markers on code ported from the old tools; they keep that
  meaning.

## Before relying on the name

Domain availability (.com, .lk), the Registrar of Companies, a trademark search at the National Intellectual
Property Office, and the lawyer's review (docs/plan-retail-features.md §1 and §7).
