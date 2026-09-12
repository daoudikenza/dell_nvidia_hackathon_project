"""
Least CLI.  python -m agent <command>

  status                      which inference backend is answering
  baseline  <team>            what cloning a teammate would grant (the problem)
  scan      <team>            access signals derived from the repo
  peers     <team>            groups the team actually uses
  onboard   <who> <team>      build the packet (name, email or id)
  brief     <who> <team>      the manager-facing answer, sized for chat
  enroll    <who>             simulate the person completing Okta Verify setup
  stage     <first> <last> [team]   simulate HR provisioning a new hire
  crosscheck <packet.md>      docs-vs-access gaps
  approve   <packet.md> <approver-email> [--live]
  drift                       the always-on scan
  journal                     what the agent did while nobody was watching

  -v / --verbose              show the agent's work as it happens
"""
import sys, json, pathlib

def main(argv):
    if not argv or argv[0] in ("-h", "--help"): print(__doc__); return 0
    from . import trace
    if "-v" in argv or "--verbose" in argv:
        trace.on()
        argv = [a for a in argv if a not in ("-v", "--verbose")]
    cmd, rest = argv[0], argv[1:]

    if cmd == "status":
        from . import llm, okta
        from .config import CFG
        name, kind, model, errs = llm.which(verbose=True)
        if kind:
            print(f"inference : {kind}  {model}  ({name})")
        else:
            print("inference : NONE REACHABLE")
            for n, k, base, m, err in errs:
                print(f"            {n:<8} {k:<7} {base}")
                print(f"                     model={m}")
                print(f"                     {err}")
            print()
            print("  what those endpoints actually serve:")
            for n in ("primary", "fallback"):
                base = CFG["inference"][n]["base"]
                url, body = llm.probe(base, CFG["inference"][n].get("api_key"))
                if url:
                    ids = []
                    if isinstance(body, dict):
                        ids = [d.get("id") or d.get("name")
                               for d in (body.get("data") or body.get("models") or [])]
                    print(f"            {url} -> {', '.join(i for i in ids if i) or 'responded'}")
                else:
                    print(f"            {base} -> nothing responding")
        try:    print(f"okta      : ok — {len(okta.users())} users, {len(okta.groups())} groups")
        except Exception as e: print(f"okta      : UNREACHABLE — {e}")
        from .config import CFG
        print(f"repo      : {'ok' if CFG['repo'].exists() else 'MISSING'} — {CFG['repo']}")
        return 0

    if cmd == "baseline":
        from .baseline import clone_a_teammate
        b = clone_a_teammate(rest[0])
        print(f'\n  "just give her what {b["donor"].split()[0]} has"')
        print(f'  {len(b["grants"])} grants · 0 justified · ~{b["typical_days"]} days\n')
        for g in b["grants"]:
            print("     ", g, " <-- ELEVATED" if g in b["elevated"] else "")
        return 0

    if cmd == "scan":
        from .scanner import scan, TEAM_PATHS
        for h in scan(TEAM_PATHS.get(rest[0], [])):
            print(f'\n  {h["group"]}')
            for c in h["citations"]: print(f'     {c["file"]}:{c["line"]}  ({c["var"]})')
        return 0

    if cmd == "peers":
        from .peers import conventional
        for c in conventional(rest[0]): print(f'  {c["group"]:<24} {c["because"]}')
        return 0

    if cmd == "onboard":
        from . import packet, okta
        uid, team = rest[0], rest[1]
        try:
            who = okta.resolve(uid)
        except LookupError as e:
            print(f"\n  {e}\n")
            staged = [u for u in okta.users() if u["status"] == "STAGED"]
            if staged:
                print("  people awaiting onboarding:")
                for u in staged:
                    print(f'     {u["profile"]["firstName"]} {u["profile"]["lastName"]}'
                          f'  ({u["profile"].get("department","-")})  id={u["id"]}')
            return 1
        print(f'\n  {who["profile"]["firstName"]} {who["profile"]["lastName"]}'
              f'  <{who["profile"]["login"]}>  [{who["id"]}]')
        p = packet.build(who["id"], team, use_llm="--no-llm" not in rest)
        out = packet.write(p)
        n = len(p["derived"]) + len(p["conventional"])
        print(f'\n  packet written: {out}')
        print(f'  {n} proposed · {len(p["declined"])} declined · '
              f'gate {"PASS" if p["gate"]["passed"] else "BLOCK"}')
        if not p["gate"]["passed"]:
            print(f'  {p["gate"]["status"]}: {p["gate"]["reason"]}')
        return 0

    if cmd == "stage":
        # Simulates HR provisioning someone. The agent is NOT told -- the loop
        # has to notice on its next tick. This is the live proof of autonomy.
        from . import okta
        first, last = rest[0], rest[1]
        team = rest[2] if len(rest) > 2 else "billing"
        u = okta.create_user(first, last, team)
        print(f'\n  HR provisioned {u["profile"]["firstName"]} {u["profile"]["lastName"]}'
              f'  <{u["profile"]["login"]}>')
        print(f'  team {u["profile"]["department"]} · starts {u["profile"]["startDate"]}'
              f' · status {u["status"]} · 0 groups · no MFA')
        print(f'\n  Nobody has told the agent. Watch the loop.\n')
        return 0

    if cmd == "enroll":
        from . import okta, gate
        u = okta.resolve(rest[0])
        prof = u["profile"]
        okta.enroll_factor(u["id"])
        g = gate.check(u["id"], person=f'{prof["firstName"]} {prof["lastName"]}',
                       handle=prof["login"])
        if g["passed"]:
            print(f'  {prof["firstName"]} {prof["lastName"]} — Okta Verify ENROLLED '
                  f'({", ".join(g["factors"])})')
            return 0
        print(f'  {prof["firstName"]} {prof["lastName"]} — still blocked')
        print(f'  {g["reason"]}')
        return 1

    if cmd == "brief":
        from . import packet, brief
        p = packet.build(rest[0], rest[1], use_llm="--no-llm" not in rest)
        out = packet.write(p)
        print()
        print(brief.render(p, str(out.relative_to(p["user"] and __import__("pathlib")
              .Path(out).parent.parent))))
        return 0

    if cmd == "crosscheck":
        from .crosscheck import gaps
        from .execute import parse_frontmatter_groups
        md = pathlib.Path(rest[0]).read_text()
        fm = parse_frontmatter_groups(md)
        proposed = set(fm["derived"]) | set(fm["conventional"])
        found = gaps(md, proposed)
        if not found: print("  no gaps"); return 0
        for g in found: print(f'  GAP  line {g["line"]}: {g["note"]}')
        return 0

    if cmd == "approve":
        from . import execute
        # Same chokepoint the Slack button and the MCP tool go through, so the
        # gate, the self-approval refusal and the approver check are identical
        # on every surface rather than reimplemented per caller.
        who = execute.Approver(email=rest[1], source="cli", display=rest[1])
        try:
            res = execute.approve(rest[0], who)
        except execute.Refused as r:
            print(f'\n  REFUSED ({r.code})')
            print(f'  {r.message}\n')
            return 1
        print(f'  subject  : {res["name"]} <{res["subject"]}>')
        print(f'  approver : {res["approver_email"]}')
        print(f'  applied  : {", ".join(res["applied"]) or "-"}  '
              f'({res["before"]} -> {res["after"]} groups)')
        if res["failed"]: print(f'  failed   : {res["failed"]}')
        pr = execute.open_pr(res["path"], res["subject"], res["applied"],
                             dry_run="--live" not in rest)
        print(f'  PR       : {"DRAFTED, NOT FILED — " if pr.get("dry_run") else ""}'
              f'branch {pr.get("branch","-")}')
        return 0

    if cmd == "journal":
        from .config import CFG
        j = CFG["_root"] / "loop" / "journal.md"
        if not j.exists():
            print("  nothing yet — start the loop:  python3 loop/daemon.py 900")
            return 0
        print(j.read_text())
        return 0

    if cmd == "drift":
        import runpy; runpy.run_module("agent.drift", run_name="__main__"); return 0

    print(f"unknown command: {cmd}\n"); print(__doc__); return 1

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
