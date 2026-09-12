# Least — full team context

Everything a teammate needs: what we are building, why, how it works, what the
demo is, what changed along the way, and every issue we hit. Read Part 1 before
you pitch. Read Part 3 before you debug.

Numbers below were re-verified against the seeded org on Sep 12.

---

# Part 1 — What we are building

## One line

**An always-on agent that reads a team's codebase and identity directory and
tells a manager exactly what a new hire needs — which IAM groups to join, which
accounts someone has to create, and how to set up — with a reason for every
grant tied to the line of code that requires it. It proposes; a human approves;
then it requests the access.**

## The problem

Some teams have clear onboarding docs. Most do not. On those teams, when an
engineer joins:

**They wait.** Two to four days of tickets to IT before they can run anything
locally, because nobody wrote down what they need.

**Then they get too much.** Nobody has time to work out what this specific
person needs, so the manager says *"give her what Sarah has."* The new hire
inherits everything that teammate accumulated over years — including production
access nobody can explain.

**And nobody knows the non-IAM half.** Even when groups get sorted, the new hire
still doesn't know they need a Stripe dashboard invite, or that the billing lead
is the one who sends it. That knowledge lives in someone's head.

The over-provisioning is the expensive part. It is permanent — nothing revokes
it — so access only accumulates. When an account is compromised, what matters is
what it could reach. Demonstrating least privilege is a hard requirement under
SOC 2 and ISO 27001, and most companies satisfy it with a spreadsheet and a
quarterly scramble.

## The insight

**Access requirements are derivable from code.** If someone joins to work on
the billing integration, the repository already says what they need:

    packages/app-store/stripepayment/_metadata.ts:11
        process.env.STRIPE_PRIVATE_KEY
    -> needs vault-billing-read          (grant)
    -> does NOT need vault-billing-admin (decline — nothing touches live keys)
    -> needs a Stripe Dashboard account  (a human must invite — ask billing lead)

That citation is real — open the file and it is on line 11.

## Three different things, deliberately kept separate

Conflating these is exactly why existing onboarding docs are useless:

| Kind | Example | Who does it |
|---|---|---|
| **IAM group** | `vault-billing-read` | the agent, after approval |
| **Account to create** | Stripe Dashboard, Sentry, Vercel | a human — doesn't exist in Okta |
| **Setup step** | point `DATABASE_URL` at staging | the new hire |

## Why this cannot run in the cloud

To do this the agent reads the private codebase, the full IAM graph, and the
secrets topology together. That combination is precisely the blueprint an
attacker wants. No security team sends it to a third-party API.

**Running locally is not us satisfying a hackathon rule. It is the only way this
product is sellable at all.** Lead the pitch with that — it turns the 30%
local-first criterion from a box-tick into the central argument.

## Not all access is in the code — and we say so

Roughly half of an engineer's real access is visible in code. The rest isn't.
Every proposed grant carries a provenance tier:

| Tier | Basis |
|---|---|
| **DERIVED** | code cites it — file and line |
| **CONVENTIONAL** | ≥75% of the team actively *uses* it (usage, not grants — so existing over-provisioning is not copied) |
| **DECLINED** | a teammate has it; nothing justifies it for a new hire |
| **UNKNOWN** | no signal — manager decides (Salesforce, Figma, anything outside Okta) |

The UNKNOWN tier is what makes the rest credible. We don't claim completeness.

---

# Part 2 — How it works

## What is running on the GB10

| Process | Port | What it is |
|---|---|---|
| llama-server | 8081 | the brain — `qwen2.5-7b`, alias `qwen7b`, needs API key |
| mock Okta | 8091 | the company directory |
| OpenClaw | — | carries messages between Slack/TUI and the model |
| MCP server | — | exposes our 11 tools to the model |
| daemon | — | the always-on loop |

## What makes it an agent rather than a script

