"""
Peer usage intersection -- the answer to "not all access is in the code".

Critically: we look at what peers USE, not what they are GRANTED. Using grants
would propagate the org's existing over-provisioning into every new hire. Using
usage means a dormant db-prod-write that one teammate holds never reaches quorum.
"""
import datetime as dt
from collections import defaultdict
from . import okta
from .config import CFG

def _parse(s): return dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%S.000Z")

def conventional(team, now=None):
    now = now or dt.datetime(2026, 9, 12, 9, 0, 0)
    window = CFG["thresholds"]["peer_window_days"]
    quorum = CFG["thresholds"]["peer_quorum"]
    members = {u["id"] for u in okta.team_members(team)}
    if not members: return []

    cutoff = now - dt.timedelta(days=window)
    used = defaultdict(set)                      # group -> users who actually used it
    for l in okta.logs():
        if l["eventType"] != "group.privilege.used": continue
        uid = l["actor"]["id"]
        if uid not in members or _parse(l["published"]) < cutoff: continue
        for t in l["target"]:
            if t["type"] == "UserGroup": used[t["id"]].add(uid)

    n = len(members)
    out = []
    for gid, who in used.items():
        frac = len(who) / n
        if frac >= quorum:
            out.append({"group": okta.name_by_gid(gid), "peers_using": len(who),
                        "team_size": n, "fraction": round(frac, 2),
                        "because": f"{len(who)}/{n} peers active in last {window}d"})
    return sorted(out, key=lambda x: -x["fraction"])

if __name__ == "__main__":
    import sys, json
    print(json.dumps(conventional(sys.argv[1] if len(sys.argv) > 1 else "billing"), indent=2))
