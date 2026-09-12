# Issues we hit, and what fixed them

Written up so nobody on the team burns the same hour twice. Roughly in the
order we hit them.

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
