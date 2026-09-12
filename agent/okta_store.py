"""
The Okta Management API answered from a local file.

Inside the NemoClaw sandbox the mock Okta HTTP server cannot run: FastAPI and
pydantic_core have no wheel for the sandbox's Python 3.13, and a sandbox cannot
reach a host service on loopback. So when config.yaml says

    okta: file:services/mock_okta/org.json

agent/okta.py routes every request here instead of over HTTP. Same paths, same
methods, same JSON shapes as services/mock_okta/app.py, standard library only.
"""
import json, os, re, time, pathlib, datetime as dt
from urllib.parse import urlparse, parse_qs

def _now(): return dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z")
def _pub(u): return {k: v for k, v in u.items() if not k.startswith("_")}

def _load(p):
    for i in range(4):
        try: return json.loads(p.read_text())
        except json.JSONDecodeError:
            if i == 3: raise
            time.sleep(0.3)

def _save(p, d):
    tmp = p.with_suffix(".json.tmp")          # atomic, same as the HTTP server
    tmp.write_text(json.dumps(d, indent=2))
    os.replace(tmp, p)

def _log(d, event, actor, targets):
    d["logs"].append({"uuid": f"ev{len(d['logs']):09d}", "published": _now(),
                      "eventType": event, "actor": actor, "target": targets})

def handle(file, method, url, body=None):
    """Return (status, json) for one Okta API request."""
    p = pathlib.Path(file)
    u = urlparse(url); q = {k: v[0] for k, v in parse_qs(u.query).items()}
    path, d = u.path, _load(p)
    user = lambda uid: next((x for x in d["users"] if x["id"] == uid), None)

    if method == "GET" and path == "/api/v1/users":
        us = d["users"]
        if q.get("q"): us = [x for x in us if q["q"].lower() in json.dumps(x["profile"]).lower()]
        return 200, [_pub(x) for x in us[:int(q.get("limit", 200))]]

    if method == "POST" and path == "/api/v1/users":
        b = body or {}
        email = b.get("email") or f'{b["firstName"].lower()}.{b["lastName"].lower()}@cal.example.com'
        uid = "00u" + str(abs(hash(email)) % 10**8).zfill(8)
        if user(uid): return 409, {"error": "already exists"}
        new = {"id": uid, "status": "STAGED", "created": _now(),
               "profile": {"firstName": b["firstName"], "lastName": b["lastName"],
                           "email": email, "login": email, "title": "Software Engineer",
                           "department": b.get("department") or "billing",
                           "startDate": b.get("startDate") or "2026-09-15",
                           "manager": b.get("manager") or "sarah.chen@cal.example.com"},
               "_factors": []}
        d["users"].append(new)
        _log(d, "user.lifecycle.create", {"id": "hr-system", "type": "Application"},
             [{"id": uid, "type": "User"}])
        _save(p, d)
        return 201, _pub(new)

    m = re.fullmatch(r"/api/v1/users/([^/]+)(/groups|/factors)?", path)
    if m:
        x = user(m.group(1))
        if not x: return 404, {"error": "user not found"}
        if m.group(2) is None and method == "GET": return 200, _pub(x)
        if m.group(2) == "/groups" and method == "GET":
            gids = {mm["groupId"] for mm in d["memberships"] if mm["userId"] == x["id"]}
            return 200, [g for g in d["groups"] if g["id"] in gids]
        if m.group(2) == "/factors" and method == "GET":
            return 200, x.get("_factors", [])
        if m.group(2) == "/factors" and method == "POST":
            ft = q.get("factorType", "push")
            x.setdefault("_factors", [])
            if not any(f["factorType"] == ft for f in x["_factors"]):
                x["_factors"].append({"factorType": ft, "provider": "OKTA",
                                      "status": "ACTIVE", "created": _now()})
                _log(d, "user.mfa.factor.activate", {"id": x["id"], "type": "User"},
                     [{"id": x["id"], "type": "User"}])
                _save(p, d)
            return 200, x["_factors"]

    if method == "GET" and path == "/api/v1/groups":
        return 200, d["groups"]

    m = re.fullmatch(r"/api/v1/groups/([^/]+)/users(?:/([^/]+))?", path)
    if m:
        gid, uid = m.group(1), m.group(2)
        if uid is None and method == "GET":
            uids = {mm["userId"] for mm in d["memberships"] if mm["groupId"] == gid}
            return 200, [_pub(x) for x in d["users"] if x["id"] in uids]
        if uid and method == "PUT":
            if not any(g["id"] == gid for g in d["groups"]): return 404, {"error": "group not found"}
            if not user(uid): return 404, {"error": "user not found"}
            if not any(mm["userId"] == uid and mm["groupId"] == gid for mm in d["memberships"]):
                b = body or {}
                d["memberships"].append({"userId": uid, "groupId": gid, "granted": _now(),
                                         "justification": b.get("justification"),
                                         "approvedBy": b.get("approvedBy")})
                _log(d, "group.user_membership.add", {"id": "agent", "type": "Application"},
                     [{"id": gid, "type": "UserGroup"}, {"id": uid, "type": "User"}])
                _save(p, d)
            return 204, None
        if uid and method == "DELETE":
            before = len(d["memberships"])
            d["memberships"] = [mm for mm in d["memberships"]
                                if not (mm["userId"] == uid and mm["groupId"] == gid)]
            if len(d["memberships"]) == before: return 404, {"error": "membership not found"}
            _log(d, "group.user_membership.remove", {"id": "agent", "type": "Application"},
                 [{"id": gid, "type": "UserGroup"}, {"id": uid, "type": "User"}])
            _save(p, d)
            return 204, None

    if method == "GET" and path == "/api/v1/logs":
        ls = d["logs"]
        if q.get("since"): ls = [l for l in ls if l["published"] >= q["since"]]
        if q.get("filter"): ls = [l for l in ls if q["filter"] in json.dumps(l)]
        return 200, ls[-int(q.get("limit", 5000)):]

    return 404, {"error": f"no route {method} {path}"}