The model never touches anything. It gets a menu of tools and decides which to
call, reads the result, decides again. Nobody scripts the order.

    manager in Slack: "I have a new hire joining billing, what do they need?"
       -> OpenClaw hands the text to the model
       -> model calls onboarding_brief
            -> find the person in Okta
            -> scan cal.com for access signals        (reads files on disk)
            -> check what the team actually uses       (Okta usage logs)
            -> compute what cloning a teammate gives   (the baseline)
            -> check MFA
            -> write the packet
       -> model posts the brief back to Slack
       -> manager replies "approve"
       -> model calls apply_access -> groups provisioned in Okta, each carrying
          its justification and approver

## What makes it always-on

`loop/daemon.py` runs on a timer and **acts when the world changes**, without
being asked:

- **HR stages a new hire** -> builds their packet before anyone requests it
- **Production access sits unused** -> records it, drafts the revocation
- **cal.com moves** -> regenerates every affected packet

It remembers what it already reported, so quiet ticks stay quiet.
`agent journal` shows everything it did while nobody watched.

**Live proof for the demo:** `agent stage Marcus Webb billing` writes a new
person into Okta the way an HR system would. Nobody tells the agent. On the next
tick it prepares his packet unprompted.

## The deliverable — the packet

`packets/<name>.md` is four documents in one file, which is why they can't drift
apart:

- **frontmatter** — machine-readable; `approve` executes from it
- **onboarding guide** — who owns what (git history), setup, env vars — for the new hire
- **access request** — every grant with its citation — for the manager
- **the committed file** — audit evidence of who got what, why, and who approved

The **Declined** section is the product. Every company can list what someone was
granted. None can show a written record of what was refused and why.

## Where the model is — and isn't

**Not** in scanning, peer math, drift, MFA, or env var extraction. That is grep
and set operations; determinism demos better and cannot hallucinate a file path.
**Yes** in the onboarding prose and in choosing which tools to call.

If a judge asks: *"we use the model where judgment is needed and code where it
isn't."*

## What is real, what is simulated

| Real | Simulated |
|---|---|
| cal.com — 7,702-file production monorepo | Okta (real Management API shapes) |
| the scanner and every citation | the 41-person org |
| local inference, zero network calls | Vault (dry-run — binary not present) |
| Slack (once wired) | |

*"The only thing we simulated is the identity directory — and we simulated its
actual API, so this code runs against a real Okta tenant unchanged."*

---

# Part 3 — The seeded org and the demo numbers

## The people

| Who | Role in the demo |
|---|---|
| **Nadia Rahimi** | the new hire. billing, STAGED, 0 groups, starts Mon 14 Sep |
| **Sarah Chen** | Nadia's manager, and the senior teammate who gets cloned |
| **Marcus Webb** | created live with `agent stage` to prove autonomy |

## The numbers (verified)

- Cloning Sarah Chen gives **9 grants**, including `db-prod-write` and `deploy-prod`, **0 justified**
- The agent proposes **6**, all justified, and declines **3** — both production grants plus `jira-eng`
- Accounts someone must create: **Stripe Dashboard, Sentry, Vercel**
- **46%** of production-level access in the org is granted and never used (6 of 13)

## Drift findings

| Group | Holder | Team |
|---|---|---|
| `infra-admin` | ci runner (service account) | infra |
| `deploy-prod` | ci runner (service account) | infra |
| `vault-billing-admin` | Priya Novak | platform |
| `db-prod-write` | Tom Silva | app-store |
| `db-prod-write` | Yuki Yamada | bookings |
| `db-prod-write` | Ida Moreau | platform |

The org also contains legitimate, actively-used production access, so findings
read as discovered rather than planted.

## The strongest finding — production access with no MFA

| Person | Tenure | Holds | MFA |
|---|---|---|---|
| **Sarah Chen** | 1349 days | `db-prod-write`, `deploy-prod` | never enrolled |
| ci runner | 980 days | `infra-admin`, `deploy-prod` | never enrolled |
| Liam Larsson | 907 days | `db-prod-read` | never enrolled |
| Tess Andersen | 754 days | `pagerduty-oncall`, `eng-infra` | never enrolled |

