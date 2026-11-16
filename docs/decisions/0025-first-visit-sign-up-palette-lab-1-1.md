# 0025 — The first visit, sign-up, the palette, and the lab's version 1.1.0

- **Date:** 2026-11-16
- **Status:** Built on the owner's instruction of 2026-11-13 (with Janu). Points marked "to confirm" are choices
  made here for the owner to accept or change.

## Context

The owner and Janu asked for five things:

- a new colour scheme, "something the market will react well to";
- no noise on a first visit: only "Where are you starting from?", then different things shown by answer;
- a way to sign up after that, to gain sign-ups and e-mail addresses;
- the portfolio lab optimised;
- whatever else was unfinished, including charts not yet built.

## Decision

1. **The front door asks one question and shows nothing else.**
   - A first-time visitor at `/` sees the question, four answers and a way to skip. The header keeps only the brand;
     the footer keeps only the disclaimers.
   - After the second question, the path's page offers the visitor's own home page.
   - `/home/<type>/<answer>` is that home page: the blocks, guides and pages that fit the answer (`web/lib/homes.ts`).
     A newcomer sees savings first and no yield-curve chart; someone who follows bonds sees the curve first.
   - The old overview is `/markets` ("Today's markets"), for everyone.
   - Tailoring chooses what is shown first. It never changes what a tier may see: every block shows the same free
     figures, read through the same tier check (hard rule 5).
2. **The answers are remembered in one first-party cookie.**
   - `ziq-start` contains `<type>.<answer>` or `skip`. It is set by the server when a path's page is opened
     (`web/proxy.ts`), lasts a year, cannot be read by scripts, and identifies nobody.
   - With it, `/` opens on the visitor's home page (or on `/markets` after a skip). `/start` always shows the
     question again.
3. **Sign-up stores an e-mail address, with consent, and nothing more (to confirm).**
   - Accounts and an e-mail service do not exist yet (decision 0016). A sign-up is stored as `pending`.
   - Nothing is sent to an address until its owner confirms it through a link (double opt-in), which the account
     system will do. The page says this plainly; it does not claim an account exists.
   - The consent box is not pre-ticked. The weekly summary is a separate, optional box.
   - The website can add a sign-up through one checked database function and can never read the list
     (migration 0019). The answer never says whether an address was already there.
   - The owner reads the list with `python -m data_platform.jobs.signups` (summary, list, export, unsubscribe,
     delete).
   - A plain privacy page, `/privacy`, says what is kept and how to have it removed.
4. **Palette: "Ceylon Sapphire" (to confirm).**
   - Deep sapphire and navy, a little gold, a clean cool ground. It replaces Evergreen.
   - Reasons:
     - Blue is the colour most used by financial brands, and the one people have learnt to read as "an institution
       to trust" (a design agency's review found blue in about half of the fifty largest financial brands).
     - A green brand in a markets product is read as "rose". Green and red now mean only "rose" and "fell".
     - Sapphire and gold are recognisably Sri Lankan without copying any bank's colours.
   - Chart colours are a fixed order of five, checked by a validator for colour-blind separation and contrast in
     light and dark. None is green or red.
5. **The lab's version 1.1.0** (`cse_lab_backtest`; `docs/research/portfolio-lab-optimisation-2026-11.md`).
   - The covariance is estimated from daily returns with two lagged days. It was chosen on realised risk in a weekly
     walk-forward test, never on returns. The test is stored with the model and repeats itself as history grows.
   - A K-name portfolio is filled with the shares minimum variance would take next.
   - A review trades the least that keeps estimated volatility within 1 % of the minimum.
   - Version 1.0.0 keeps running as the reference. The example portfolio stays minimum variance, 15 names, quarterly
     (decision 0024).
   - The lab stays internal: no route on the real site, every output unpublished (decision 0023).
6. **Charts added.**
   - Site: turnover and foreign-flow bars and an ASPI/S&P SL20 comparison on the market page; yields over time on
     the bonds page; carry against duration on the carry page.
   - Lab report: value over time, falls from the peak, the risk test, cost per review, value against risk share by
     share, and sectors.

## Consequences

- **Before the real site collects any address**, the lawyer's view of the Personal Data Protection Act is needed
  (`docs/plan-retail-features.md` §7 item 6), and the privacy page must name who is responsible for the data and how
  to reach them. Both are on the switch-on checklist. The preview's sign-up form sends and keeps nothing.
- Sign-up on a deployed site needs `FEEDBACK_KEY_SECRET` (it shares the feedback forms' sender key); without it the
  form says sign-up is not switched on.
- The cookie is a preference cookie, described on the privacy page. No consent banner is planned for it; the lawyer
  should confirm that.
- Two new migrations (0019 sign-ups, 0020 the risk test) and one new internal output table.
- To revisit:
  - the palette and the wording of the four homes, once the owners have used the preview;
  - moving `cse_risk_estimates`, `cse_portfolio_lab` and `cse_lab_record` to the daily estimate (a new version of
    each), once the owner has seen the research note;
  - the lab's choices again with twelve months of results.
