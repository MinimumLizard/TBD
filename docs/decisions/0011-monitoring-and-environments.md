# 0011 — Three environments; Healthchecks.io and a gap check for monitoring; Resend for email

- **Date:** 2026-10-11
- **Status:** Proposed

## Decision

- **Environments:** local (against a free dev Supabase project), staging (a second Pro-organisation project plus
  Vercel previews), production. Every pull request gets a preview deployment.
- **Secrets:** only in GitHub Actions secrets, Vercel environment variables and the founders' password manager.
  `.env.example` lists names only. Secret scanning runs in CI.
- **Monitoring:** Healthchecks.io dead-man's switches for every scheduled job (free: 20 checks; $5 Supporter if
  needed); a daily gap-check email only when something is wrong; an owner-only `/status` page.
- **Email:** Resend for login links and alerts. The free tier is 3,000/month (100/day); Pro is $20/month for 50,000.
  Supabase's built-in email is for development only, so production auth needs a real email provider.
- **Not yet:** a dedicated error tracker and analytics (architecture §18).
