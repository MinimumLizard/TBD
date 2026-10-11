# 0005 — Collectors run on GitHub Actions, built to survive its unreliable schedule

- **Date:** 2026-10-11
- **Status:** Proposed

## Context

All three tools run on GitHub Actions cron. The audit measured starts 5–6 hours late. On 2026-10-05 the CSE run never
started at all, and that session's turnover is permanently lost (audit F4, F6). The owner prefers boring, managed
services.

## Decision

Keep GitHub Actions as the job runner, but stop trusting it to be punctual:
1. **Several attempts per day** per source (architecture §6). Each is a no-op once the data is in.
2. **Collectors catch up.** They ask "which expected days are missing?", not "what is today?".
3. **An outside dead-man's switch** (Healthchecks.io). Every job pings when done; a missing ping emails the owner.
4. **A daily gap check** against trading calendars.
5. **Every step has a timeout**, so a stuck run can't block the queue (audit F15).

## Alternatives considered

- **Google Cloud Run Jobs + Cloud Scheduler (Mumbai):** punctual, and nearly free at this size. But it is a second
  cloud console, with IAM and container images for a non-engineer to manage. It is the upgrade path if, despite the
  above, a session is lost again.
- **Render cron jobs:** simple, but Render's pricing page did not show cron prices when checked. It adds a vendor for
  modest benefit.
- **Supabase scheduled functions:** they run Deno (TypeScript), not Python, and the models are Python.

## Cost

Private repos get 2,000 free Actions minutes/month on GitHub Free. Estimated use is about 1,500–2,500 minutes;
overage is $0.006/minute on Linux runners.

## Review trigger

If any trading session is lost to a scheduling failure after launch, move collectors to Cloud Run Jobs.
