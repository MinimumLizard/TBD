# Retail features: plan and open questions (2026-10-16)

The owner and Janu asked for six changes to make ZinvestIQ friendlier to retail investors. This page says what each
one needs, what can be built now, what must wait for a lawyer, and the decisions only the owner can make. It is a
proposal: nothing here is built yet except the name (§1).

| # | Request | Can it be built? | Waits on | Proposed phase |
|---|---|---|---|---|
| 1 | Name the company ZinvestIQ | Done on the site | Name checks (§1) | Done |
| 2 | Weekly email updates, per market and tier | Yes | Accounts (Phase 4b); an email provider | 4b |
| 3 | Community interaction, for feedback | Feedback: yes. Open discussion: later | Lawyer, for discussion | 4b (feedback) |
| 4 | "FD vs the market" comparison | Yes for the market and for bills/bonds; **not yet** for the Sharpe basket | Long price history; a forward record | 5 (new) |
| 5 | Rebalancing signals as a value proposition | Engine: yes. **Publishing: needs a lawyer** | Lawyer; possibly an SEC licence | 3b (engine), then gated |
| 6 | Model portfolios with fewer names | **Yes: 10–15 names hold up** (§6) | Phase 3b port of the portfolio lab | 3b |

## 1. The name: ZinvestIQ

The site now says ZinvestIQ (`web/messages/en.json`), and the switch-on checklist names the accounts
`zinvestiq-prod`, `zinvestiq-raw` and `zinvestiq-raw-copy`. Decision 0017 records it. Before printing it on
anything, check:

- **Domains:** zinvestiq.com and zinvestiq.lk (the .lk registry is run by LK Domain Registry).
- **Company name:** reserve it with the Registrar of Companies when the company is formed.
- **Trademark:** a search at the National Intellectual Property Office of Sri Lanka, and in any market you may enter.
- **The lawyer (§7):** whether a name containing "invest" adds to how the service is read under the SEC's rules.
  It probably does not on its own, but it is cheap to ask together with §5.

The repository can keep the name `TBD`, or you can rename it on GitHub (Settings → General → Repository name);
GitHub redirects the old address, so nothing breaks.

## 2. Weekly email updates