**The line:** *"The person whose permissions we clone onto every new hire has
production database write and has never enrolled a second factor. One phished
password and that is the blast radius."*

## The demo

1. **Journal already shows overnight work** — always-on before you speak
2. **Manager in Slack:** *"@Least I have a new hire joining billing, what do they need?"*
3. **The brief lands** — 9 today vs 6 proposed, citations, accounts to create with who to ask, setup steps
4. **Open `_metadata.ts:11`** — the citation is real
5. **Declined section** — both production grants refused, with reasons
6. **The MFA finding** — Sarah Chen
7. **`agent stage Marcus Webb billing`** — agent prepares his packet unprompted, 30s later
8. **Manager replies "approve"** — Okta goes 0 -> 6 groups, each carrying its reason and approver

Close: *"We don't claim to derive all access. We derive what's in the code,
justify it in writing, and flag the rest for a human. That's strictly better
than cloning a teammate — which is what happens today."*

If Slack won't cooperate, run the same sequence in the OpenClaw TUI. Same agent,
same tools, no tokens, no internet.

## Judging, and where each point lands

| Criterion | Weight | Our evidence |
|---|---|---|
| Local-first + always-on | 30% | on-box inference; daemon acts unprompted; `stage` proves it live |
| Business value | 30% | 9->6 grants; prod access declined; audit evidence generated |
| Demo + pitch | 30% | Slack flow; real citation on screen; the Sarah Chen finding |
| Technical execution | 10% | NemoClaw + OpenClaw + OpenShell; MCP tools; doesn't break |

---

# Part 4 — What changed from the original brief

The one-page mentor brief is out of date in ways that would hurt on stage.
**Do not quote it — use this file.**

| The brief said | Reality now | Why it changed |
|---|---|---|
| `services/billing/payment_client.ts:34` | **`packages/app-store/stripepayment/_metadata.ts:11`** | the brief's path was illustrative and **does not exist in cal.com**. Quote it and a judge who checks finds nothing |
| "Sarah joins billing" | **Nadia Rahimi** joins; Sarah Chen is her manager and the clone donor | name collision in the seed |
| Qwen3.6-35B | **qwen2.5-7b** (`qwen7b`) via llama.cpp | the 7B came up first; the 35B weights are on disk if there is time |
| MFA gate on the new hire is the insight | **the inverse is**: existing staff with prod access and no MFA | a new hire lacking MFA is a tautology, not a finding |
| least-privilege tool | onboarding: **groups + accounts + setup**, with least privilege as the method | the actual problem is teams with no onboarding docs |
| manager approves in Slack | Slack is being wired now — see `SLACK.md` | |
| Vault dev | dry-run | `vault` binary not present on the box |

## Open questions we took to mentors

1. Is code-derived access credible to a real security team, or too naive?
2. Onboarding or drift detection — which is the better wedge?
3. Who buys this — security, IT ops, or engineering leadership?
4. Is propose-only enough, or does the human in the loop kill the time savings?

---

# Part 5 — Issues we hit, and what fixed them

Roughly in the order we hit them.


---

## Environment — the GB10

### `error: externally-managed-environment` on pip install
Ubuntu (PEP 668) refuses `pip3 install` into system Python.
**Fix:** use a venv.

    python3 -m venv .venv
    .venv/bin/pip install -r requirements.txt

`run.sh` and `setup-demo-repo.sh` now find `.venv` themselves — no need to
activate. For bare commands use `.venv/bin/python -m agent ...`.

### mcporter can't find our modules
`mcporter` spawns the MCP server as its own process and reaches for **system**
python, which has none of our packages. Fails with missing modules and nothing
pointing back at the venv.
**Fix:** register with the venv interpreter explicitly.

    mcporter add least -- $PWD/.venv/bin/python $PWD/mcp/server.py

