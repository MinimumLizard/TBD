# Hosting ZinvestIQ: what is needed, in order

Written 2026-11-26 for the owner. The full technical checklist is `docs/phase3-4-verification.md` §6. This page is the
plain-language order of work, with what each step costs and what it does and does not open up.

## The short version

| Stage | What it gives you | Who can see it | Blocked by |
|---|---|---|---|
| 1. Data running | Collection and models every day, and history building up (the lab's live record starts) | Nobody: no website yet | Your accounts (about an hour) |
| 2. Private site | The real site on the internet, behind one password | You, Janu and anyone you give the password to | Nothing beyond stage 1 |
| 3. Public site, Free tier | Anyone can open it; everyone sees Free | The public | The CSE's written permission (roadmap item 0) and the lawyer's review (roadmap item 4) |
| 4. Paid tiers | Pro and Plus for people who pay | Subscribers | Accounts and payments (Phase 4b; decision 0016), and prices |

Until stage 4, every visitor of the real site sees **Free**: tiers come from a subscription, and there are no
accounts yet. To show Pro and Plus to people before then, use the preview link, which shows every tier.

## Stage 1: start the data (your accounts; no website yet)

Follow `docs/phase3-4-verification.md` §6, parts A to C:

1. **Supabase Pro** (US$25 a month), Mumbai region. This is the database.
2. **Cloudflare R2** (free at this size) for the permanent archive of every file collected.
3. **Backblaze B2** (free at this size) for a second copy of it.
4. **Healthchecks.io** (free) for alarms. Create the nine checks the checklist lists.
5. **GitHub secrets.** Paste the keys into the repository's settings. Never paste them into a chat.
6. **"Migrate history".** Run it once. It takes about four hours, and it checks every row against your old tools.
7. **Switch on collection.** Set the variable `COLLECTION_ENABLED` to `true`. From the next scheduled time it
   collects three times each weekday, runs the models after each collection, runs a gap check, and backs up every
   night.

## Stage 2: the private site (about 30 minutes, after stage 1)

1. **The website's database login.** Set its password once, in Supabase's SQL editor (checklist step 9).
2. **Vercel Pro** (US$20 a month). Import the repository:
   - root folder `web`;
   - region **bom1 (Mumbai)**, next to the database.
3. **Settings on Vercel** (Production):
   - `DATABASE_URL`: Supabase's transaction pooler string, with the website's login;
   - `DATABASE_CA_CERT`: the certificate downloaded from Supabase;
   - `APP_ENV=production`;
   - `FEEDBACK_KEY_SECRET`: any long random text;
   - **`SITE_PASSWORD`**: the password for the private site. Every page then asks for it, and search engines are
     told not to list it. Built for this, and free; Vercel's own password feature costs US$20 a month more.
4. **Open the site and check it:**
   - the markets page shows the latest session;
   - the password prompt appears in a private window.
5. **A domain (optional).**
   - Buy one: a `.lk` name costs more than a `.com`.
   - Point it at Vercel, which shows the two DNS records to add and handles HTTPS by itself.

## Stage 3: open it to the public

1. **Before:**
   - the CSE's written permission for commercial use of its data (`config/sources.yaml`, `cse_api`);
   - the lawyer's view on everything listed in roadmap item 4:
     - the disclaimers and the wording;
     - directors' and shareholders' names;
     - the portfolio lab (decision 0027);
     - the two starting questions on amount and timeframe;
     - the sign-up form and data protection;
     - the name "Cheat codes".
2. **Then:** remove `SITE_PASSWORD` on Vercel and redeploy.
3. **Make the repository private** (decision 0012).
   - GitHub then stops pausing scheduled jobs after 60 quiet days.
   - The CI checks stay as they are.

## Stage 4: paid tiers (to be built)

- **Accounts** (Supabase Auth, log-in by e-mail link) and **payments** (PayHere; decision 0016).
- When they are built, the server reads each visitor's tier from their subscription. The tier check
  (`web/lib/entitlements.ts`) and the 57 leak tests already enforce Free, Pro and Plus.
- **Prices:** to decide (the owner, 2026-11-26: later).

## Running costs

The estimate in `docs/architecture.md` §13 is about **US$56–68 a month** at up to 500 users. It covers:

- Supabase Pro, plus an optional staging database;
- Vercel Pro;
- storage, alarms and a domain: a few dollars.

Legal advice and any CSE data licence are not included.

## Once it is running

- **Healthchecks e-mails you** if a job stops.
- **Every night:**
  - a backup is written to R2 and copied to B2;
  - the gap check reports any missing day.
- **Any change pushed to the repository goes live** on Vercel once its tests pass. The repository's main branch is
  the one Vercel and the scheduled jobs use.
