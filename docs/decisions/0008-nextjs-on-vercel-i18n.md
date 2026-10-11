# 0008 — Next.js on Vercel Pro; all copy in message files for Sinhala and Tamil

- **Date:** 2026-10-11
- **Status:** Proposed (the owner's default, confirmed)

## Decision

- Next.js (App Router, TypeScript) on **Vercel Pro** ($20/month per developer seat). **Vercel's Hobby plan is
  "for personal, non-commercial use"**, so it can't host the product.
- `next-intl` with `web/messages/{en,si,ta}.json`. No user-facing string in code. Locale-aware numbers and dates.
  Noto Sans Sinhala and Noto Sans Tamil fonts.
- One chart library: Apache ECharts (Apache-2.0).
- Mobile-first design tokens and components, shared by every page.

## Alternatives considered

- **Cloudflare Pages / Netlify:** cheaper at scale, but Next.js's server features are first-class on Vercel, and fewer
  surprises matter more than $20/month.
- **Keeping the three existing front-ends:** they are three different stacks (Jinja, Python strings, Vite) and all
  are static, so they can't do server-side tier checks.

## Consequences

Keeping all copy in message files also gives the copy lint one place to scan (decision 0010).
