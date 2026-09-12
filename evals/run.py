#!/usr/bin/env python3
"""
Least — evaluation harness.

    .venv/bin/python evals/run.py

Twenty-odd cases with expected outcomes, run headlessly, printed as a pass-rate
table. This is the answer to "how did you evaluate it", and a pass rate beats
any adjective.

Three things it checks that are worth naming, because they are the three claims
the product makes that a judge would otherwise have to take on trust:

  CITATIONS   every `file:line` in every generated packet is greped back against
              the real repository and must resolve to a file with that many
              lines. This covers the model-written prose too, which until now
              was governed by an instruction in a system prompt and nothing else.

  REFUSALS    the approval control, exercised against the live directory:
              unenrolled subject, self-approval, a bystander, a path that
              escapes the packets directory. Each asserts on what reached the
              directory, not on what was printed.

  PARITY      the same request through slackbot.core and through the CLI
              produces the same packet. The terminal path is the demo fallback,
              so "Slack is a convenience, not the product" has to be true.

A case that cannot run says SKIP and why. It never says PASS. A harness that
goes green when the thing it tests is absent is worse than no harness.
"""
import json
import pathlib
import re
import subprocess
import sys
import urllib.error

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent import execute, gate, llm, okta, packet as pk          # noqa: E402
from agent.config import CFG                                       # noqa: E402
from agent.scanner import TEAM_PATHS                               # noqa: E402

SUBJECT = "nadia.rahimi@cal.example.com"
MANAGER = "sarah.chen@cal.example.com"
BYSTANDER = "marcus.okafor@cal.example.com"

CASES = []


def case(section, name):
    def wrap(fn):
        CASES.append((section, name, fn))
        return fn
    return wrap


def reseed():
    subprocess.run([sys.executable, str(ROOT / "services/mock_okta/seed.py")],
                   capture_output=True, check=True)


def prereqs():
    """Fail with one line, not a traceback, when the box is not set up."""
    problems = []
    try:
        okta.users()
    except Exception as e:
        problems.append(f"the directory is not answering ({type(e).__name__}). "
                        f"Start it: ./run.sh")
    if not CFG["repo"].exists():
        problems.append(f"the demo repo is missing at {CFG['repo']}. "
                        f"Fetch it: ./setup-demo-repo.sh")
    return problems


def approver(email, source="cli"):
    return execute.Approver(email=email, source=source, display=email)


def groups_of(email):
    return {g["profile"]["name"] for g in okta.user_groups(okta.resolve(email)["id"])}


# --------------------------------------------------------------- citations
CITATION = re.compile(r"`?([\w./-]+\.(?:ts|tsx|js|jsx|py|yml|yaml|json|prisma)):(\d+)`?")


def _bad_citations(text):
    """Every file:line in this text, that does not resolve in the real repo."""
    bad = []
    for f, line in CITATION.findall(text):
        target = CFG["repo"] / f
        if not target.is_file():
            bad.append(f"{f}:{line} — no such file")
            continue
        try:
            n = sum(1 for _ in target.open("rb"))
        except OSError as e:
            bad.append(f"{f}:{line} — unreadable ({e})")
            continue
        if int(line) > n:
            bad.append(f"{f}:{line} — file has {n} lines")
    return bad


def _citation_case(team):
    @case("CITATIONS", f"every file:line in a {team} packet resolves")
    def _(team=team):
        uid = next((u["id"] for u in okta.users()
                    if u["profile"].get("department") == team), None)
        if not uid:
            return None, f"no {team} user in the directory"
        p = pk.build(uid, team, use_llm=False)
        rendered = pk.render(p)
        found = CITATION.findall(rendered)
        if not found:
            # Vacuous truth is not a pass. No citations means the scanner found
            # no signal for this team in this checkout, which is a finding about
            # the corpus, not evidence that citations resolve.
            return None, "no citations derived for this team in this checkout"
        bad = _bad_citations(rendered)
        return not bad, (f"{len(bad)} dangling: {bad[:3]}" if bad
                         else f"{len(found)} citations, all resolve")
    return _


for _team in TEAM_PATHS:
    _citation_case(_team)


@case("CITATIONS", "model-written prose invents no file:line")
def prose_citations():
    """
    The prose sections are the only text in a packet the model writes. The
    system prompt tells it not to invent identifiers; this checks rather than
    trusts. Skips rather than passes when there is no inference on this host.
    """
    name, kind, model = llm.which()[:3]
    if not kind:
        return None, "no inference backend on this host — cannot generate prose"
    p = pk.build(SUBJECT, "billing", use_llm=True)
    prose = " ".join(v for k, v in p["prose"].items() if isinstance(v, str)
                     and not k.startswith("_"))
    bad = _bad_citations(prose)
    return not bad, (f"{len(bad)} invented: {bad[:3]}" if bad
                     else f"prose from {p['prose'].get('_model')} cites nothing false")


