"""
Access drift detector.

Deterministic. No LLM. Joins Okta memberships against the system log to find
grants nobody is using, then ranks by blast radius. The model's job comes
later: explaining each finding and drafting the revocation for a human.

This is the always-on loop — it runs nightly, not once at onboarding.
"""
import json, datetime as dt, pathlib, sys
from collections import defaultdict

NOW = dt.datetime(2026, 9, 12, 9, 0, 0)
SENSITIVITY = {0: "routine", 1: "elevated", 2: "PRODUCTION"}

def parse(s): return dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%S.000Z")

def analyse(org, unused_days=90):
    gname = {g["id"]: g["profile"]["name"] for g in org["groups"]}
    gsens = {g["id"]: g.get("_sensitivity", 0) for g in org["groups"]}
    user  = {u["id"]: u for u in org["users"]}

    last_used = defaultdict(lambda: None)
    for l in org["logs"]:
        if l["eventType"] != "group.privilege.used": continue
        uid = l["actor"]["id"]
        for t in l["target"]:
            if t["type"] == "UserGroup":
                k = (uid, t["id"]); ts = parse(l["published"])
                if last_used[k] is None or ts > last_used[k]: last_used[k] = ts

    findings = []
    for m in org["memberships"]:
        uid, gid = m["userId"], m["groupId"]
        if uid not in user: continue
        used = last_used[(uid, gid)]
        idle = (NOW - used).days if used else (NOW - parse(m["granted"])).days
        if used is None or idle >= unused_days:
            u = user[uid]
            findings.append({
                "user":  u["profile"]["email"],
                "name":  f'{u["profile"]["firstName"]} {u["profile"]["lastName"]}',
                "team":  u["profile"]["department"],
                "group": gname[gid], "groupId": gid, "userId": uid,
                "sensitivity": gsens[gid],
                "granted_days_ago": (NOW - parse(m["granted"])).days,
                "never_used": used is None,
                "idle_days": idle,
                "service_account": u["profile"].get("title") == "Service Account",
            })
    # blast radius first, then how long it has been sitting there
    findings.sort(key=lambda f: (-f["sensitivity"], -f["idle_days"]))
    return findings

def coverage(org):
    """What fraction of granted privilege is actually exercised?"""
    total = len(org["memberships"])
    stale = len(analyse(org))
    return total, stale, round(100 * stale / total, 1)

if __name__ == "__main__":
    org = json.loads((pathlib.Path(__file__).parent.parent /
                      "services/mock_okta/org.json").read_text())
    fs = analyse(org)
    total, stale, pct = coverage(org)

    print(f"\n  ACCESS DRIFT REPORT — {NOW:%Y-%m-%d}")
    print(f"  {'='*68}")
    print(f"  {total} active grants, {stale} unused for 90+ days  ->  {pct}% over-provisioned\n")

    for label, sens in (("PRODUCTION ACCESS", 2), ("ELEVATED", 1)):
        sel = [f for f in fs if f["sensitivity"] == sens]
        if not sel: continue
        print(f"  {label}  ({len(sel)})")
        for f in sel:
            tag = "NEVER USED" if f["never_used"] else f'idle {f["idle_days"]}d'
            svc = "  [service account]" if f["service_account"] else ""
            print(f"    {f['group']:<22} {f['name']:<20} {f['team']:<11} {tag}{svc}")
        print()

    routine = [f for f in fs if f["sensitivity"] == 0]
    print(f"  ROUTINE  ({len(routine)} unused — lower priority)")
    for f in routine[:5]:
        print(f"    {f['group']:<22} {f['name']:<20} {f['team']}")
    if len(routine) > 5: print(f"    ... and {len(routine)-5} more")
