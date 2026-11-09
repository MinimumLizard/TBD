# Janu's review (2026-11-09): what was built and what waits

Janu reviewed the preview and sent notes on how a first-time visitor should be met. This file maps each point to what
was built on 2026-11-09, and sets out the plan for the points that need accounts or an outside service first. Nothing
here changes the rule that the site gives information and education, never advice (hard rule 4).

## 1. Each point and where it landed

| Janu's point | Status | Where |
|---|---|---|
| Ask "what type of investor are you?" on the first page | **Built** | Home page, first section; also `/start`. Four choices: completely new; knows the basics but has not invested; invests but is not always sure; invests and wants sharper tools |
| Tailor it with questions, and do not ask investors the questions meant for people who have not started | **Built** | `/start/<type>`: one follow-up question per type. Only the first two types reach the "how do I start (accounts, brokers, minimums)" route |
| "Based on what you told me, this is where to start": guide first, then show what it is for | **Built** | `/start/<type>/<answer>`: three steps. Each step is a guide and the page of the site it explains ("Then use it here") |
| People do not know how to start | **Built** | New guide `/learn/getting-started`: fixed deposits, bills and bonds, the CDS account through a stockbroker, fees of about 1.1 % a trade, unit trusts |
| Statistics that make visitors feel seen | **Built** | "You're not alone": about 1 in 500 Sri Lankans invests on the CSE (CSE chairman, via Echelon); about 4 in 10 adults are not financially literate (CBSL survey, via The Morning); and our own figure, how many one-year fixed deposits since 2003 lost value after tax and inflation (85 of 272 in the preview data). Each one links to its source |
| A review after each guide ("10k people found this useful") | **Built, with one condition** | "Was this guide useful?" box at the end of every guide. The count appears only once a guide has 25 or more "useful" votes. Below that, the box only asks. A number is never invented |
| Avoid choice overload | **Built** | Each path shows three steps, and the first is marked as the one to start with. The old four-card "Where to start" section is removed |
| One week of Pro in exchange for a review | **Plan (§2)** | Needs accounts (Phase 4b) |
| A chatbot | **Plan (§3)** | Needs an AI service account, a budget and a lawyer's view of the answers it may give |
| Email capture | **Parked** | Janu's notes marked it for later; the weekly e-mail plan stays as in `docs/plan-retail-features.md` §2 |

How it works:

- The paths are in `web/lib/paths.ts` and the text is in `web/messages/en.json` (`start.*`).
- Every path is a plain web address. It works without JavaScript, can be shared, and is in the preview.
- The browser remembers the last path. The home page then offers "Continue your starting path". Nothing about it is
  sent to the server.
- The paths choose what to read. They never say what to do with money, and each result page says so.

How the vote count works:

- Votes count per page. Migration `0018_page_vote_counts.sql` keeps one vote per visitor and page: a second vote
  replaces the first while the visitor's key is still kept, which is seven days. Repeating a vote cannot push the count
  up.
- The website can read only the two totals for a page (`community.page_votes`). It cannot read any row, key or
  message.
- The 25-vote threshold is `SHOW_COUNT_FROM` in `web/lib/data/feedback.ts`.
- Footer vote: on guide pages the footer's "Was this page useful?" is hidden, because the guide's own box asks the
  same thing and records it under the same page.

## 2. Plan: one week of Pro for a review

This waits for accounts (Phase 4b), because a trial has to belong to someone and end on its own.

- **Who can have one:** a signed-in account on Free that has used the site on at least 7 different days. This keeps it
  for people who have actually used Free and can review it. One trial per account, ever; one per e-mail address.
- **What it asks:** three short questions, kept with the other feedback (`community.feedback`, a new kind
  `trial_review`):
  - What did you come to the site for?
  - What was most useful?
  - What was missing or unclear?
  An optional fourth question asks whether the answer may be quoted on the site, by first name only.
- **What it gives:** Pro for 7 days from the moment the review is sent. The grant is a row with an end date, read by
  `web/lib/entitlements.ts`, which stays the only tier check (hard rule 5). The trial ends on its own; nothing is
  charged and no card is asked for.
- **Data protection:** the review is personal data under the Personal Data Protection Act. It is kept with the
  account and deleted with it. Quotes are used only with the tick-box consent.
- **Owner decisions needed:**
  1. Is 7 days of use the right bar?
  2. May reviews be quoted on the site?
  3. Should Plus users also be offered a week of Pro?

## 3. Plan: a chatbot

A chatbot can help someone who does not know what to search for. It is also the feature most likely to drift into
advice, so it needs the tightest limits.

- **What it may answer from:** only the site's own text: the guides, the glossary, the methods pages (METHOD.md) and
  the published figures for the day. It answers in plain language and links to the page it took the answer from. If
  the answer is not in that material, it says so.
- **What it must refuse:**
  - any question about what to do with money ("should I…", "which share…", "is now a good time…");
  - anything about a person's own circumstances;
  - forecasts.
  The refusal links to the guide that explains how to judge the question. It never gives an opinion.
- **Checks:**
  - the copy lint's banned phrases are applied to every answer before it is shown;
  - a test set of about 200 questions (half of them attempts to get advice) must pass before launch and after any
    change.
- **Service:** an AI provider's API (Anthropic's Claude, for example), called from the server so the key never reaches
  the browser (hard rule 3). Cost depends on use; a monthly cap is set in the provider's console. Conversations would
  be personal data: kept for 30 days for quality checks, then deleted, and the visitor is told so.
- **Before anything is built:**
  1. The owner opens an account with the provider and sets a budget.
  2. The lawyer reviews the refusal rules and the test set, and confirms the bot is information rather than advice.
     This is the same question as `docs/plan-retail-features.md` §7.
  3. The owner confirms who "Hatim" is. Janu's note mentions the name next to the chatbot, and we read it as a person
     to involve (perhaps someone who has built one).
- **Order:** after accounts, because a limit per account is the simplest way to cap cost and abuse.

## 4. What the owner may want to change

- The four starting types and their follow-up questions: the wording is in `web/messages/en.json` (`start.types`,
  `start.questions`).
- Which guides each answer leads to: `web/lib/paths.ts`. A unit test (`web/tests/unit/paths.test.ts`) checks that
  every step leads to a real guide and page.
- The statistics: each one has its source next to it.
  - The "1 in 500" figure is the CSE chairman's "about 50,000 active investors, 0.2 % of the population".
  - The "4 in 10" figure is the CBSL survey's 58 % financially literate.
  - If newer figures are published, update `start.stats` and the links in `web/components/Stats.tsx`.
