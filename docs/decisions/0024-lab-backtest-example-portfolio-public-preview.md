# 0024 — The lab's walk-forward test, how the example portfolio is built, and the public preview link

- **Date:** 2026-11-01
- **Status:** Accepted in part. The owner asked for the backtest, the dynamic rebalancing and the public link
  (2026-11-01). The choice of the example portfolio (point 3) is a proposal for the owner to confirm.

## Context

The owner asked for four things:

- the portfolio lab finished "properly";
- a dynamic rebalancing feature;
- a backtest of what the rules' portfolio would have returned "if we went with it a year ago";
- the same rules used to build and justify today's portfolio.

All of it is to be presented as education, not advice. The owner also asked for the preview as a public page reachable
by a link.

## Decision

1. **A walk-forward test, `cse_lab_backtest` (internal, like the rest of the lab; migration 0017).**
   - On each past date, it applies the lab's own rules using only what was known on that date.
   - It simulates holding the result, with the record's execution rules and costs.
   - The ASPI and treasury bills sit beside it. `data_platform/models/cse_lab_backtest/METHOD.md` has the rules.
   - It cannot start a year ago. The CSE's public price history reaches back one year, and the rules need half a year
     of weekly returns before their first estimate, so the honest start is 8 April 2026.
   - It lengthens by itself as history accumulates. The CSE's historical data, part of the permission request, would
     allow a multi-year test.
2. **Two rebalancing policies, side by side.**
   - **Quarterly:** the lab's rule, with a drift band in between.
   - **Dynamic:** a monthly check that rebalances only when the holdings have moved more than 3 % of estimated
     tracking error away from the rules' fresh portfolio. A holding leaving the universe also triggers it.
   - The comparison shows the trade-off between reacting and paying costs.
3. **The example portfolio (proposal): minimum variance, 15 names, quarterly reviews.** Reasons:
   - It is the rules' steadiest portfolio, and its construction uses no return forecast.
   - Maximum Sharpe depends on an assumed 6 % premium and changes its largest names on small data changes.
   - 15 names had lower volatility than 10 in the test, for similar costs.
   - The monthly check traded about twice as often without earning its costs back in the period tested.
   - The choice is to be revisited after twelve months of results. Six months says little about any method.
   - Today's example portfolio is the latest quarterly review's weights. Each holding comes with the measurements that
     explain it (volatility against the universe's median, beta, average correlation with the other names, risk
     contribution, the cap or floor, kept or new).
4. **Education framing.** Every lab page states three things:
   - the rules are written in advance and applied to public data;
   - the test uses only information available at each date;
   - nothing considers anyone's circumstances or says what to do.

   The three publishing paths for the lawyer (plan §5: P1 licensed adviser, P2 rules-based index, P3 user-run tool)
   stay in the report.
5. **The public preview link (owner's instruction).**
   - The preview stays an Artifact. Making it reachable by anyone with the link is done by the owner from the page's
     Share menu; this session cannot change sharing.
   - Its pages carry `noindex`, so search engines are asked not to list them.
   - **What a public link exposes**, as the owner was told:
     - every tier's data on every page (the preview switches tiers in the browser; the real site's server-side tier
       check is unchanged);
     - directors' and shareholders' names (decision 0021);
     - the lab page.
   - The lawyer's view (plan §7 items 9 and 10, §5) and the CSE's permission (roadmap item 0) are still needed before
     the real site launches. The preview is not the launch.

## Consequences

- One new internal model and one migration. No change to the real site's tiers or pages: the lab still has no route
  there.
- The lab report (`jobs/lab_report`) opens with the rules, the walk-forward test and today's example portfolio, then
  the existing workings and the mock-ups.
- To revisit:
  - the example's choice and the 3 % threshold, with twelve months of results;
  - the cost per side, against the current CSE schedule;
  - the minimum trade size, which drives the costs of small portfolios.
