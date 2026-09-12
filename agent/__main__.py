"""
Least CLI.  python -m agent <command>

  status                      which inference backend is answering
  baseline  <team>            what cloning a teammate would grant (the problem)
  scan      <team>            access signals derived from the repo
  peers     <team>            groups the team actually uses
  onboard   <user_id> <team>  build the packet
  crosscheck <packet.md>      docs-vs-access gaps
  approve   <packet.md> <approver-email> [--live]
  drift                       the always-on scan
"""
import sys, json, pathlib

def main(argv):
    if not argv or argv[0] in ("-h", "--help"): print(__doc__); return 0
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
        if not p["gate"]["passed"]: print(f'  {p["gate"]["reason"]}')
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
        from .execute import parse_frontmatter_groups, apply, open_pr
        from . import okta
        path = pathlib.Path(rest[0]); md = path.read_text()
        approver = rest[1]
        fm = parse_frontmatter_groups(md)
        groups = fm["derived"] + fm["conventional"]
        email = next((l.split(":",1)[1].strip() for l in md.splitlines()
                      if l.startswith("subject:")), "")
        uid = next((u["id"] for u in okta.users() if u["profile"]["login"] == email), None)
        res = apply(uid, groups, approver, path.name)
        print(f'  applied  : {", ".join(res["applied"]) or "-"}')
        if res["failed"]: print(f'  failed   : {res["failed"]}')
        pr = open_pr(path, email, groups, dry_run="--live" not in rest)
        print(f'  PR       : {"DRY RUN — " if pr.get("dry_run") else ""}branch {pr.get("branch","-")}')
        return 0

    if cmd == "drift":
        import runpy; runpy.run_module("agent.drift", run_name="__main__"); return 0

    print(f"unknown command: {cmd}\n"); print(__doc__); return 1

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
