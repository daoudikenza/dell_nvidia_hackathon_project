# Least — submission writeup

Dell x NVIDIA Hackathon, Cornell, 12 September 2026.

Covers rule 06: the stack declared, and every piece of content we did not author
cleared for use.

## What it does

When someone joins an engineering team, a manager decides what systems they need.
In practice they copy a senior teammate's permissions, because that is the only
answer available on a Monday morning. The new hire gets everything that person
accumulated over three years, including production database write access nobody
has used since 2024. This is how over-provisioning happens at every company, and
it is nobody's fault: the manager has no way to know which of those twelve groups
the code actually requires.

Least reads the codebase the new hire will work on, and the identity directory
they exist in, and works out what they actually need. Each proposal carries the
file and line number that requires it: `vault-billing-read` because
`packages/app-store/stripepayment/_metadata.ts:11` reads `STRIPE_PRIVATE_KEY`.
It says which groups it is declining and why. It says plainly which things it
cannot determine, because a Figma seat is not visible from either source.

It proposes. It does not grant. A human approves, and only then does anything
change in the directory, and the grant is recorded with the justification and the
approver against it.

It also runs the same analysis backwards over the existing organisation: which
grants has nobody used, who holds production access with no second factor
enrolled. That half is the larger market, because every company already has the
problem and no new hire is required to create it.

## What is deterministic and what is the model

The question we expect first, so the answer is the architecture.

**Code, not the model:** finding the environment variables a file reads and the
line they are on; mapping those to IAM groups; computing which groups a team
actually uses from directory system logs; the MFA gate; the approval control;
every refusal; the drift analysis. Anything that must be exact is a script.

**The model:** deciding which of those checks a plain-English request is asking
for, and writing the two paragraphs of onboarding prose around identifiers the
scanner found. It is never asked to name a file, a variable or a group, because
a 3B model asked to do that invented `VAULT_BILLING_READ_TOKEN`, which does not
exist in cal.com. The evaluation harness greps every `file:line` in the generated
prose back against the real repository for exactly this reason.

The model is the router, not the calculator.

## The stack

| Layer | What | Version |
|---|---|---|
| Reference stack and CLI | NVIDIA NemoClaw | ref `lkg`, cloned from `github.com/NVIDIA/NemoClaw.git` |
| Sandbox and gateway | NVIDIA OpenShell | 0.0.106, pinned minimum and maximum by NemoClaw |
| Agent runtime | OpenClaw (NemoClaw default) | as shipped at NemoClaw `lkg` |
| Inference server | vLLM, OpenAI-compatible, `localhost:8000/v1` | as shipped in the NemoClaw vLLM recipe image |
| Model | `nvidia/Qwen3.6-35B-A3B-NVFP4` | 23.5 GB, NVFP4 |
| Fallback model | `nvidia/NVIDIA-Nemotron-3-Nano-4B-FP8` | 5.3 GB |
| Hardware | Dell Pro Max with GB10, aarch64, 128 GB unified memory | loaned for the event |

NemoClaw and OpenShell are not vendored into this repository. They are installed
on the box by NemoClaw's own installer; `SETUP.md` has the procedure.

Python libraries, all from PyPI, all permissively licensed:

| Library | Version | Used for |
|---|---|---|
| fastapi | 0.141.1 | the mock Okta HTTP server |
| uvicorn | 0.52.4 | serving it |
| pydantic | 2.13.5 | request bodies in that server (via fastapi) |
| PyYAML | 6.0.3 | reading `config.yaml` |
| slack_bolt | 1.30.0 | the Slack bot, Socket Mode |
| slack_sdk | 3.44.1 | Slack Web API calls |
| pytest | 9.1.1 | the test suite (development only) |

The agent itself imports only the standard library: `urllib` for both the
directory and the inference endpoint, `json`, `re`, `subprocess`, `pathlib`,
`hashlib`. The MCP server has no dependencies at all, so it runs inside the
OpenShell sandbox without installing anything.

## Local-first

Rule 02: no remote LLM or API call in the agent's runtime path.

Inference is vLLM on `localhost:8000`, with Ollama on `localhost:11434` as a
fallback. Both are loopback. The agent's inference client
(`agent/llm.py`) builds its URL opener with an explicit empty `ProxyHandler`, so
a host with `http_proxy` set cannot silently route localhost traffic outward.

Slack is a message transport. It carries the manager's question and the agent's
answer. It never carries a prompt to a model and never returns a completion. If
Slack is unreachable the product still works; if vLLM is unreachable it does not.
That is the distinction rule 02 is about.

This is checked rather than asserted:

    python3 -m agent local

prints the model id read back from the inference endpoint's own `/models`
response, `nvidia-smi`, and every established outbound connection held by the
agent's processes, classified as loopback, allowed transport, or a finding. The
same output is available in the channel as `@Least status`.

Why it has to be local: the two inputs are a private codebase and a corporate
identity directory. Both are exactly the material a company will not send to a
third-party API, which is precisely why this workflow is still done by hand.

## Data provenance

