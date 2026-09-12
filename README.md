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

---

## Running on the GB10

    ./run.sh                    # seeds Okta, starts mock Okta + Vault dev, checks inference
    python3 -m agent status     # which backend is answering

Inference resolves vLLM first (the 35B), Ollama second. Neither reachable = hard
error, never a silent cloud call.

## Demo commands

    python3 -m agent baseline billing            # the problem: 9 grants, 0 justified
    python3 -m agent scan     billing            # code-derived signals w/ file:line
    python3 -m agent peers    billing            # what the team actually uses
    python3 -m agent onboard  nadia billing      # gate BLOCKS - no MFA
    python3 -m agent enroll   nadia              # she completes Okta Verify
    python3 -m agent onboard  nadia billing      # now gate PASSES
    python3 -m agent crosscheck packets/nadia-rahimi.md
    python3 -m agent approve  packets/nadia-rahimi.md sarah.chen@cal.example.com
    python3 -m agent drift                       # the always-on scan
    python3 loop/daemon.py 900                   # the always-on loop
    python3 -m agent journal                     # what it did unprompted

Re-run `python3 services/mock_okta/seed.py` to reset between rehearsals.

## The new hire

`00uNEWHIRE01` — Nadia Rahimi, billing, starts Mon 14 Sep, STAGED, no groups,
no MFA enrolled (so the gate fires). Her manager is Sarah Chen, the same senior
engineer the baseline clones from.

## Wiring into OpenClaw (the part that makes it an agent)

OpenClaw connects Slack to the model. MCP connects the model to *our code*.
Without this the agent cannot call anything and Least is just a CLI.

    # register the tool server with the sandbox
    mcporter add least -- python3 /path/to/dell_nvidia_hackathon_project/mcp/server.py

    # load the behaviour
    #   mcp/AGENT.md  ->  OpenClaw agent system prompt

Verify the server independently of OpenClaw:

    printf '%s\n' \
      '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' \
      '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}' \
      | python3 mcp/server.py

Eleven tools: current_practice, scan_repo, peer_usage, check_mfa, build_packet,
onboarding_brief, find_gaps, access_drift, apply_access, enroll_mfa, find_user.

The ordering lives in `mcp/AGENT.md`. The refusals do not: `apply_access` routes
through `agent/execute.py` `approve()`, which re-reads the packet, re-runs the
MFA gate against the directory, refuses self-approval, and refuses an approver
the packet does not name. A model that ignores its prompt and calls
`apply_access` directly gets refused by the same code that refuses a human.

## Showing the work

    python3 -m agent onboard nadia billing -v

Prints what the agent is doing as it does it -- files opened, HTTP calls with
record counts and latency, each citation as it is found, each decline with its
reason, and the model's token rate. Trace goes to stderr, so the result still
pipes cleanly:

    python3 -m agent onboard nadia billing -v 2>trace.log

For the demo, run this in a second pane beside Slack. A result that appears
instantly with nothing in between looks hardcoded; the trace is what shows it
is not.

## Proving "acts on its own over time"

Start the loop and leave it running:

    python3 loop/daemon.py 30        # 30s ticks for a live demo

Then, on stage, change the world without touching the agent:

    python3 -m agent stage Marcus Webb billing

That writes a STAGED user into Okta, exactly as an HR system would. Nobody
tells the agent. On its next tick it notices, builds his packet, applies the
MFA gate, and journals what it did:

    PREPARE  Marcus Webb starts 2026-09-15 on billing — packet ready
             (5 proposed, 4 declined, gate BLOCK) marcus-webb.md

`python3 -m agent journal` prints everything it did while nobody was watching.
