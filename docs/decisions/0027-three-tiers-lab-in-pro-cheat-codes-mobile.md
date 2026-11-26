# 0027 — Three tiers, the portfolio lab in Pro, cheat codes, and a mobile-first site

- **Date:** 2026-11-26
- **Status:** The owner's decisions of 2026-11-26 (points 1 to 3), asked and answered in writing in the session. Points
  4 and 5 are built on the owner's instruction.

## Context

The owner (with Janu) asked for:

- a site built for phones, "sleek and navigable", without filler text;
- three tiers, Free, Pro and Plus: the portfolio lab and share analysis in Pro, all bond analysis in Plus, with the
  premium topics highlighted;
- subtle, compact pointers ("cheat codes") to what most Sri Lankans do not know is public: directors' dealings, money
  flows by one search, ownership structures.

## Decision

1. **Three tiers, a ladder: Free < Pro < Plus** (the owner chose the ladder over side-by-side tiers). Professional is
   dropped. `config/entitlements.yaml` is the only place a tier is set:
   - **Free: the market and a taste of each cheat code.**
     - Prices and indices.
     - Dividends and splits.
     - Directors' dealings, as filed.
     - Each company's owner types, free float and **top three shareholders**.
     - Money flows a week late.
     - The bond list, and the last 30 days of the yield curve.
     - Bond z-scores five days late.
     - The savings comparison, and every guide.
   - **Pro: share analysis and the portfolio lab.**
     - Money flows on the day.
     - Full ownership: the top 20, the controller, the chain and the group.
     - Total returns.
     - Company figures: P/E, P/B, ROE and dividend yield.
     - The portfolio lab.
   - **Plus: everything in Pro, plus every bond analysis.**
     - Each bond's full curve history.
     - Z-scores on the day.
     - Trades against dealers' quotes.
     - Liquidity.
     - Carry, roll-down, duration and convexity.
2. **The portfolio lab is in Pro, and goes live with the site** (the owner's written decision, 2026-11-26).
   - This relaxes the safeguard of decision 0010 point 6 and decision 0023, which kept model portfolios internal
     until a lawyer's view. The owner chose it over the alternative offered: a Pro page kept switched off until the
     lawyer's view.
   - What is published: `cse_lab_backtest` (current 1.2.0), on neutral settings: Rs 1 mn and no personal settings.
     It shows:
     - the example portfolio (minimum variance, 15 names, reviewed twice a year);
     - its record since April, with costs and dividends net of tax;
     - the three review schedules.
   - Migration 0022 gives the website's role read access to those tables.
   - What stays internal: `cse_risk_estimates`, `cse_portfolio_lab` and `cse_lab_record`. The last reads the owner's
     private settings.
   - The page is worded as education ("a worked example to learn from, not a list to copy"), passes the copy lint,
     and carries the general disclaimer.
   - The launch of the site as a whole still waits for the CSE's written permission (roadmap item 0). The lawyer's
     review (roadmap item 4) still covers the rest of the site.
3. **Cheat codes: a taste free, the depth in Pro** (the owner's choice).
   - A free taste is enforced on the server by a new entitlement, `top_rows`. `web/lib/entitlements.ts` grants
     `topRows`, and `web/lib/db.ts` cuts ranked lists to the first N rows. It also refuses the columns and tables
     that are withheld: the controller, the ownership chain and the group.
   - The leak suite checks this: the fourth holder and the group head never reach a free visitor, and do reach Pro.
4. **Cheat codes are shown subtly.**
   - One glowing accent colour, amber on a soft gold ground. It checks above 5:1 for contrast, and is luminous in
     dark mode.
   - It appears in five places:
     - a slim, scrollable strip on the home pages, `/markets` and `/cse`;
     - a "Cheat codes" link in the header, and a tab on phones;
     - `/codes`, eight codes with one line each;
     - each share page: Owners · Directors' trades · Money flow;
     - each company in search results: the same three, so one search reaches all of a company's codes.
   - The pulse respects reduced motion.
5. **Mobile first, less text.**
   - On phones, a tab bar at the bottom: Home, Shares, Bonds, Codes, Search. The header is slimmer and the footer is
     shorter.
   - Page intros are cut to one line.
   - The "On this page" links become one sideways-scrolling row.
   - "Why it matters" is a closed one-line toggle.
   - Sources and methods sit in one closed line.
   - The "behind the calendar" warning is a small pill.
   - Plans: three cards, each paid tier's own topics highlighted, and no method-link lists.

## To confirm

- Prices for Pro and Plus: none are shown; "Opening soon".
- Whether "Cheat codes" is the name to keep. It is a phrase the lawyer may want to see beside the disclaimer.
