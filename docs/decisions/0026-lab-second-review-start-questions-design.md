# 0026 — The lab's second review, questions 3 and 4, and a calmer design

- **Date:** 2026-11-20
- **Status:** Built on the owner's instruction of 2026-11-20. Points marked "to confirm" are choices made here for
  the owner to accept or change.

## Context

The owner asked for four things:

- a less "clunky" look;
- a test for bugs, and a review of every formula the lab uses;
- a review of how the lab balances and rebalances, against the academic literature, tested on the data;
- two more questions on the starting screen, such as the amount, so that more of what is shown fits the visitor.

## Decision

1. **The lab's second review was planned before it was run.**
   - The questions, the test (Ledoit and Wolf 2011, studentised block bootstrap, with Holm's correction) and the
     adoption rules were committed before any result was seen (`docs/research/portfolio-lab-optimisation-2026-11.md`
     §7.1 to §7.3). A method is never chosen on backtested returns (decision 0025).
   - Candidates tested:
     - for the risk estimate: nonlinear shrinkage (Ledoit and Wolf 2020) and exponential weighting (RiskMetrics);
     - for building the portfolio: hierarchical risk parity (López de Prado 2016), inverse volatility, equal risk
       contribution (Maillard, Roncalli and Teïletche 2010), maximum diversification (Choueifaty and Coignard
       2008) and equal weight (DeMiguel, Garlappi and Uppal 2009);
     - for rebalancing: partial adjustment (Gârleanu and Pedersen 2013), monthly and half-yearly reviews, and a
       wider no-trade band (Leland 1999).
2. **Kept:**
   - the risk estimate (daily returns with two lagged days, linear shrinkage);
   - minimum variance within the caps.

   No alternative passed the pre-registered rule, except one: hierarchical risk parity, and only when it was allowed
   to ignore the lab's caps. Within the same caps it was no steadier, and with costs it cost more (§7.6).
3. **Changed: reviews twice a year, January and July, instead of four times.**
   - They cost 22 % less over the test and were no more volatile, which is the pre-registered test.
   - `cse_lab_backtest` 1.2.0 is current. It runs the half-yearly, quarterly and monthly-check policies side by
     side; 1.1.0 is kept as the reference.
   - `cse_portfolio_lab` 1.2.0 and `cse_lab_record` 1.2.0 review their K-name versions in January and July. Neither
     has had a production run (decision 0015 rule 11).
   - The lab page shows the three schedules side by side and explains why twice a year.
4. **Formula review:**
   - F1. Dividends are now credited after the final 15 % withholding tax (since 1 January 2023; Inland Revenue
     (Amendment) Act No. 45 of 2022). This applies to every walk-forward version and to the record's 1.2.0.
   - F2. Tiny weights (below 1e-6) are now set to zero, so the stored weights sum to 1.
   - The 1.12 % cost per side is confirmed against the brokers' published schedules.
   - A new audit, `python -m data_platform.jobs.lab_audit`, rebuilds every walk-forward book from its trades and
     checks caps, floors, costs, whole shares, review dates and summaries. It passes on every stored row.
5. **Questions 3 and 4 on the starting screen: roughly how much, and when the money might be needed.**
   - Both questions are optional, with "Prefer not to say" or "Not sure" as an answer.
   - The answers change only **facts** that are shown:
     - for the amount: what trading costs at an amount like it, how many shares of a typical price it buys,
       whether it is above the deposit-insurance limit, and a link to the calculator;
     - for the period: how often deposits and bills kept their value over every past period that long, the worst
       such period, and how far the share market fell in the past year.
   - They never change what is suggested, because nothing is suggested.
   - The answers are kept in the same `ziq-start` cookie (`type.answer.amount.horizon`), in the visitor's browser
     only. They identify nobody and are not stored on the server.
   - **For the lawyer (to add to plan §7):** facts selected by a visitor's amount and time horizon could be read as
     "personalised". The copy says plainly that these are facts about the past and about costs, not a suggestion,
     but the lawyer's view is needed before the real site asks these questions.
6. **A calmer design.**
   - Fixed a layout bug: every page's content sat flush under the header, because `.container`'s padding
     overrode `main`'s.
   - Boxes inside boxes are flattened:
     - tiles inside a card have no second border;
     - the coloured side bars are gone;
     - the on-page links and related links are soft pills instead of outlined ones.
   - Spacing:
     - more space between sections;
     - softer shadows;
     - link cards lift on hover;
     - the starting path is numbered;
     - with neither new question answered, one line and a button replace two empty cards.
   - On the lab page, the intro's three points are three cards.
   - The palette (Ceylon Sapphire) is unchanged.

## To confirm

- Twice-yearly reviews for the example portfolio (point 3). Quarterly results stay visible beside it.
- The lab's caps stay, although hierarchical risk parity without them was steadier over this short test (point 2).
- The wording of questions 3 and 4 and of their facts, before the lawyer sees it.
