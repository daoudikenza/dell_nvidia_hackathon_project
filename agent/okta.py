"""
Okta client. Written against the real Management API surface, so pointing it at
a real tenant is a base-URL change plus an auth header.
"""
import json, urllib.request
from .config import CFG

BASE = CFG["okta"]

# Everything we talk to is on this machine. If the host has http_proxy /
# https_proxy set (common on managed and event networks), urllib will route
# even localhost through it and the handshake fails as
# [SSL: WRONG_VERSION_NUMBER]. An explicit empty ProxyHandler opts out.
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))

def _get(path):
    with _OPENER.open(f"{BASE}{path}", timeout=30) as r:
        return json.loads(r.read())

def _send(path, method, body=None):
    req = urllib.request.Request(f"{BASE}{path}", method=method,
        data=json.dumps(body).encode() if body else None,
        headers={"Content-Type": "application/json"})
    with _OPENER.open(req, timeout=30) as r:
        return r.status

def users():                 return _get("/api/v1/users")
def user(uid):               return _get(f"/api/v1/users/{uid}")
def groups():                return _get("/api/v1/groups")
def user_groups(uid):        return _get(f"/api/v1/users/{uid}/groups")
def factors(uid):            return _get(f"/api/v1/users/{uid}/factors")
def group_users(gid):        return _get(f"/api/v1/groups/{gid}/users")
def logs(since=None):        return _get(f"/api/v1/logs" + (f"?since={since}" if since else ""))
def assign(gid, uid, why=None, by=None):
    return _send(f"/api/v1/groups/{gid}/users/{uid}", "PUT",
                 {"justification": why, "approvedBy": by})
def revoke(gid, uid):        return _send(f"/api/v1/groups/{gid}/users/{uid}", "DELETE")

def gid_by_name(name):
    return next((g["id"] for g in groups() if g["profile"]["name"] == name), None)
def name_by_gid(gid):
    return next((g["profile"]["name"] for g in groups() if g["id"] == gid), gid)
def team_members(team):
    return [u for u in users() if u["profile"].get("department") == team]