**The codebase** is [cal.com](https://github.com/calcom/cal.com), cloned at depth
100 from the public repository. It is MIT licensed (`Copyright (c) 2020-present
Cal.com, Inc.`), which permits this use. We chose a real codebase rather than a
fixture because the citations have to point at real files for the demo to mean
anything. `./setup-demo-repo.sh` fetches it; it is not vendored here.

**The identity directory is synthetic. We generated it.** No real person, no real
company, no real credential appears anywhere in it.
`services/mock_okta/seed.py` is the generator and is the whole provenance: 40
engineers with names assembled from a fixed first-name and surname list, one
service account, one new hire, spread across five teams, with group memberships
and usage logs derived from a seeded `random` sequence. Email addresses are all
`@cal.example.com`, a reserved example domain that cannot receive mail.

The over-provisioning in it is planted deliberately, and `seed.py` prints what it
planted when it runs, so the findings the agent reports can be checked against
what was put there. The planted problems are ordinary ones: three people with
production database write access unused for 210 days, two who changed teams and
kept the old group, a service account with full infrastructure admin dormant for
980 days, one person with vault admin where read would do, three people with no
second factor enrolled.

Group ids and user ids are sha256-derived, so re-running the generator produces a
byte-identical directory on any machine.

**The mock Okta server** (`services/mock_okta/app.py`) implements the subset of
the real Okta Management API that the agent uses, with the same paths, methods
and JSON shapes. It deliberately exposes no "find unused access" endpoint,
because real Okta has none; deriving that from raw memberships and system logs is
the product. Pointing the agent at a real tenant is a base URL change and an auth
header.

## How to run it

Assuming a GB10 and nothing else.

```bash
# 1. The stack, per SETUP.md: NemoClaw's installer, then bring up vLLM.
curl -fsSL https://www.nvidia.com/nemoclaw.sh | sh
#    Verify before going further:
curl localhost:8000/v1/models

# 2. This repository.
git clone <this repo> && cd dell_nvidia_hackathon_project
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

# 3. The demo codebase (needs network once; a few hundred MB).
./setup-demo-repo.sh

# 4. Point config.yaml at whatever vLLM is actually serving.
./fix-model.sh http://localhost:8000/v1

# 5. Seed the directory and start everything.
./run.sh

# 6. Drive it.
python3 -m agent status                                      # what is answering
python3 -m agent local                                       # the local-first evidence
python3 -m agent onboard nadia.rahimi@cal.example.com billing
python3 -m agent approve packets/nadia-rahimi.md sarah.chen@cal.example.com
python3 -m agent drift

# 7. The evaluation table.
.venv/bin/python evals/run.py
```

Slack is optional and is not the demo path. `SLACK.md` has the setup. Tokens go
in a gitignored `.env`; none are committed.

## How we evaluated it

`.venv/bin/python evals/run.py` runs 22 cases headlessly and prints a pass table.
On the development host it reports 22/22 with 2 skipped.

The three groups that matter:

- **Citations.** Every `file:line` in every generated packet, across all five
  teams, resolved against the real cal.com checkout and required to name a file
  that exists with at least that many lines. The model-written prose is checked
  the same way, rather than trusted to the system prompt that tells it not to
  invent identifiers.
- **Refusals.** The approval control against a live directory: unenrolled
  subject, self-approval, a bystander, a path escaping the packets directory, and
  the named manager succeeding. Each asserts on what reached the directory, not
  on what was printed.
- **Parity.** The same request through Slack and through the terminal produces an
  identical access block, because the terminal is the demo path and Slack is a
  convenience.

A case that cannot run reports SKIP and why. It never reports PASS.

Separately, `pytest` runs 37 unit tests, every one of which runs with the
directory stopped. We verified that by stopping it. They cover the MFA gate's
failure taxonomy, the approval control, frontmatter injection into the approval
decision, and seed reproducibility across processes.

## What is real and what is not

Named before a judge finds them.

- **The directory is synthetic.** The Okta API surface is faithful and the agent
  code would run against a real tenant unchanged for the onboarding half. The
  drift half would not: it reads a `_sensitivity` field that we invented and real
  Okta has no equivalent of. That belongs in a policy file owned by a security
  team, and it is not there yet.
- **Five places still read `org.json` off disk** instead of going through the
  Okta client, so those paths would need rewriting against a real tenant.
- **The access request is drafted, not filed.** Approving provisions the groups
  in the directory for real, and prepares a branch and commit for the audit
  trail, but filing it is a separate `--live` flag that we do not run during a
  demo.
- **The packet is the authority at approval time.** Someone with write access to
  this repository could edit a packet's frontmatter between generation and
  approval and the agent would apply what it reads. Closing that needs the packet
  signed when it is generated.
- **Vault policy generation runs in dry-run** unless a Vault binary is present.
- **The Slack bot's handlers are not covered by tests.** `slackbot/core.py` is
  written with no Slack in it precisely so every decision path can be exercised
  offline, and it is. The thin Slack plumbing in `slackbot/bot.py` is not.

## Licence

This repository is MIT licensed. See `LICENSE`.
