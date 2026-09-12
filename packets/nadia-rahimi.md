---
subject: nadia.rahimi@cal.example.com
name: Nadia Rahimi
team: billing
start_date: 2026-09-14
manager: sarah.chen@cal.example.com
generated: 2026-09-12T16:03:16Z
model: nvidia/Qwen3.6-35B-A3B-NVFP4   # on-box, no network
status: blocked-mfa
access:
  derived:
    - {group: db-staging-read, because: "packages/prisma/auto-migrations.ts:21 — connects to Postgres (DATABASE_URL)"}
    - {group: deploy-staging, because: "apps/api/v2/src/vercel-webhook.controller.e2e-spec.ts:18 — deploys the service (VERCEL_PROMOTE_WEBHOOK_SECRET)"}
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

> **BLOCKED — No Okta Verify factor enrolled. All grants blocked until enrollment completes.**

Starts 2026-09-14. Manager: sarah.chen@cal.example.com.

## Summary

| | |
|---|---|
| Cloning a teammate would grant | **9** grants, 0 justified |
| This packet proposes | **6** grants, all justified |
| Declined | **3** |

## What you're joining

You're joining the billing team, responsible for managing the financial aspects of cal.com. Key areas of focus include Stripe payment processing, Prisma database management, and API deployments. The team is led by Mandar Joshi, Benny Joo, and Romit, and is connected to various signals, including database migrations, deployment, error reporting, and Stripe API credential management.

## Who owns what

Most frequent authors in `packages/app-store/stripepayment`:

- Mandar Joshi
- Benny Joo
- Romit

## Running it locally

To run the billing service locally, you'll need to set up a development environment that mirrors the production setup, including the necessary dependencies and configurations. This is done to ensure that the service behaves as expected and to facilitate testing and debugging before deploying to production.

Environment variables this code actually reads (extracted from the repo, not generated):

- `DATABASE_URL`
- `INSIGHTS_DATABASE_URL`
- `SENTRY_DSN`
- `STRIPE_PRIVATE_KEY`
- `VERCEL_PROMOTE_WEBHOOK_SECRET`

## Access requested

**Derived from code** — the repository requires these:

- `db-staging-read` — packages/prisma/auto-migrations.ts:21 — connects to Postgres (DATABASE_URL)
    - also `packages/prisma/index.ts:87` (`INSIGHTS_DATABASE_URL`)
- `deploy-staging` — apps/api/v2/src/vercel-webhook.controller.e2e-spec.ts:18 — deploys the service (VERCEL_PROMOTE_WEBHOOK_SECRET)
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