# --------------------------------------------------------------- refusals
@case("REFUSALS", "unenrolled subject is refused and granted nothing")
def refuse_unenrolled():
    reseed()
    pk.write(pk.build(SUBJECT, "billing", use_llm=False))
    before = groups_of(SUBJECT)
    try:
        execute.approve("packets/nadia-rahimi.md", approver(MANAGER))
        return False, "approved an unenrolled subject"
    except execute.Refused as r:
        ok = r.code == "mfa_gate" and groups_of(SUBJECT) == before
        return ok, f"{r.code}, directory unchanged ({len(before)} groups)"


@case("REFUSALS", "the subject cannot approve their own access")
def refuse_self():
    reseed()
    okta.enroll_factor(okta.resolve(SUBJECT)["id"])
    pk.write(pk.build(SUBJECT, "billing", use_llm=False))
    before = groups_of(SUBJECT)
    try:
        execute.approve("packets/nadia-rahimi.md", approver(SUBJECT))
        return False, "subject approved themselves"
    except execute.Refused as r:
        return r.code == "self_approval" and groups_of(SUBJECT) == before, r.code


@case("REFUSALS", "a bystander cannot approve, and is told who can")
def refuse_bystander():
    before = groups_of(SUBJECT)
    try:
        execute.approve("packets/nadia-rahimi.md", approver(BYSTANDER))
        return False, "a bystander approved"
    except execute.Refused as r:
        return (r.code == "not_approver" and MANAGER in r.message
                and groups_of(SUBJECT) == before), f"{r.code}, names {MANAGER}"


@case("REFUSALS", "a packet path escaping packets/ is refused")
def refuse_traversal():
    before = groups_of(SUBJECT)
    try:
        execute.approve("packets/../../../etc/passwd", approver(MANAGER))
        return False, "read a path outside packets/"
    except execute.Refused as r:
        return r.code == "bad_packet_path" and groups_of(SUBJECT) == before, r.code


@case("REFUSALS", "the named manager CAN approve")
def allow_manager():
    before = groups_of(SUBJECT)
    res = execute.approve("packets/nadia-rahimi.md", approver(MANAGER))
    after = groups_of(SUBJECT)
    return bool(res["applied"]) and after > before, \
        f"{len(before)} -> {len(after)} groups"


@case("REFUSALS", "declined groups are never applied")
def declined_not_applied():
    md = (CFG["_packets"] / "nadia-rahimi.md").read_text()
    declined = set(execute.parse_frontmatter_groups(md)["declined"])
    held = groups_of(SUBJECT)
    leaked = declined & held
    return not leaked, (f"leaked {leaked}" if leaked
                        else f"{len(declined)} declined, none held")


@case("REFUSALS", "the audit record carries the approver, not a display name")
def audit_record():
    org = json.loads((ROOT / "services/mock_okta/org.json").read_text())
    uid = okta.resolve(SUBJECT)["id"]
    recorded = [m for m in org["memberships"]
                if m["userId"] == uid and m.get("approvedBy")]
    return (bool(recorded) and all(MANAGER in m["approvedBy"] for m in recorded)), \
        f"{len(recorded)} grants carry {MANAGER}"


# --------------------------------------------------------------- gate taxonomy
@case("GATE", "an unknown user reads as not-in-directory, not an outage")
def gate_404():
    g = gate.check("00uNOSUCHUSER", person="Nobody")
    return (g["status"] == "no_such_user" and not g["passed"]
            and "unreachable" not in g["reason"].lower()), g["status"]


@case("GATE", "a directory that does not answer says nothing was checked")
def gate_down():
    real = okta.factors
    okta.factors = lambda uid: (_ for _ in ()).throw(
        urllib.error.URLError("[Errno 61] Connection refused"))
    try:
        g = gate.check("00uNEWHIRE01", person="Nadia Rahimi")
    finally:
        okta.factors = real
    return (g["status"] == "directory_unreachable"
            and "not enrolled" not in g["reason"].lower()), g["status"]


@case("GATE", "an unenrolled person is named, with the command to fix it")
def gate_not_enrolled():
    reseed()
    u = okta.resolve(SUBJECT)
    g = gate.check(u["id"], person="Nadia Rahimi", handle=SUBJECT)
    return (g["status"] == "not_enrolled" and "Nadia Rahimi" in g["reason"]
            and f"agent enroll {SUBJECT}" in g["reason"]), g["status"]


@case("GATE", "enrollment started but not activated does not pass")
def gate_pending():
    real = okta.factors
    okta.factors = lambda uid: [{"factorType": "push", "status": "PENDING_ACTIVATION"}]
    try:
        g = gate.check("00uNEWHIRE01", person="Nadia Rahimi")
    finally:
        okta.factors = real
    return not g["passed"] and g["status"] == "not_enrolled", g["status"]


