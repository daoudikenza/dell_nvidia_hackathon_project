---
subject: nadia.rahimi@cal.example.com
name: Nadia Rahimi
team: billing
start_date: 2026-09-14
manager: sarah.chen@cal.example.com
generated: 2026-09-12T18:16:08Z
model: qwen7b   # on-box, no network
status: awaiting-approval
access:
  derived:
    - {group: db-staging-read, because: "packages/prisma/index.ts:10 — connects to Postgres (DATABASE_URL)"}
    - {group: deploy-staging, because: "apps/api/v2/src/vercel-webhook.guard.ts:12 — deploys the service (VERCEL_PROMOTE_WEBHOOK_SECRET)"}
    - {group: sentry-eng, because: "apps/api/v2/src/instrument.ts:5 — reports errors to Sentry (SENTRY_DSN)"}
    - {group: vault-billing-read, because: "packages/app-store/stripepayment/_metadata.ts:11 — reads Stripe API credentials (STRIPE_PRIVATE_KEY)"}
  conventional:
    - {group: eng-billing, because: "8/9 peers active in last 30d"}
    - {group: grafana-billing, because: "7/9 peers active in last 30d"}
  declined:
    - {group: db-prod-write, because: "production-level access with no code path requiring it"}
    - {group: deploy-prod, because: "production-level access with no code path requiring it"}
    - {group: jira-eng, because: "no code path requires it and fewer than 75% of the team uses it"}
---

# Nadia Rahimi — billing team

Starts 2026-09-14. Manager: sarah.chen@cal.example.com.

## Summary

| | |
|---|---|
| Cloning a teammate would grant | **9** grants, 0 justified |
| This packet proposes | **6** grants, all justified |
| Declined | **3** |

## What you're joining

You are joining the billing team of the cal.com codebase, where you will work on critical components such as Stripe payment processing and database interactions. Your contributions will involve paths like `packages/app-store/stripepayment` and `packages/prisma`, with responsibilities including database reads and error reporting via Sentry. Notable files include `packages/prisma/index.ts` for database connections and `packages/app-store/stripepayment/_metadata.ts` for handling Stripe API credentials.

## Who owns what

Most frequent authors in `packages/app-store/stripepayment`:

- Mandar Joshi
- Benny Joo

## Running it locally

The developer will set up the local environment to run the billing API and its associated services, ensuring they can test and debug the Stripe payment integration and other features locally before deploying changes to the staging environment. This setup is crucial for validating that the database connections, error reporting, and deployment processes function correctly in a controlled local setting.

Environment variables this code actually reads (extracted from the repo, not generated):

- `DATABASE_URL`
- `INSIGHTS_DATABASE_URL`
- `SENTRY_DSN`
- `STRIPE_PRIVATE_KEY`
- `VERCEL_PROMOTE_WEBHOOK_SECRET`

## Access requested

**Derived from code** — the repository requires these:

- `db-staging-read` — packages/prisma/index.ts:10 — connects to Postgres (DATABASE_URL)
    - also `packages/prisma/index.ts:87` (`INSIGHTS_DATABASE_URL`)
- `deploy-staging` — apps/api/v2/src/vercel-webhook.guard.ts:12 — deploys the service (VERCEL_PROMOTE_WEBHOOK_SECRET)
- `sentry-eng` — apps/api/v2/src/instrument.ts:5 — reports errors to Sentry (SENTRY_DSN)
- `vault-billing-read` — packages/app-store/stripepayment/_metadata.ts:11 — reads Stripe API credentials (STRIPE_PRIVATE_KEY)

**Team convention** — not in the code, but the team actually uses these:

- `eng-billing` — 8/9 peers active in last 30d
- `grafana-billing` — 7/9 peers active in last 30d

**Declined** — a teammate has these; nothing justifies giving them to a new hire:

- ~~`db-prod-write`~~ — production-level access with no code path requiring it
- ~~`deploy-prod`~~ — production-level access with no code path requiring it
- ~~`jira-eng`~~ — no code path requires it and fewer than 75% of the team uses it

**Unknown** — no signal in code or peer usage. Manager decides:

- Salesforce, Figma, or anything provisioned outside the identity provider.
