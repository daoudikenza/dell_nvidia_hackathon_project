# Getting the Slack demo working

## Fastest path — run our bot  (recommended for the demo)

A manager mentions the bot like a colleague:

    @Least onboard @Mikko Liivak to billing

It resolves the mentioned Slack user to a name, finds them in Okta (or stages
them, standing in for the HR sync), scans cal.com, and replies in-thread with
the brief and an **Approve access** button. Clicking it provisions the groups.

### 1. Slack app settings  (api.slack.com/apps -> your app)

- **Socket Mode** -> on. App-level token, scope `connections:write` -> `xapp-…`
- **Interactivity & Shortcuts** -> on. No request URL needed in Socket Mode.
  Required for the Approve button.
- **Event Subscriptions** -> on -> bot event `app_mention`
- **OAuth & Permissions -> Bot Token Scopes:** `app_mentions:read`, `chat:write`,
  **`users:read`** (turns `@Mikko Liivak` into a name)
- **Reinstall to Workspace** after changing scopes -> `xoxb-…`
- In the channel: `/invite @Least`

### 2. On the Dell

    cd ~/hackathon/dell_nvidia_hackathon_project
    git pull
    .venv/bin/pip install -r requirements.txt
    ./run.sh                                   # mock Okta must be up

    export SLACK_BOT_TOKEN="xoxb-…"
    export SLACK_APP_TOKEN="xapp-…"
    .venv/bin/python -m slackbot.bot

Leave it running. It prints `Least is listening on Slack`.

### 3. In Slack

    @Least onboard @Nadia Rahimi to billing        # enrolled -> Approve button
    @Least onboard @Mikko Liivak to billing        # new -> staged, MFA blocks
    @Least who has production access nobody uses?
    @Least who has elevated access without MFA?

Mikko is blocked until he enrolls. To show the unblock live:

    .venv/bin/python -m agent enroll mikko         # on the Dell

then click **Re-check Okta Verify** in the thread.

### Do not run two Socket Mode connections on one app

If you ALSO enabled Slack through NemoClaw (`channels add slack`) with the same
tokens, Slack splits events randomly between the two connections — half your
mentions vanish. Pick one:

    nemoclaw <sandbox-name> channels stop slack    # keep our bot

or create a second Slack app for the other path.

### The honest tradeoff

This bot carries Slack messages itself instead of through OpenClaw. Inference
still runs on the GB10, the tools are the same ones OpenClaw's agent calls over
MCP, and the OpenClaw TUI remains the stack demonstration. If a judge asks, say
exactly that. If OpenClaw's own Slack channel works for you (below), prefer it.

---

## The OpenClaw-native path


Taken from NemoClaw's own docs (`docs/manage-sandboxes/set-up-slack.mdx`), not
guessed. Slack uses **Socket Mode**, which is what makes this work on venue wifi
with no public URL.

---

## 1. Create the Slack app  (browser, any machine, ~5 min)

At **api.slack.com/apps** → *Create New App* → *From scratch* → name it `Least`.

**a. Socket Mode** — left sidebar → *Socket Mode* → toggle **on**. It generates
an app-level token. Scope `connections:write`.
→ copy the **`xapp-…`** token

**b. Event Subscriptions** — toggle on → *Subscribe to bot events* → add
`app_mention`

**c. OAuth & Permissions** → *Bot Token Scopes*:
`app_mentions:read`, `chat:write`

**d. Install to Workspace**
→ copy the **`xoxb-…`** token

**e. In Slack:** `/invite @Least` in the channel you'll demo in.

## 2. Get the two IDs NemoClaw wants

Allowlists use **IDs, not names**.

- **Your member ID** — click your avatar → *Profile* → ⋮ → *Copy member ID*
  (starts `U…`)
- **Channel ID** — right-click the channel → *Copy link*. The ID is the last
  path segment (starts `C…`)

## 3. Enable the channel

    export SLACK_BOT_TOKEN="xoxb-…"
    export SLACK_APP_TOKEN="xapp-…"
    export SLACK_ALLOWED_USERS="U…"        # your member ID
    export SLACK_ALLOWED_CHANNELS="C…"     # the demo channel ID

    nemoclaw <sandbox-name> channels add slack

NemoClaw validates both tokens live against Slack's `auth.test` and
`apps.connections.open` before saving. **If validation fails it silently skips
the Slack channel** — it does not error loudly — so check step 4.

Don't know your sandbox name? `nemoclaw --help`, or it is whatever you named it
during `nemoclaw onboard`.

## 4. Wait for readiness — do not skip this

    nemoclaw <sandbox-name> channels status --channel slack --wait --timeout 180 --json

Polls until Slack is registered, the `slack` network policy preset is applied,
the OpenClaw Slack runtime is running, Socket Mode is connected, and the account
probe succeeds. Exits 0 with evidence, or nonzero with a category and reason
telling you which one failed.

After a rebuild, OpenClaw needs time to initialise the Slack plugin. Deferred
initialisation is reported as *retryable* — rerun it.

## 5. Give the agent our tools

    cd ~/hackathon/dell_nvidia_hackathon_project
    mcporter add least -- $PWD/.venv/bin/python $PWD/mcp/server.py
    mcporter list

**Use `.venv/bin/python`, not `python3`** — mcporter spawns its own process and
system python has none of our packages.

Load `AGENTS.md` as the agent's system prompt. It tells the agent that when a
manager asks about a new hire, call `onboarding_brief` and post the result
as-is.

## 6. Test

In the demo channel:

    @Least I have a new hire joining billing next week, what do they need?

A correct answer names **Nadia Rahimi**, says **9 grants today vs 6 proposed**,
cites `stripepayment/_metadata.ts:11`, lists the accounts someone must create
(Stripe Dashboard, Sentry, Vercel) with who to ask, and ends asking for approval.

If it answers vaguely with no citations, it is not calling our tools — check
`mcporter list` and test the server standalone (see `mcp/README.md`).

---

## Gotchas from the docs

**One Slack sandbox per OpenShell gateway.** Two sandboxes sharing Slack
credentials conflict. `channels add slack` aborts on a detected conflict;
`--force` overrides, onboarding and rebuild do not.

**Both allowlists apply together.** With both set, the mention must come from an
allowed channel *and* an allowed member. A denied mention gets a denial notice,
not silence — so if you see "denied", your member or channel ID is wrong.

**Channel messages always require an explicit @mention.** DMs do not.

**Testing without live Slack:** `NEMOCLAW_SKIP_SLACK_AUTH_VALIDATION=1` lets
channel setup run with placeholder tokens. Format checks still apply. Useful if
venue wifi dies while you are still wiring.

---

## If it will not cooperate by 5 PM

Stop and demo in the OpenClaw TUI instead. It is already running on the box, it
is the same agent with the same tools, it needs no tokens and no internet, and
it satisfies "correct use of NemoClaw + OpenClaw + OpenShell" identically.

You lose the chat metaphor. You keep every number, every citation, and the whole
argument. "Doesn't break" is in the judging criteria; a prettier demo that fails
is worth less than a plain one that works.
