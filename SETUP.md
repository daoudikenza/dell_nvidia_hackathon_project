# Running Least on the GB10

Three phases. Each one is verifiable on its own, so when something breaks you
know exactly where. Do not skip ahead — Phase 1 rules out half the possible
problems in five minutes.

---

## Phase 1 — Prove the pipeline works

No Slack, no OpenClaw, no agent. Just the code.

    git clone https://github.com/daoudikenza/dell_nvidia_hackathon_project.git
    cd dell_nvidia_hackathon_project
    python3 -m venv .venv
    .venv/bin/pip install -r requirements.txt

Ubuntu refuses `pip3 install` into system python (PEP 668:
"externally-managed-environment"), so use a venv. `run.sh` and
`setup-demo-repo.sh` find `.venv` on their own - you do not have to activate it.

For bare `python3 -m agent ...` commands either activate it:

    source .venv/bin/activate

or call the interpreter directly: `.venv/bin/python -m agent status`.

**The one place this matters later:** `mcporter` spawns the MCP server itself
and will use system python unless told otherwise. Register it with the venv
interpreter or it fails with missing modules and no obvious cause:

    mcporter add least -- $PWD/.venv/bin/python $PWD/mcp/server.py

### Get the demo codebase

**cal.com is NOT part of the NemoClaw/OpenClaw/OpenShell stack.** It is demo
data and arrives separately - whoever carried the stack on USB had no reason
to bring it.

    ./setup-demo-repo.sh

Clones it if missing, fixes `config.yaml` to match, and verifies the scanner
finds signals. If you already have it somewhere else:

    ./setup-demo-repo.sh /path/to/cal.com

Faster than cloning: copy `~/hack-stage/demo-repos/cal.com` off a teammate's
laptop (443 MB). **Do not clone with `--depth 1`** - "Who owns what" comes from
git log, so no history means that section silently goes empty.

Start the services:

    ./run.sh

This seeds Okta, starts mock Okta on :8081, starts Vault dev on :8200 if the
binary is present, and reports which inference backend answers.

    python3 -m agent status

**It must say `vllm`.** If it says `ollama` you are about to demo a 3B model by
accident — vLLM is not up. If it says neither, start one before continuing.

Now run the pipeline:

    python3 -m agent baseline billing
    python3 -m agent onboard 00uNEWHIRE01 billing
    cat packets/nadia-rahimi.md

If you see a packet with real file citations, **the product works.** Everything
after this is interface.

### Reset between rehearsals

    python3 services/mock_okta/seed.py

Deterministic (seeded 42), so the demo state is identical every time.

---

## Phase 2 — Make it an agent

    mcporter add least -- python3 $PWD/mcp/server.py
    mcporter list                                  # "least" should appear

Test the tool server on its own, before involving OpenClaw:

    printf '%s\n' \
      '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' \
      '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}' \
      | python3 mcp/server.py

Expect 9 tools. If this works and OpenClaw doesn't see them, the problem is
registration — not your code.

Then load `mcp/AGENT.md` as the OpenClaw agent's system prompt. Without it the
agent has tools but no idea in what order to use them, or when to refuse.

---

## Phase 3 — Slack

You do not need the Slack desktop app. You need a workspace and two tokens.

1. **Workspace** — use an existing one, or create a free one at slack.com.
   A fresh workspace demos better: no noise on screen.

2. **Tokens** — at api.slack.com/apps, create an app and enable **Socket Mode**.
   Socket Mode matters: without it Slack needs a public URL to POST events to,
   and the GB10 on venue wifi does not have one. Socket Mode opens an outbound
   websocket instead.
   - Bot token `xoxb-…` with `chat:write`, `app_mentions:read`
   - App token `xapp-…` with `connections:write`

3. **Give them to OpenClaw** — via `nemoclaw onboard`, which covers managed
   integrations. Slack is OpenClaw's primary use case so it should be a
   prompted step.

### Test

In Slack:

    @least what would Nadia Rahimi get if we onboarded her to billing today?

A correct answer names Sarah Chen as the donor, says 9 grants, and mentions
`db-prod-write`. If it answers without those specifics it is not calling your
tools — check Phase 2.

---

## The always-on loop

    python3 loop/daemon.py 3600        # drift scan + repo watch, hourly

For the demo, run one pass before you present so the channel already shows the
overnight finding when you begin.

---

## If you run out of time

**Phases 1 and 2 alone are a demoable product.** Drive it from the terminal and
narrate. Slack makes it *look* like an agent; MCP makes it *be* one.

If Slack fights you at 4 PM, drop it and rehearse the terminal version.
"Doesn't break" is in the judging criteria. A prettier demo that fails is worth
less than a plain one that works.

---

## Known untested surfaces

Honest list, so nothing surprises you:

- The vLLM path in `agent/llm.py` — only the Ollama fallback has been exercised
- The 35B model — all output so far came from a 3B
- aarch64 Linux — developed on macOS ARM
- `execute.open_pr` live — only dry-run; the `gh` calls have never fired
- OpenClaw and Slack — not wired at all yet

The first two are the ones to check immediately: `python3 -m agent status`,
then read a generated packet and grep one cited file path to confirm it exists.
