"""
Packet generator -- the deliverable.

One Markdown file that is simultaneously the onboarding doc, the access request,
the justification, and (once committed) the audit evidence. Frontmatter is
machine-readable so execute.py can act on it; the body is human-readable so a
manager can approve on understanding rather than on trust.
"""
import datetime as dt, json, os, subprocess, pathlib
from . import okta, peers, gate, llm, trace
from .scanner import scan, accounts_and_setup, TEAM_PATHS
from .baseline import clone_a_teammate
from .config import CFG

SYSTEM = ("You are a staff engineer writing onboarding notes for a new teammate. "
          "Be concrete and brief. No greetings, no filler, no bullet-point padding. "
          "You are given real facts about a real repository -- use only those facts "
          "and never invent file names, services, or people. "
          "Do NOT restate the section title; start directly with the content.")

def _strip_echoed_heading(text, title):
    """Small models repeat the heading back. Drop it rather than render it twice."""
    lines = [l for l in text.strip().splitlines()]
    while lines and (lines[0].strip().lower().strip("#* ") == title.lower()
                     or not lines[0].strip()):
        lines.pop(0)
    return "\n".join(lines).strip()

def owners(repo, subpath, top=4):
    """Who actually owns this code, from git history.

    A trimmed copy of the repo (as uploaded into the sandbox) carries no history,
    so a precomputed .least-owners.json is used when present.
    """
    pre = pathlib.Path(repo) / ".least-owners.json"
    if pre.exists():
        try: return json.loads(pre.read_text()).get(subpath, [])[:top]
        except Exception: pass
    try:
        out = subprocess.run(["git", "-C", str(repo), "log", "--format=%an", "--", subpath],
                             capture_output=True, text=True, timeout=25).stdout
        names = [l for l in out.splitlines() if l.strip()]
        from collections import Counter
        return [n for n, _ in Counter(names).most_common(top)]
    except Exception:
        return []

