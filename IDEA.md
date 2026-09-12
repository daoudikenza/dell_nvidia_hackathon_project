# Least — one-page brief

**Least is an always-on agent that reads your codebase and your IAM directory
and works out who should have access to what — with a justification for every
grant, tied to the line of code that requires it. It proposes; a human approves.**

---

## The problem

Two things happen when an engineer joins a team.

**They wait.** Two to four days of Jira tickets to IT before they can run
anything locally.

**Then they get too much.** Nobody has time to work out what this specific
person actually needs, so they get cloned from a teammate. That over-permission
is permanent — nothing revokes it. Access only ever accumulates.

The second one is the expensive problem. When an account is compromised, what
matters is what that account could reach. Over-provisioning is the single
biggest contributor to blast radius, and demonstrating least privilege is a hard
requirement under SOC 2 and ISO 27001. Most companies satisfy it with a
spreadsheet and a quarterly scramble.

## The insight

**Access requirements are derivable from code.** If someone is joining to work
on `services/billing`, the repo already tells you what they need:

    services/billing/payment_client.ts:34 reads vault:secret/billing/stripe-test
    -> needs: vault-billing-read
    -> does NOT need: vault-billing-admin (no code path touches live keys)

So the agent never asks "what should Sarah get?" It reads the code she will
actually work on and proposes the minimum, citing its reasoning per grant.

## Why this cannot run in the cloud

To do this the agent must read the private codebase, the full IAM graph, and
the secrets topology. That combination is precisely the blueprint an attacker
would want. No security team signs off on sending it to a third-party API.

Running locally is not us satisfying a hackathon rule. It is the only way this
product is sellable at all.

## What already works

- Mock Okta serving the real Management API surface — users, groups,
  memberships, Okta Verify factors, system log. No analysis endpoints, because
  real Okta has none: deriving unused access from raw logs is the product.
  Agent code written against it runs against a real tenant unchanged.
- A seeded 41-person org with realistic rot: dormant production DB write, a CI
  service account holding infra-admin for 980 days, vault admin where read would
  do, stale groups after team moves, users without MFA.
- A deterministic drift detector that joins grants against usage and ranks by
  blast radius. **It finds that 46% of production-level access is unused.**

## The demo

1. "Sarah joins the billing team." Agent reads the repo, proposes 6 grants and
   explicitly declines 3, with a reason for each.
2. She has no Okta Verify enrolled. The agent refuses to proceed. Gate, not a
   warning.
3. Manager approves in Slack. Only then does anything execute.
4. Nightly drift scan runs: finds the CI service account dormant since 2023 and
   drafts the revocation.

## What we want your read on

1. **Is code-derived access credible to a real security team, or is the mapping
   from imports to permissions too naive to trust?** This is our biggest
   technical risk and we would rather hear it now.
2. **Which is the better wedge — onboarding, or drift detection?** Onboarding is
   the nicer story. Drift is the recurring pain and the bigger market. We are
   building both but can only demo one well.
3. **Who actually buys this?** Security, IT ops, or eng leadership? They have
   very different objections.
4. **What would stop you trusting an agent anywhere near IAM?** We made it
   propose-only for exactly this reason — is that enough, or does a
   human-in-the-loop kill the time savings that justify it?

## Scope guardrails for today

Building, in order, willing to stop after 3:
1. repo scanner (extract access signals from code)
2. proposal generator with per-grant justification
3. Slack approval -> execute against mock Okta + dev Vault
4. nightly drift loop
5. *stretch:* onboarding doc + narrated video

Video is the flashiest and least important to the score. It only happens if
everything above is solid.
