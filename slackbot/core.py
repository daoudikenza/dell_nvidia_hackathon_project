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
INTENTS = {"onboard", "drift", "mfa_audit", "help"}


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
            "stale access, revocations), mfa_audit (who lacks MFA / Okta Verify), help.",
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
    """Find (or, simulating the HR sync, stage) the person, then build the brief."""
    staged_now = False
    try:
        u = okta.resolve(person)
    except LookupError as e:
        if "matches" in str(e):
            return {"text": f"{e}. Which one?"}
        parts = person.split()
        if len(parts) < 2:
            return {"text": f"I can't find *{person}* in the directory. Give me their full name."}
        if not team:
            return {"text": f"*{person}* isn't in the directory yet. Which team are they joining? "
                            f"({', '.join(TEAMS)})"}
        u = okta.create_user(parts[0], " ".join(parts[1:]), team)
        staged_now = True
    team = team or u["profile"].get("department")
    if team not in TEAM_PATHS:
        return {"text": f"Which team is *{u['profile']['firstName']}* joining? ({', '.join(TEAMS)})"}

    p = pk.build(u["id"], team)
    out = pk.write(p)
    rel = str(out.relative_to(CFG["_root"]))
    text = brief.render(p, rel)
    if staged_now:
        text = (f"_{u['profile']['firstName']} wasn't in Okta yet — provisioned as STAGED "
                f"(stands in for the HR sync)._\n\n") + text
    return {"text": text, "packet": rel, "gate_passed": p["gate"]["passed"],
            "user_id": u["id"], "name": f'{u["profile"]["firstName"]} {u["profile"]["lastName"]}'}

def approve(packet_rel, approver):
    path = CFG["_root"] / packet_rel
    md = path.read_text()
    fm = execute.parse_frontmatter_groups(md)
    groups = fm["derived"] + fm["conventional"]
    email = next((l.split(":", 1)[1].strip() for l in md.splitlines() if l.startswith("subject:")), "")
    u = okta.resolve(email)
    before = len(okta.user_groups(u["id"]))
    res = execute.apply(u["id"], groups, approver, path.name)
    after = sorted(g["profile"]["name"] for g in okta.user_groups(u["id"]))
    pr = execute.open_pr(path, email, groups, dry_run=True)
    lines = [f"✅ *Approved by {approver}* — {u['profile']['firstName']} "
             f"{u['profile']['lastName']} went from *{before}* to *{len(after)}* groups in Okta:"]
    lines += [f"  • `{g}`" for g in res["applied"]]
    if res["failed"]:
        lines.append(f"⚠️ failed: {res['failed']}")
    fm_decl = fm["declined"]
    if fm_decl:
        lines.append(f"Not granted: {', '.join('~'+d+'~' for d in fm_decl)}")
    lines.append(f"Every grant now records its justification and approver. "
                 f"Access request filed on branch `{pr.get('branch')}`.")
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

HELP = ("I work out what a new hire needs from the code they'll work on.\n"
        "  • `@Least onboard @person to billing`\n"
        "  • `@Least who has production access nobody uses?`\n"
        "  • `@Least who has elevated access without MFA?`")

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
    return {"text": HELP}