def build(user_id, team, use_llm=True):
    # LEAST_NO_LLM=1 skips prose generation - set inside the sandbox, where the
    # model server on the host is not reachable on loopback.
    use_llm = use_llm and not os.environ.get("LEAST_NO_LLM")
    repo   = CFG["repo"]
    trace.step(f"resolving {user_id}")
    u      = okta.resolve(user_id)
    user_id = u["id"]
    prof   = u["profile"]
    paths  = TEAM_PATHS.get(team, [])
    derived     = scan(paths)
    accounts, setup_steps = accounts_and_setup(derived)
    trace.step("peer usage — what does the team ACTUALLY use?")
    conventional= [c for c in peers.conventional(team)
                   if c["group"] not in {d["group"] for d in derived}]
    for c in conventional:
        trace.log("peer", f"+    {c['group']}", c["because"])
    proposed    = {d["group"] for d in derived} | {c["group"] for c in conventional}
    trace.step("baseline — what happens today?")
    base        = clone_a_teammate(team)
    trace.log("pkt", f"cloning {base['donor']} would grant {len(base['grants'])}",
              "0 justified")
    sens        = {g["profile"]["name"]: g.get("_sensitivity", 0) for g in okta.groups()}
    declined    = [{"group": g,
                    "because": ("no code path requires it and fewer than 75% of the team "
                                "uses it" if sens.get(g,0) < 2 else
                                "production-level access with no code path requiring it")}
                   for g in sorted(set(base["grants"]) - proposed)]
    g           = gate.check(user_id,
                             person=f'{prof["firstName"]} {prof["lastName"]}',
                             handle=prof["login"])
    trace.log("gate", "PASS — Okta Verify enrolled" if g["passed"]
                      else f'BLOCK — {g["status"]}',
              ", ".join(g["factors"]) or g["statement"] or "")
    for d in declined:
        trace.log("pkt", f"-    {d['group']}", d["because"][:60])
    own         = owners(repo, paths[0]) if paths else []

    prose = {}
    if use_llm:
        trace.step("writing the onboarding prose")
        facts = json.dumps({"team": team, "paths": paths, "owners": own,
                            "signals": [{"group": d["group"], "why": d["why"],
                                         "file": d["citations"][0]["file"]} for d in derived]},
                           indent=2)
        try:
            prose["intro"] = _strip_echoed_heading(llm.ask(SYSTEM,
                f"Write 3-4 sentences for a section called \"What you're joining\" for a new "
                f"engineer on the {team} team of the cal.com codebase. Facts:\n{facts}"),
                "What you're joining")
            # NOTE: the model is NOT asked to name environment variables. A 3B
            # model invented VAULT_BILLING_READ_TOKEN here, which does not exist
            # in cal.com. Identifiers come from the scanner; the model only
            # writes the sentence around them.
            prose["local"] = _strip_echoed_heading(llm.ask(SYSTEM,
                f"Write TWO sentences of context for a 'Running it locally' section: what "
                f"the developer is setting up and why. Do NOT list or name any environment "
                f"variables, files, or tokens - those are rendered separately. Facts:\n{facts}"),
                "Running it locally")
            prose["_model"] = llm.LAST_USED or "?"
        except llm.Offline as e:
            prose["_offline"] = str(e)

    return {"user": u, "team": team, "derived": derived, "conventional": conventional,
            "accounts": accounts, "setup_steps": setup_steps,
            "declined": declined, "baseline": base, "gate": g, "owners": own,
            "prose": prose, "paths": paths,
            "generated": dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")}

def _scalar(v):
    """
    Make a directory string safe to interpolate into frontmatter.

    Frontmatter is read back to decide who may approve a packet and which groups
    to apply, so a newline inside a profile field is an authorisation bug, not a
    formatting one: a surname containing "\nmanager: mallory@..." injected a
    manager line that the parser -- which took the first match -- preferred to
    the real one, and an "access: derived:" block whose groups were then applied.
    Proven end to end against the live directory before this existed.

    Everything that reaches frontmatter goes through here. Newlines become
    spaces; nothing is dropped, so a mangled name is visible rather than silently
    truncated.
    """
    return " ".join(str("-" if v is None else v).split())


def render(p):
    prof, g = p["user"]["profile"], p["gate"]
    fm = ["---",
          f'subject: {_scalar(prof["login"])}',
          f'name: {_scalar(prof["firstName"])} {_scalar(prof["lastName"])}',
          f'team: {_scalar(p["team"])}',
          f'start_date: {_scalar(prof.get("startDate","-"))}',
          f'manager: {_scalar(prof.get("manager","-"))}',
          f'generated: {p["generated"]}',
          f'model: {p["prose"].get("_model") or "none — no prose generated"}'
          f'   # on-box, no network',
          f'status: {"awaiting-approval" if g["passed"] else "blocked-mfa"}',
          "access:", "  derived:"]
    for d in p["derived"]:
        fm.append(f'    - {{group: {_scalar(d["group"])}, because: "{_scalar(d["because"])}"}}')
    fm.append("  conventional:")
    for c in p["conventional"]:
        fm.append(f'    - {{group: {_scalar(c["group"])}, because: "{_scalar(c["because"])}"}}')
    fm.append("  declined:")
    for d in p["declined"]:
        fm.append(f'    - {{group: {_scalar(d["group"])}, because: "{_scalar(d["because"])}"}}')
    fm += ["---", ""]

    n_prop = len(p["derived"]) + len(p["conventional"])
    b = ["# %s %s — %s team" % (prof["firstName"], prof["lastName"], p["team"]), ""]
    if not g["passed"]:
        b += [f'> **BLOCKED — {g["reason"]}**', ""]
    b += [f'Starts {prof.get("startDate","-")}. Manager: {prof.get("manager","-")}.', "",
          "## Summary", "",
          f'| | |', f'|---|---|',
          f'| Cloning a teammate would grant | **{len(p["baseline"]["grants"])}** grants, 0 justified |',
          f'| This packet proposes | **{n_prop}** grants, all justified |',
          f'| Declined | **{len(p["declined"])}** |', ""]
    if p["prose"].get("intro"):
        b += ["## What you're joining", "", p["prose"]["intro"], ""]
    if p["owners"]:
        b += ["## Who owns what", "",
              "Most frequent authors in `%s`:" % (p["paths"][0] if p["paths"] else "-"), ""]
        b += ["- %s" % o for o in p["owners"]] + [""]
    envs = sorted({c["var"] for d in p["derived"] for c in d["citations"]})
    if p["prose"].get("local") or envs:
        b += ["## Running it locally", ""]
        if p["prose"].get("local"): b += [p["prose"]["local"], ""]
        if envs:
            b += ["Environment variables this code actually reads "
                  "(extracted from the repo, not generated):", ""]
            b += ["- `%s`" % e for e in envs] + [""]

    b += ["## Access requested", ""]
    if p["derived"]:
        b += ["**Derived from code** — the repository requires these:", ""]
        for d in p["derived"]:
            b.append(f'- `{d["group"]}` — {d["because"]}')
            for c in d["citations"][1:3]:
                b.append(f'    - also `{c["file"]}:{c["line"]}` (`{c["var"]}`)')
        b.append("")
    if p["conventional"]:
        b += ["**Team convention** — not in the code, but the team actually uses these:", ""]
        b += [f'- `{c["group"]}` — {c["because"]}' for c in p["conventional"]] + [""]
    if p["declined"]:
        b += ["**Declined** — a teammate has these; nothing justifies giving them to a new hire:", ""]
        b += [f'- ~~`{d["group"]}`~~ — {d["because"]}' for d in p["declined"]] + [""]
    b += ["**Unknown** — no signal in code or peer usage. Manager decides:", "",
          "- Salesforce, Figma, or anything provisioned outside the identity provider.", ""]

    if p.get("accounts"):
        b += ["## Accounts someone has to create", "",
              "These are not IAM groups — they do not exist in the identity provider, "
              "so the agent cannot grant them. A person has to send an invite.", "",
              "| Service | Ask | Level | Why |", "|---|---|---|---|"]
        for a in p["accounts"]:
            b.append(f'| {a["service"]} | {a["ask"]} | {a["level"]} | `{a["because"]}` |')
        b.append("")

    if p.get("setup_steps"):
        b += ["## First-day setup", ""]
        b += [f'- {x["step"]}' for x in p["setup_steps"]] + [""]
    if p["prose"].get("_offline"):
        b += ["> _Prose sections omitted: %s_" % p["prose"]["_offline"], ""]
    return "\n".join(fm + b)

def write(p):
    prof = p["user"]["profile"]
    slug = prof["login"].split("@")[0].replace(".", "-")
    out  = CFG["_packets"] / f"{slug}.md"
    out.write_text(render(p))
    return out