**What it would be:** every Saturday morning (after Friday's close and the weekly model run), one email per market
(CSE, government bonds) to each subscriber of that market. It says what changed this week, in the site's neutral
language, for example: index and breadth, the bond curve's shift, the largest curve residual changes,
new dividends and disclosures. It links back to the pages.

**How it stays inside the rules:**

- **Hard rule 5 applies to email too.** A paid number must never reach an unentitled inbox. So the email is built
  by the website's server through the same tier check (`web/lib/entitlements.ts`), once per tier and market
  (2 markets × 4 tiers = 8 versions), and each subscriber gets the version for their tier. Not one email per
  person: that also keeps it non-personalised (decision 0010 point 4).
- The copy lint scans the email templates, and every email carries the disclaimer from the one registry.
- **Consent and unsubscribing:** Sri Lanka's Personal Data Protection Act (No. 9 of 2022) applies. That means opt-in,
  a stated purpose, one-click unsubscribe and deletion on request.

**What it needs:**

- User accounts with email addresses and tiers (Phase 4b).
- A managed email service. Resend or Postmark are boring, cheap and well documented: free up to a few thousand emails
  a month, then roughly USD 15–20 a month (check current prices).
- Your domain's mail records (SPF, DKIM, DMARC) so the emails are not marked as spam.
- One scheduled job.

**Effort:** about a week once accounts exist.

**Built so far (2026-10-18), without accounts:** the e-mail itself. `web/lib/email/weekly.ts` builds each market's
e-mail for one tier through the same data functions and tier check as the pages; `web/lib/email/digest.ts` turns it
into the HTML and plain-text bodies (tables and inline styles, which e-mail programs show reliably). A visitor can
see this week's e-mail for their own plan at `/email/cse` and `/email/bonds`, and the tier-leak tests check that the
bond e-mail carries Plus and Pro numbers only to those tiers (with no delayed preview: an e-mail dated this week
should not carry last week's figures). What remains needs accounts: the subscriber list, consent and unsubscribe
links, the e-mail service and its domain records, and one scheduled sender (a Vercel cron route protected by
`CRON_SECRET` that builds the 8 versions in-process and hands each to the e-mail service with its subscribers; no
address of the site will ever take a tier as a parameter).

## 3. Community interaction and feedback

There are three levels, with very different risk:

| Option | What it is | Risk | Recommendation |
|---|---|---|---|
| A. Feedback | "Was this useful?" and a comment box on every page; a page of requested features where signed-in users vote | Low: users talk to us, not to each other about shares | **Build in Phase 4b** |
| B. One-way channel | A WhatsApp Channel or Telegram channel for announcements ("new page", "data delayed") | Low, if it only carries what the site says | Optional, any time |
| C. Discussion | A forum or group chat where users discuss shares | **High:** the platform would host other people's tips and rumours. The SEC acts against stock tips and market manipulation online, and the host can be drawn in. It needs rules, active moderation and a lawyer's view | **Not before the lawyer says how** |

Option A is small to build on the database we already have: one table and one form. Signed-in users only, which
limits spam. Moderated before anything is shown publicly.

**Built (2026-10-18):** option A without the vote page (that needs accounts). Every page's footer asks "Was this
page useful? Yes / No" and links to `/feedback`, a short form (topic and message; no name or e-mail). Both are plain
forms that work without JavaScript. Nothing anyone writes is shown on the site. Safeguards:

- The website's database login still cannot read anything but model outputs: it can only call one function,
  `community.submit_feedback()` (migration 0012), which checks every field and refuses more than 30 votes or 5
  messages an hour from one sender, or 2,000 an hour from everyone.
- The sender's network address is never stored, only a scrambled form of it (keyed with `FEEDBACK_KEY_SECRET`),
  deleted after seven days. Posts from other websites are refused, and a hidden field catches simple bots.
- You read it with `uv run python -m data_platform.jobs.feedback summary | list | mark | delete` (delete is for
  a request under the Personal Data Protection Act).
- Until accounts exist anyone can send feedback; when they do, messages can be limited to signed-in users.

## 4. "FD vs the market" comparison

This is a good idea. Most Sri Lankan savers compare everything with a fixed deposit, so showing the trade-off
honestly is exactly the education the site is for. The honest version has limits that matter.

**What the data allows today:**

- **Share prices go back only to October 2025.** The CSE's own chart endpoint serves 240 sessions, and that is all
  the old tool or this platform holds (audit §2.2). The total-return index begins on 2026-10-01 in our data.
- **Bond quotes go back to 2025-12-01** (the old Nelson-Siegel database), auctions to 2025-12-11.
- **FD rates are not collected at all.** The Central Bank (CBSL) publishes the average weighted fixed-deposit rate
  (AWFDR) and treasury bill yields with long histories. Its terms must be checked under decision 0009 before use.

**The Sharpe basket cannot be compared yet, honestly.** The portfolio model needs 52 weeks of returns before it
can form its first portfolio, and prices start in October 2025, so the first possible portfolio date is October
2026: the old tool's live record began on 2026-10-07. Any figure for "if you had invested in the Sharpe basket a
year ago" would be a backtest built with hindsight: today's choice of shares, tested on the past it was chosen
from. That overstates returns, and showing it to retail investors would be misleading. Regulators treat
hypothetical performance shown to the public seriously.

**Built 2026-10-18 (owner's approval of that day):** the fixed deposit vs treasury bills vs inflation part of item 1
and its calculator, at `/learn/savings`, from the CBSL's monthly interest-rate table (2003 to date) and the CCPI
(collectors `cbsl` and `dcs_cpi`; model `lk_savings_compare`, method in its METHOD.md). Taxes: the advance income tax
on deposit interest from 2023; bill interest taxed at each person's rate, so bills are shown before tax. Government
bonds and the share market are not in it yet.

**What can be built (proposal, a new "Phase 5: retail education"):**

1. **FD vs treasury bills vs government bonds**, from the CBSL's published rates (if its terms allow) and our own
   bond data. These are products a saver can buy instead of an FD. Fully factual; no model involved.
2. **FD vs the share market** (ASPI or S&P SL20, total return where available). It shows the whole distribution,
   not one lucky period: "in X of the Y one-year periods since …, the market returned more than a 12-month FD;
   the worst was −Z%". It includes 2022. It needs long index history: the CSE data licence (enquiry outstanding)
   or the CBSL's published index series.
3. **A calculator:** amount, start date and horizon in; the FD's value and the market's value out, with the
   assumptions shown.
4. **The model portfolios' forward record**, once one exists. Show it only after a minimum period (12 months
   proposed), only after the lawyer's view (§5), and always beside the market and the FD.

Every comparison must include:

- trading costs: 1.12% per side in the old tool, still marked "verify";
- withholding tax on dividends and on FD interest (current rates to be confirmed);
- inflation;
- the bad periods, not only the good ones.

## 5. Rebalancing signals: the biggest decision

The old terminal already runs model portfolios with a live record and a quarterly rebalance (audit §2.3, C10–C12).
Publishing them was deliberately **deferred until a lawyer's view** in Phase 1 (decision 0010 point 6, architecture
§3), and hard rule 4 forbids buy/sell language and recommendations. Sending subscribers "rebalance: add X, reduce Y"
is, in substance, what an investment adviser does. As we understand it, investment advice is a regulated
activity under the SEC Act No. 19 of 2021. **A Sri Lankan lawyer must confirm** before any of this is published.

There are three ways it could go. The lawyer decides which are open:

| Path | What subscribers see | What it needs |
|---|---|---|
| **P1. Become licensed** | Model portfolios and their rebalancing, as advice | SEC registration as an investment adviser (capital, qualified people, compliance procedures). Slow and costly, but it makes the value proposition fully legal |
| **P2. Publish indices** | Rules-based indices ("ZinvestIQ CSE Minimum Variance 15"), with published rules and scheduled reconstitutions reported as index changes ("weight 6.1% → 4.8%") | A lawyer's view that this is information and not advice; the rules published in full; no instruction to anyone |
| **P3. A tool** | An optimiser the user runs: they choose the constraints, the tool shows the resulting portfolio and its risk | A lawyer's view on where a tool becomes advice. It must not take in the user's own holdings or circumstances (decision 0010 point 4) |

**Recommendation:** build the engine now, as internal research (Phase 3b: port the portfolio lab with parity, plus
the fewer-name versions in §6). Publish nothing. Take concrete mock-ups of P1, P2 and P3 to the lawyer. Then decide.
Once something is published to paying subscribers it is hard to take back (hard rule 7).

## 6. Model portfolios with fewer names

**The concern is right.** The current maximum-Sharpe portfolio holds 37 names (40 until 2026-10-14). With Rs 100,000,
21 of those positions would be under Rs 2,500 each, too small to be worth the trading costs. Several holdings are
token amounts: 7 names are under 1%.

**Test.** Take the K largest names of the full portfolio and re-optimise on only those. The rules are:

- the same sector (30%), ownership-group (20%) and liquidity caps;
- a per-stock cap of max(10%, 1.5/K), because 10 names at a 10% cap would leave no choice at all;
- a minimum of 0.5/K per name, so every holding is worth having.

Session 2026-10-15, the old tool's own data and code. Measured by
`scripts/research/fewer_names.py <CSE clone> out.json`, run in the old repo's environment as the script's
docstring says:

| Names | Max Sharpe: volatility | Sharpe (share of full) | Tracking error vs full | Min variance: volatility | Tracking error vs full |
|---|---|---|---|---|---|
| Full portfolio | 20.5% (37 names) | 0.533 | — | 11.1% (31 names) | — |
| 25 | 20.2% | 0.529 (99%) | 2.4% | 11.1% | 1.0% |
| 20 | 19.7% | 0.521 (98%) | 4.3% | 11.2% | 1.6% |
| 15 | 20.0% | 0.513 (96%) | 5.5% | 11.4% | 2.6% |
| 12 | 20.4% | 0.507 (95%) | 6.3% | 11.5% | 3.5% |
| 10 | 20.7% | 0.499 (94%) | 7.3% | 11.9% | 4.7% |
| 8 | 22.4% | 0.486 (91%) | 9.2% | 12.4% | 6.1% |
| 6 | 28.8% | 0.430 (81%) | 17.2% | 13.4% | 7.9% |
| 5 | not possible within the sector and group caps | | | 14.2% | 9.3% |

**What this says:**

- **10 to 15 names keep almost everything.** Risk is about the same as the full portfolio and the estimated Sharpe
  ratio within 4–6%.
- **Below 8 names it gets clearly worse:** much higher risk, and the portfolio no longer resembles the model.
- So a retail version is possible without hurting the model's integrity, provided it is presented as what it is:
  a 10- or 15-name portfolio built by the same rules, with its own record.

**Caveats that must go with it:**

- **These are in-sample estimates.** They use one year of weekly returns, the old tool's assumptions (risk-free 9.9%
  typed by hand, equity risk premium 6% assumed) and expected returns from CAPM. With one year of data, a Sharpe
  estimate's uncertainty is roughly ±1. Differences of a few hundredths are noise. The table shows the *shape*:
  little is lost down to about 10 names. It does not promise any return.