# --------------------------------------------------------------- parity
@case("PARITY", "Slack and the terminal produce the same packet")
def parity():
    reseed()
    okta.enroll_factor(okta.resolve(SUBJECT)["id"])
    from slackbot import core

    slack = core.onboard(SUBJECT, "billing")
    slack_md = (ROOT / slack["packet"]).read_text()
    slack_access = slack_md.split("access:")[1].split("---")[0]

    r = subprocess.run([sys.executable, "-m", "agent", "onboard", SUBJECT,
                        "billing", "--no-llm"], cwd=ROOT, capture_output=True, text=True)
    if r.returncode != 0:
        return False, f"CLI onboard failed: {r.stderr[-120:]}"
    cli_access = (CFG["_packets"] / "nadia-rahimi.md").read_text() \
        .split("access:")[1].split("---")[0]
    return slack_access == cli_access, "identical access blocks"


@case("PARITY", "Slack refuses to create a person who is not in the directory")
def parity_no_create():
    from slackbot import core
    before = len(okta.users())
    r = core.onboard("Wholly Fictional", "billing")
    return ("do not create people" in r["text"] and len(okta.users()) == before), \
        f"{before} users before and after"


# --------------------------------------------------------------- determinism
@case("DETERMINISM", "reseeding twice gives byte-identical state")
def stable_seed():
    org = ROOT / "services/mock_okta/org.json"
    reseed(); a = org.read_text()
    reseed(); b = org.read_text()
    return a == b, f"{len(a)} bytes, identical"


@case("DETERMINISM", "group ids survive a reseed")
def stable_ids():
    org = ROOT / "services/mock_okta/org.json"
    reseed(); a = json.loads(org.read_text())
    reseed(); b = json.loads(org.read_text())
    live = {g["id"] for g in b["groups"]}
    dangling = {m["groupId"] for m in a["memberships"]} - live
    return not dangling, f"{len(dangling)} dead ids"


@case("DETERMINISM", "both directory backends agree on a person's id")
def backends_agree():
    """
    Actually exercise both, rather than grepping one of them for the word
    sha256: the HTTP mock could diverge and the grep would stay green.
    """
    import importlib, json as _json, urllib.request
    email = "eval.backend.check@cal.example.com"

    req = urllib.request.Request(f"{okta.BASE}/api/v1/users", method="POST",
        data=_json.dumps({"firstName": "Eval", "lastName": "Check",
                          "email": email, "department": "billing"}).encode(),
        headers={"Content-Type": "application/json"})
    try:
        http_id = _json.loads(urllib.request.urlopen(req).read())["id"]
    except urllib.error.HTTPError as e:
        if e.code != 409:
            return False, f"HTTP backend refused: {e.code}"
        http_id = next(u["id"] for u in okta.users() if u["profile"]["login"] == email)

    store = importlib.import_module("agent.okta_store")
    status, out = store.handle(ROOT / "services/mock_okta/org.json",
                               "POST", "/api/v1/users",
                               {"firstName": "Eval", "lastName": "Check",
                                "email": email, "department": "billing"})
    file_id = out.get("id") if isinstance(out, dict) else None
    if status == 409:
        file_id = http_id
    reseed()
    return http_id == file_id, f"HTTP {http_id} == file {file_id}"


# --------------------------------------------------------------- local-first
@case("LOCAL-FIRST", "every inference endpoint is on loopback")
def loopback_only():
    from agent import local_first
    off = [e for e in local_first.inference() if not e["loopback"]]
    return not off, (f"off-box: {[e['base'] for e in off]}" if off
                     else "all endpoints are localhost")


@case("LOCAL-FIRST", "the agent holds no unexpected outbound connection")
def no_egress():
    from agent import local_first
    e = local_first.egress("agent")
    if not e["checked"]:
        return None, e["note"]
    return not e["findings"], (f"{len(e['findings'])} unexpected: {e['findings'][:2]}"
                               if e["findings"] else "loopback and Slack only")


# --------------------------------------------------------------- runner
def main():
    problems = prereqs()
    if problems:
        print("\n  cannot run:")
        for p in problems:
            print(f"    - {p}")
        print()
        return 2

    print("\n  Least — evaluation harness")
    print(f"  repo: {CFG['repo']}")
    print(f"  {'':-<74}")
    print(f"  {'':<12} {'':<50} {'':<8}")

    results, section = [], None
    for sec, name, fn in CASES:
        if sec != section:
            section = sec
            print(f"\n  {sec}")
        try:
            ok, note = fn()
        except Exception as e:
            ok, note = False, f"{type(e).__name__}: {e}"
        results.append(ok)
        mark = {True: "PASS", False: "FAIL", None: "SKIP"}[ok]
        print(f"    {mark:<5} {name:<56} {note}")

    reseed()
    passed = sum(1 for r in results if r is True)
    failed = sum(1 for r in results if r is False)
    skipped = sum(1 for r in results if r is None)
    total = passed + failed
    print(f"\n  {'':-<74}")
    rate = f"{passed}/{total}" + (f"  ({skipped} skipped)" if skipped else "")
    pct = f"{100*passed/total:.0f}%" if total else "-"
    print(f"  {rate}   {pct}\n")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
