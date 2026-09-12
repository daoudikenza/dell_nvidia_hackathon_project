# Least — least-privilege access, derived from your code

An always-on agent that reads a codebase and an IAM directory *locally*, and:

1. **Onboarding** — given "Sarah, billing team", proposes a minimal access set,
   justifying every grant against the file that requires it.
2. **Drift** — runs nightly, finds access nobody uses, drafts revocations.
3. **Human-in-the-loop** — proposes only. A manager approves in Slack; the agent
   never grants access on its own.

## Why local-only

To do this the agent reads the private codebase, the IAM graph, and the secrets
topology. That combination is the blueprint an attacker would want. No security
team sends it to a third-party API — so inference runs on-box via NemoClaw +
OpenClaw + OpenShell with vLLM. Local isn't a constraint here, it's the premise.

## Architecture

    OpenClaw agent (in OpenShell sandbox)
        |-- vLLM / Qwen3.6-35B      reasoning + justification only
        |-- repo scanner            deterministic: vault paths, envs, CI roles
        |-- mock-okta  :8081        real Okta API shapes
        |-- vault dev  :8200        real HCL policies
        `-- slack                   approval gate

Deterministic code does the extraction. The model does the reasoning. Never ask
the LLM to do what grep does better.

## Run

    python services/mock_okta/seed.py                       # seed the org
    uvicorn services.mock_okta.app:app --port 8081          # Okta API
    python agent/drift.py                                   # drift report

## Seeded findings

The org is seeded with realistic over-provisioning so the agent has real
findings. 46% of production-level grants are unused.
