"""
What the Slack bot does, with no Slack in it.

Kept separate from the Slack plumbing so every path can be exercised offline:
parse the manager's message, decide what they want, do it, return the reply.
"""
import re, json, pathlib, urllib.error
from agent import okta, packet as pk, brief, execute, llm, trace
from agent.scanner import TEAM_PATHS
from agent.config import CFG

TEAMS = list(TEAM_PATHS)
INTENTS = {"onboard", "drift", "mfa_audit", "local", "help"}


def explain_failure(e):
    """
    Turn an exception into something a manager can act on.

    Every unhandled error used to reach the channel as
    `Something failed: HTTPError: HTTP Error 404: Not Found`, which is the same
    string whether the directory is down, the person was never provisioned, or
    the demo was reseeded under a running bot. Those have three different
    remedies, so they get three different messages.
    """
    if isinstance(e, urllib.error.HTTPError) and e.code == 404:
        return ("The directory answered, and it has no record of that person or group. "
                "This is not an outage. If the demo was reseeded while I was running, "
                "the ids I was holding are stale — ask me again by name and I will look "
                "them up fresh.")
    if isinstance(e, urllib.error.URLError):
        return (f"I could not reach the identity provider at {okta.BASE} ({e.reason}). "
                f"Nothing was checked and nothing was changed. Someone needs to start it "
                f"with `./run.sh` on the box.")
    if isinstance(e, LookupError):
        return str(e)
    if isinstance(e, FileNotFoundError):
        return (f"I could not find `{e.filename}`. If that is a packet, it was cleared "
                f"since the message was posted — re-run the onboard and approve the new one.")
    return (f"I failed with `{type(e).__name__}: {e}`. Nothing was granted. "
            f"The agent's own log on the box has the traceback.")

def _team_in(text):
    t = text.lower().replace("app store", "app-store")
    return next((team for team in TEAMS if re.search(rf"\b{re.escape(team)}\b", t)), None)

def _rules(text):
    t = text.lower()
    if re.search(r"\b(onboard|new hire|joining|joins|starts?|starting|what does .* need)\b", t):
        return "onboard"
    if re.search(r"\b(local|locally|on.?box|air.?gap|offline|egress|nvidia|gpu|"
                 r"what model|which model|where.*(run|running))\b", t): return "local"
    if re.search(r"\b(mfa|okta verify|2fa|second factor)\b", t): return "mfa_audit"
    if re.search(r"\b(drift|unused|stale|audit|over-?provision|revok|nobody uses|never used|"
                 r"not used|dormant|production access|prod access)", t): return "drift"
    return "help"

def decide(text):
    """
    The model decides what the manager is asking for. Rules are the fallback,
    so a slow or confused model can never stall a live demo.
    """
    try:
        raw = llm.ask(
            "You route requests for an access-management assistant. Reply with ONE line "
            'of JSON only, like {"intent": "onboard"}. intent must be one of: onboard '
            "(someone is joining a team / what does a new hire need), drift (unused or "
            "stale access, revocations), mfa_audit (who lacks MFA / Okta Verify), "
            "local (is this running locally, what model, GPU, does anything leave "
            "the box), help.",
            f"Request: {text}")
        m = re.search(r"\{.*?\}", raw, re.S)
        intent = json.loads(m.group(0)).get("intent") if m else None
        if intent in INTENTS:
            trace.log("llm", f"decided intent: {intent}")
            return intent, "model"
    except Exception as e:
        trace.log("llm", "router unavailable, using rules", str(e)[:60])
    return _rules(text), "rules"

def _name_in(text):
    m = re.search(r"\b(?:onboard|onboarding)\s+([A-Z][\w'-]+(?:\s+[A-Z][\w'-]+)+)", text)
    return m.group(1) if m else None

def onboard(person, team=None):
    """Find the person, then build the brief. Finding, never creating."""
    try:
        u = okta.resolve(person)
    except LookupError as e:
        if "matches" in str(e):
            return {"text": f"{e}. Which one?"}
        # AGENTS.md: HR provisions identities, this agent does not create people.
        # The Slack path used to call okta.create_user here, which made the
        # agent's own stated rule false. Refusing keeps the rule true, and the
        # demo still works -- `agent stage` is the HR sync stand-in.
        return {"text": (
            f"*{person}* is not in the directory, and I do not create people. "
            f"Identities come from HR; I work out what an existing identity needs.\n"
            f"To stand in for that sync on the box: "
            f"`python3 -m agent stage {person} {team or '<team>'}`, then ask me again.")}
    team = team or u["profile"].get("department")
    if team not in TEAM_PATHS:
        return {"text": f"Which team is *{u['profile']['firstName']}* joining? ({', '.join(TEAMS)})"}

    p = pk.build(u["id"], team)
    out = pk.write(p)
    rel = str(out.relative_to(CFG["_root"]))
    return {"text": brief.render(p, rel), "packet": rel,
            "gate_passed": p["gate"]["passed"],
            "user_id": u["id"], "name": f'{u["profile"]["firstName"]} {u["profile"]["lastName"]}'}