### Port 8081 already in use
The llama server owns 8081. Our mock Okta wanted it too.
**Fix:** Okta moved to **8091**. The port now comes from `config.yaml` alone —
`run.sh` reads it and warns if something else holds it.

| Port | Service |
|---|---|
| 8081 | llama-server (the model) |
| 8091 | mock Okta |
| 8200 | Vault dev |

### `[SSL: WRONG_VERSION_NUMBER]` / handshake timeouts
We used `https://localhost:8081`. The llama server logs
`listening on http://0.0.0.0:8081` — it speaks **plain HTTP**. Pointing https at
it makes Python attempt a TLS handshake that never completes.
**Fix:** `http://` everywhere for local services. `fix-model.sh` now rewrites
`https://localhost` → `http://` automatically.

We initially misdiagnosed this as a proxy problem. It wasn't — but the proxy
bypass we added is still correct and worth keeping: if the host has
`http_proxy` set, urllib routes even localhost through it.

### Inference "NONE REACHABLE" with no explanation
Three possible causes (wrong port, wrong model name, wrong scheme) and no way
to tell them apart.
**Fix:** `agent status` now prints the error per backend and probes each
endpoint for `/models`, `/v1/models`, `/api/tags`, `/health`.

### The inference server needs an API key
Started with `--api-key local-hackathon-key`. Our client sent no
`Authorization` header, so even a correct URL was rejected.
**Fix:** `api_key` in `config.yaml`, sent as `Bearer`. Pass it to the helper:

    ./fix-model.sh http://localhost:8081/v1 local-hackathon-key

### The model name is not the file name
llama.cpp registers whatever `--alias` says (`qwen7b`), not the HuggingFace repo
id. A mismatched name returns an error that reads as "server down".
**Fix:** `fix-model.sh` reads `/v1/models` and writes the real id.

### cal.com wasn't on the USB
**cal.com is demo data, not part of the NemoClaw/OpenClaw/OpenShell stack** —
whoever carried the stack had no reason to bring it.
**Fix:** `./setup-demo-repo.sh` clones it and verifies the scanner finds signals.
Clones at `--depth 100` deliberately: "Who owns what" comes from `git log`, so a
`--depth 1` clone yields an empty section **with no error**.

---

## Bugs we shipped and then fixed

### `fix-model.sh` wrote invalid YAML
Closing brace sat outside an f-string, so `}}` was written literally and
`config.yaml` became unparseable — breaking every command downstream.
**Fix:** generated line is now round-tripped through `yaml.safe_load` before the
script ships. **Lesson: never generate config without parsing it back.**

### Guessed repo paths that don't exist
`packages/features/ee/billing` was assumed. cal.com's Stripe code actually lives
in `packages/app-store/stripepayment`.
**Fix:** `TEAM_PATHS` verified against the real tree; `setup-demo-repo.sh` fails
loudly if the scanner finds nothing.

### `docker manifest inspect` lies about ghcr.io
Returns "denied" for images that `docker pull` fetches fine — it needs an auth
token even for public images. We concluded the whole stack wasn't downloadable.
It was.
**Fix:** test image availability with an actual `docker pull`.

### Cross-check reported false positives
It scanned the packet's own frontmatter and access list, so every declined group
came back as a "gap".
**Fix:** `prose_only()` — the knowledge sections only.

### The packet claimed a model that never ran
Frontmatter printed the *configured* primary, so a packet built with `--no-llm`
or via the Ollama fallback still said `Qwen3.6-35B`. Unacceptable in a document
whose purpose is being trustworthy.
**Fix:** records the model that actually answered.

---

## Runtime and concurrency

### `tick failed: expecting ',' delimiter line 51991`
The daemon polls `org.json` while the API server rewrites it. `write_text()`
truncates before writing, so a read landing in that gap sees half a document.
**Fix:** writes go to a temp file and `os.replace()` into position — atomic. The
daemon also retries a decode failure.
**Only appears once something genuinely runs continuously.**

