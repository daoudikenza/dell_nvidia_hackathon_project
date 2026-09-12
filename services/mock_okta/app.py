"""
Mock Okta — faithful to the real Okta Management API surface.

Deliberately does NOT expose any "find unused access" endpoint. Real Okta has
no such thing; deriving that from raw memberships + system logs is the product.
Agent code written against this runs unchanged against a real tenant.

  uvicorn services.mock_okta.app:app --port 8081
"""
import json, os, pathlib, datetime as dt
from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel

DB = pathlib.Path(__file__).parent / "org.json"
app = FastAPI(title="mock-okta", version="1.0")

def load():  return json.loads(DB.read_text())

def save(d):
    """
    Atomic write.

    write_text() truncates then writes, so a concurrent reader (the daemon polls
    this same file) can observe a half-written document and fail with a JSON
    delimiter error. Writing to a temp file in the same directory and renaming
    makes the swap atomic - a reader sees either the old file or the new one,
    never a partial one.
    """
    tmp = DB.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(d, indent=2))
    os.replace(tmp, DB)
def now():   return dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z")

def pub(u):   # strip internal fields, mirror real Okta user shape
    return {k: v for k, v in u.items() if not k.startswith("_")}

# ---------- users ----------
@app.get("/api/v1/users")
def list_users(q: str | None = None, limit: int = 200):
    us = load()["users"]
    if q:
        ql = q.lower()
        us = [u for u in us if ql in json.dumps(u["profile"]).lower()]
    return [pub(u) for u in us[:limit]]

@app.get("/api/v1/users/{uid}")
def get_user(uid: str):
    u = next((x for x in load()["users"] if x["id"] == uid), None)
    if not u: raise HTTPException(404, "user not found")
    return pub(u)

@app.get("/api/v1/users/{uid}/groups")
def user_groups(uid: str):
    d = load()
    gids = {m["groupId"] for m in d["memberships"] if m["userId"] == uid}
    return [g for g in d["groups"] if g["id"] in gids]

@app.get("/api/v1/users/{uid}/factors")
def user_factors(uid: str):
    """Okta Verify enrollment. The agent gates every grant on this."""
    u = next((x for x in load()["users"] if x["id"] == uid), None)
    if not u: raise HTTPException(404, "user not found")
    return u.get("_factors", [])

@app.post("/api/v1/users/{uid}/factors", status_code=200)
def enroll_factor(uid: str, factorType: str = "push"):
    """
    Enrol an Okta Verify factor. Real Okta does this via the enrollment flow on
    the person's phone; here it stands in for Nadia completing setup on her
    first morning, which is what unblocks the gate.
    """
    d = load()
    u = next((x for x in d["users"] if x["id"] == uid), None)
    if not u: raise HTTPException(404, "user not found")
    u.setdefault("_factors", [])
    if not any(f["factorType"] == factorType for f in u["_factors"]):
        u["_factors"].append({"factorType": factorType, "provider": "OKTA",
                              "status": "ACTIVE", "created": now()})
        d["logs"].append({"uuid": f"ev{len(d['logs']):09d}", "published": now(),
                          "eventType": "user.mfa.factor.activate",
                          "actor": {"id": uid, "type": "User"},
                          "target": [{"id": uid, "type": "User"}]})
        save(d)
    return u["_factors"]

class NewHire(BaseModel):
    firstName: str
    lastName: str
    email: str | None = None
    department: str = "billing"
    startDate: str | None = None
    manager: str | None = None

@app.post("/api/v1/users", status_code=201)
def create_user(h: NewHire):
    """
    HR provisions an identity. This is the upstream event Least reacts to --
    a person exists in the directory with no groups and no MFA, and the agent
    has to notice and prepare for them without anyone asking.
    """
    d = load()
    email = h.email or f"{h.firstName.lower()}.{h.lastName.lower()}@cal.example.com"
    uid = "00u" + str(abs(hash(email)) % 10**8).zfill(8)
    if any(u["id"] == uid for u in d["users"]): raise HTTPException(409, "already exists")
    u = {"id": uid, "status": "STAGED", "created": now(),
         "profile": {"firstName": h.firstName, "lastName": h.lastName,
                     "email": email, "login": email, "title": "Software Engineer",
                     "department": h.department,
                     "startDate": h.startDate or "2026-09-15",
                     "manager": h.manager or "sarah.chen@cal.example.com"},
         "_factors": []}
    d["users"].append(u)
    d["logs"].append({"uuid": f"ev{len(d['logs']):09d}", "published": now(),
                      "eventType": "user.lifecycle.create",
                      "actor": {"id": "hr-system", "type": "Application"},
                      "target": [{"id": uid, "type": "User"}]})
    save(d)
    return pub(u)

# ---------- groups ----------
@app.get("/api/v1/groups")
def list_groups(): return load()["groups"]

@app.get("/api/v1/groups/{gid}/users")
def group_users(gid: str):
    d = load()
    uids = {m["userId"] for m in d["memberships"] if m["groupId"] == gid}
    return [pub(u) for u in d["users"] if u["id"] in uids]

class GrantNote(BaseModel):
    justification: str | None = None
    approvedBy: str | None = None

@app.put("/api/v1/groups/{gid}/users/{uid}", status_code=204)
def assign(gid: str, uid: str, note: GrantNote | None = None):
    d = load()
    if not any(g["id"] == gid for g in d["groups"]): raise HTTPException(404, "group not found")
    if not any(u["id"] == uid for u in d["users"]):  raise HTTPException(404, "user not found")
    if any(m["userId"] == uid and m["groupId"] == gid for m in d["memberships"]):
        return Response(status_code=204)
    d["memberships"].append({"userId": uid, "groupId": gid, "granted": now(),
                             "justification": (note.justification if note else None),
                             "approvedBy": (note.approvedBy if note else None)})
    d["logs"].append({"uuid": f"ev{len(d['logs']):09d}", "published": now(),
                      "eventType": "group.user_membership.add",
                      "actor": {"id": "agent", "type": "Application"},
                      "target": [{"id": gid, "type": "UserGroup"}, {"id": uid, "type": "User"}]})
    save(d); return Response(status_code=204)

@app.delete("/api/v1/groups/{gid}/users/{uid}", status_code=204)
def revoke(gid: str, uid: str):
    d = load()
    before = len(d["memberships"])
    d["memberships"] = [m for m in d["memberships"]
                        if not (m["userId"] == uid and m["groupId"] == gid)]
    if len(d["memberships"]) == before: raise HTTPException(404, "membership not found")
    d["logs"].append({"uuid": f"ev{len(d['logs']):09d}", "published": now(),
                      "eventType": "group.user_membership.remove",
                      "actor": {"id": "agent", "type": "Application"},
                      "target": [{"id": gid, "type": "UserGroup"}, {"id": uid, "type": "User"}]})
    save(d); return Response(status_code=204)

# ---------- system log ----------
@app.get("/api/v1/logs")
def logs(since: str | None = None, filter: str | None = None, limit: int = 5000):
    ls = load()["logs"]
    if since: ls = [l for l in ls if l["published"] >= since]
    if filter: ls = [l for l in ls if filter in json.dumps(l)]
    return ls[-limit:]

@app.get("/health")
def health():
    d = load()
    return {"ok": True, "users": len(d["users"]), "groups": len(d["groups"]),
            "memberships": len(d["memberships"]), "logs": len(d["logs"])}