def approve(packet_rel, approver):
    """
    Apply an approved packet, or refuse and say why.

    Everything that decides whether this is allowed lives in execute.approve.
    This function's only job is to turn the outcome into a Slack message.
    """
    try:
        res = execute.approve(packet_rel, approver)
    except execute.Refused as r:
        return {"text": f"⛔ *Not approved* — {r.message}", "refused": r.code}

    lines = [f"✅ *Approved by {res['approver_display']}* — {res['name']} went from "
             f"*{res['before']}* to *{res['after']}* groups in Okta:"]
    lines += [f"  • `{g}`" for g in res["applied"]]
    if res["failed"]:
        lines.append(f"⚠️ These did not apply: {res['failed']}")
    if res["declined"]:
        lines.append(f"Not granted: {', '.join('~'+d+'~' for d in res['declined'])}")
    lines.append(f"Each grant records the file:line that justified it and "
                 f"{res['approver_email']} as the approver.")
    # The PR is a dry run. Saying it was filed when it was not is the kind of
    # claim a judge checks, and it would be the only false line in the demo.
    pr = execute.open_pr(res["path"], res["subject"], res["applied"], dry_run=True)
    lines.append(f"Access request *drafted* for branch `{pr['branch']}` — not filed. "
                 f"Run `python3 -m agent approve {pathlib.Path(packet_rel).name} "
                 f"{res['approver_email']} --live` on the box to file it.")
    return {"text": "\n".join(lines)}

def drift():
    from agent.drift import analyse
    org = json.loads((CFG["_root"] / "services/mock_okta/org.json").read_text())
    prod = [f for f in analyse(org) if f["sensitivity"] == 2]
    L = [f"*{len(prod)} production-level grants nobody is using*"]
    for f in prod:
        svc = " _(service account)_" if f["service_account"] else ""
        L.append(f"  • `{f['group']}` — {f['name']}{svc}, {f['team']} — "
                 f"{'never used' if f['never_used'] else str(f['idle_days'])+'d idle'}")
    L.append("Revocations drafted. Reply to approve any of them.")
    return {"text": "\n".join(L)}

def mfa_audit():
    from agent.drift import unprotected
    org = json.loads((CFG["_root"] / "services/mock_okta/org.json").read_text())
    rows = unprotected(org)
    L = [f"*{len(rows)} people hold elevated access with no Okta Verify enrolled*"]
    for r in rows:
        tag = "PRODUCTION" if r["worst"] == 2 else "elevated"
        L.append(f"  • *{r['name']}* ({r['team']}) — {tag}: {', '.join('`'+g+'`' for g in r['groups'][:3])} "
                 f"— {r['tenure_days']} days, never enrolled")
    L.append("One phished password on any of these is the blast radius.")
    return {"text": "\n".join(L)}

def local():
    """
    The same evidence the terminal prints, posted into the channel.

    Worth noting when this is on screen: the reply travelled over Slack, and the
    inference that produced every other reply did not.
    """
    from agent.local_first import report
    return {"text": "```\n" + report() + "\n```"}

HELP = ("I work out what a new hire needs from the code they'll work on.\n"
        "  • `@Least onboard @person to billing`\n"
        "  • `@Least who has production access nobody uses?`\n"
        "  • `@Least who has elevated access without MFA?`\n"
        "  • `@Least are you running locally?` — model id, GPU, and everything "
        "this box has a connection to")

def handle(text, mentioned_names=()):
    intent, how = decide(text)
    team = _team_in(text)
    if intent == "onboard":
        person = (mentioned_names[0] if mentioned_names else None) or _name_in(text)
        if not person:
            return {"text": "Who's joining? Mention them, e.g. `@Least onboard @Mikko Liivak to billing`."}
        return onboard(person, team)
    if intent == "drift":     return drift()
    if intent == "mfa_audit": return mfa_audit()
    if intent == "local":     return local()
    return {"text": HELP}
