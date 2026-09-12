"""
The baseline: what happens TODAY.

A manager does not compute a team median. They point at the nearest senior
person and say "give her what Marcus has." The new hire therefore inherits
everything that person accumulated over three years -- including the parts
nobody uses and the parts nobody can explain.

That inheritance IS the problem this product exists to fix, so the baseline
models it literally.
"""
import datetime as dt
from . import okta

def _parse(s): return dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%S.000Z")

def pick_donor(team):
    """Whoever a manager would actually point at: the longest-tenured teammate."""
    members = okta.team_members(team)
    if not members: return None
    return min(members, key=lambda u: _parse(u["created"]))

def clone_a_teammate(team):
    donor = pick_donor(team)
    if not donor:
        return {"team": team, "grants": [], "donor": None, "justified": 0, "typical_days": 3}
    grants = sorted(g["profile"]["name"] for g in okta.user_groups(donor["id"]))
    sens   = {g["profile"]["name"]: g.get("_sensitivity", 0) for g in okta.groups()}
    return {
        "team": team,
        "donor": f'{donor["profile"]["firstName"]} {donor["profile"]["lastName"]}',
        "donor_email": donor["profile"]["email"],
        "grants": grants,
        "elevated": [g for g in grants if sens.get(g, 0) >= 1],
        "justified": 0,
        "typical_days": 3,
    }

if __name__ == "__main__":
    import sys, json
    print(json.dumps(clone_a_teammate(sys.argv[1] if len(sys.argv) > 1 else "billing"), indent=2))