- **Maximum Sharpe is unstable.** On 2026-10-14, one new week of data swapped 2 of the top 10 names and moved 15.6%
  of the portfolio (measured from the old tool's `data/lab/*.json`). A small portfolio rebuilt every week would trade
  constantly. The retail versions should therefore:
  - rebalance only on a fixed calendar (quarterly, as the lab already does);
  - use a buffer: a held name stays until it drops well out of the top K, for example the top 1.5K;
  - include costs in their record.

**Which portfolio for retail (my view):** **minimum variance with 15 names, rebalanced quarterly** as the main one,
with maximum Sharpe 15 and an equal-weight 15 beside it for comparison. The reasons:

- It does not depend on expected returns, which is the weakest input here (CAPM with an assumed premium).
- It is far more stable from week to week.
- Its estimated risk is about half that of maximum Sharpe (11% vs 20% a year). That matters for savers moving
  from FDs, who feel losses most.

All of them are measured forward from the day they start, never backfilled.

## 7. What to ask the lawyer (add to the legal review, roadmap item 4)

1. Is publishing model portfolios, their weights and their scheduled changes to paying subscribers "investment advice"
   under the SEC Act No. 19 of 2021? Under P2 (indices) and under P3 (a user-run tool)?
2. If it is, what does registration as an investment adviser require, and how long does it take?
3. Can a "FD vs market" comparison and a model portfolio's forward record be shown, and with what wording?
4. Does hosting user discussion (§3 C) expose the company, and what moderation would be expected?
5. The disclaimers, the method pages, the email templates and the name.
6. The Personal Data Protection Act for accounts and email.
7. Market data (added 2026-10-18). The CSE's website terms (www.cse.lk/disclaimer) limit its data to personal,
   non-commercial use without the CEO's written permission. How enforceable are website terms of this kind in Sri
   Lanka, and do bare facts such as a day's closing price have any protection beyond them? Whatever the answer, the
   plan is to ask the CSE for permission or buy a licence (roadmap item 0); this question is about the risk while
   that is pending. Taking the same prices from a third party such as TradingView does not help: its own terms
   allow display-only, personal use, forbid "creating products or services based on TradingView content", and it
   receives the CSE's data under its own agreement with the exchange. Its free embeddable chart widgets are the one
   use it offers websites; confirm their terms for a paid site before using them.
8. Two companies (added 2026-10-19, decision 0020). The Sri Lankan product (ZinvestIQ) and a separate crypto and
   global markets product start from the same platform code, written for the owners. Which company owns that code,
   and on what terms does the other use it (an assignment and a licence)? Anything to keep the two clearly separate
   (names, directors, shared staff, cross-promotion) given the CBSL's position on crypto?
9. Directors' dealings (added 2026-10-19, Phase 3b part 3). Listed companies announce every share dealing by a
   director, and the CSE publishes the notice, naming the director and any related account (a relative, or a company
   the director is connected with). The owners decided to show the names as filed, with a link to the CSE's notice
   (decision 0021, 2026-10-19), alongside each transaction's company, the director's role in a short category ("non-executive
   director", "chair"), own or related account, purchase or disposal, shares, price and value, and per company the
   totals, the number of accounts on each side and a "cluster" mark (two or more accounts making purchases, with
   purchases above disposals). (a) Under the Personal Data Protection Act, may we show the director's name, the
   related account's name, or a link to the CSE's own notice (which names them), given the notice is already public?
   (b) Can a role reveal a person even without the name (a company has one chair), and is that acceptable? (c) Is a
   per-company "cluster" mark, or a list of companies ordered by the value of directors' dealings, at risk of being
   read as investment advice, and what wording keeps it factual? The names are shown in the private preview; nothing
   is public before your answer.
10. Shareholder lists (added 2026-10-19, Phase 3b part 3). Every interim report lists the company's twenty largest
    shareholders, many of them private individuals (and joint holders, estates and family trusts). We store the
    lists, credit each holding to its beneficial owner (custodian and margin accounts resolved), and publish only
    company-level figures: the share held by the top 20 by type of owner, whether one block controls the company
    (over 50 %) or has influence (20–50 %), its ownership group, and a free-float estimate. The controlling block or
    group head is named only when it is a company, a fund or the state; otherwise only its type ("an individual").
    (a) Under the Personal Data Protection Act, may we show individual shareholders' names and holdings, or a
    per-person view across companies ("who holds what"), given each report is public? (b) Can "controlled by an
    individual" or a group of companies headed by one unnamed person still identify that person, and is that
    acceptable? (c) The owner keeps confirmations that two spellings are one person in a private file outside the
    public repository (`OWNERSHIP_PRIVATE_FILE`): is storing such a link in our database acceptable, and on what
    basis? The two tables with names (`models.cse_holding`, `models.cse_ownership_detail`) are served to nobody, and
    the website's database login cannot read them, until you answer.

## 8. Proposed order of work

1. **Now (done this session):** the name, a visual preview of the site, and the CSE market-status fix
   (`docs/phase3-4-verification.md` §10).
2. **Phase 3b, CSE models, in this order:**
   1. **Corporate actions and total returns (C6, C7).** Every return comparison needs dividends and splits; without
      them, prices understate returns and splits look like crashes.
   2. **Risk estimates and the portfolio lab (C8–C10), internal only.** The ported version must reproduce the old
      tool exactly; the fewer-name versions sit beside it.
   3. **Fundamentals (C21, C22).** P/E, dividend yield and book value are retail-friendly education.
   4. **Ownership, directors' dealings and flows (C13–C20).** The most work (report text parsing) and very
      distinctive.
3. **Phase 4b:** accounts, payments, weekly emails, the feedback feature, Sinhala and Tamil, Vercel.
4. **Phase 5 (new), retail education:** FD vs bills and bonds; FD vs the market; the calculator.
5. **After the lawyer:** whichever of P1–P3 is open, and any discussion feature.

## 8a. Small changes to make the existing site friendlier (from the first visual review)

- **Company names beside share codes.** Today it shows "JKH.N0000" alone. The name is collected (`cse.security_list`)
  but not yet in the share model's output.
- **Plain-language help** for terms a new investor will not know (basis points, curve residual, breadth, z-score,
  carry): a short glossary, linked from where each term appears.
- **A logo and colours** once the name is cleared (§1).
- **Dividend- and split-adjusted price charts**, which come with corporate actions (Phase 3b, first).

## 9. Decisions for you and Janu

1. Is the Phase 3b order in §8 right? I can start corporate actions and total returns as soon as you say so.
2. Agree that the model portfolios are built internally now and published only after the lawyer (§5)?
3. Feedback first (§3 A), and open discussion only after the lawyer?
4. For the FD comparison: start with FD vs bills and bonds, and FD vs the market? Show the Sharpe basket only after
   12 months of forward record?
5. Retail portfolios: 15 names, with minimum variance as the main one (§6)? Or 10 names?
6. Weekly emails on Saturday morning?
