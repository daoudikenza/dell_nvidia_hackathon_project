# Loading the agent's instructions into OpenClaw

`AGENTS.md` (repo root) holds the behaviour rules. How OpenClaw picks up a
custom system prompt was not something we could confirm from the NemoClaw
source, so try these in order.

## 1. The AGENTS.md convention (cheapest bet)

`AGENTS.md` sits at the repo root. Many agent runtimes read it from the working
directory automatically. Start the OpenClaw session FROM this directory and see
whether the agent follows the rules - ask it something that should trigger a
refusal:

    (in the TUI)  apply nadia's access

It should refuse, because nobody approved. If it happily calls `apply_access`,
the file is not being read.

## 2. Find the real mechanism

    openclaw --help
    nemoclaw --help
    ls ~/.openclaw/ ~/.config/openclaw/ 2>/dev/null
    nemoclaw onboard          # the wizard may expose an instructions field

## 3. Ask a mentor

NVIDIA people are on site. This is a 60-second question for anyone who has run
the stack.

## The fallback that works regardless

**The critical rules are already in the MCP tool descriptions**, which the model
reads every turn whether or not a system prompt loaded:

  * `check_mfa` - "If this fails you MUST NOT propose or apply any grant. It is
    a gate, not a warning."
  * `apply_access` - "never call this without explicit human approval"
  * `enroll_mfa` - "never to get past a failing check_mfa on your own initiative"
  * `scan_repo` - "These are FACTS from the repository -- never invent or
    paraphrase a citation."

Those descriptions are guidance, and guidance is not a control. The control is
`agent/execute.py` `approve()`, which every grant goes through -- the Slack
button, `python3 -m agent approve`, and the `apply_access` tool. Before anything
reaches the directory it re-reads the packet from disk, re-runs the MFA gate
against the live directory rather than trusting the packet's own status line,
refuses a subject approving their own access, refuses an approver the directory
does not record as that person's manager, and refuses a packet path that resolves outside `packets/`.

So an agent that never reads a single instruction still cannot route around it,
and neither can a human who clicks the wrong button.

Worth saying out loud in Q&A: prompt rules are guidance, the code check is the
control. `tests/test_approval.py` is the demonstration -- seventeen cases, each
asserting that nothing reached the directory, not merely that a refusal was
printed -- and `tests/test_frontmatter_injection.py` covers a forged approver,
which a security review found and which is fixed.