### Merge conflict on every `git pull`
`packets/*.md` is rewritten by every `onboard` run and was tracked.
**Fix:** gitignored. `approve` uses `git add -f` so the packet a human actually
signed off on still enters the record — arguably more correct.

### Six identical `GET /api/v1/groups` per packet
`name_by_gid` refetched once per membership. Found immediately after adding
`-v`.
**Fix:** `groups()` cached per process. **Making work visible found a bug in
minutes.**

### A one-character typo produced a raw traceback
`00oNEWHIRE01` vs `00uNEWHIRE01` → urllib 404 stack trace.
**Fix:** `okta.resolve()` takes an id, an email, or part of a name. Use
`agent onboard nadia billing` — never type the id on stage.

---

## Model behaviour

### The model invented environment variables
llama3.2 produced `VAULT_BILLING_READ_TOKEN` and `VAULT_BILLING_WRITE_TOKEN`.
Neither exists in cal.com. A judge who greps a cited variable and finds nothing
ends the demo.
**Fix:** the model no longer emits identifiers at all. Env vars render from
scanner data; the model writes only the prose around them.

**Watch for this with qwen7b.** Smaller model, same failure mode. Rule 1 in
`AGENTS.md` exists because of it.

---

## Design problems we caught before the judges did

### The baseline was too clever
Computing the team median gave 3 grants — an unimpressive delta. Managers don't
compute medians; they say *"give her what Sarah has."*
**Fix:** clone one senior teammate. Now 9 grants including `db-prod-write` and
`deploy-prod`, and that inheritance IS the problem we're solving.

### Everyone used everything
The seed logged usage for every grant, so almost nothing looked stale.
**Fix:** tools handed out by default (Figma, analytics, prod-read) now go
largely unused — the ordinary half of over-provisioning.

### 100% of production access was unused
Every prod grant in the org was a planted finding, which reads as rigged.
**Fix:** seeded legitimate, actively-used production access alongside it. Now
46% — credible and still damning.

### The MFA gate on a new hire is a tautology
"The new person doesn't have MFA yet" — obviously. Not a finding.
**Fix:** the inverse. Drift now surfaces **existing staff with production access
and no MFA** — Sarah Chen, 1349 days, `db-prod-write`, never enrolled. She is
also the person every new hire gets cloned from. *That* is a finding.

### Name collision
The seed's senior donor was also called Sarah Chen, same as our demo new hire.
**Fix:** new hire is **Nadia Rahimi**; Sarah Chen is her manager — which reads
better anyway.

---

## Still open

- **vLLM path never exercised** — we run llama.cpp. The code path is
  OpenAI-shaped and should work, but it is untested.
- **Running qwen2.5-7b, not the 35B.** Citations are unaffected (they come from
  the scanner). Tool selection and prose quality are.
- **OpenClaw + Slack not wired.** Tools are ready; the wiring is not.
- **How OpenClaw loads `AGENTS.md` is unconfirmed** — see `mcp/README.md`. The
  critical rules are in the MCP tool descriptions regardless, and the MFA gate
  is enforced in `agent/gate.py` no matter what the model decides.
- **`open_pr` is dry-run.** The `gh` calls have never fired.
- Everything was developed on macOS ARM, not aarch64 Linux.

---

## Two habits that paid off

**Verify the citation, don't trust it.** After any change:

    .venv/bin/python -m agent onboard nadia billing
    grep -n "STRIPE_PRIVATE_KEY" ~/hack-stage/demo-repos/cal.com/packages/app-store/stripepayment/_metadata.ts

**Run with `-v`.** It shows files opened, HTTP calls with latency, each citation
as it is found, and the model's token rate. It proves the demo isn't hardcoded,
and it found the duplicate-query bug on its first run.
