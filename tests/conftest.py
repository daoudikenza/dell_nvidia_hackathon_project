"""
Offline fixtures.

The directory is replaced at the `agent.okta` boundary, so every test here runs
with no mock Okta on :8081 and no network. That is deliberate: the approval
refusals are the security control, and a control that can only be tested when a
service happens to be up will not be tested.
"""
import pytest

from agent import okta, execute
from agent.config import CFG


NADIA = {"id": "00uNEWHIRE01", "status": "STAGED",
         "profile": {"firstName": "Nadia", "lastName": "Rahimi",
                     "email": "nadia.rahimi@cal.example.com",
                     "login": "nadia.rahimi@cal.example.com",
                     "department": "billing", "manager": "sarah.chen@cal.example.com"}}
SARAH = {"id": "00u00000000", "status": "ACTIVE",
         "profile": {"firstName": "Sarah", "lastName": "Chen",
                     "email": "sarah.chen@cal.example.com",
                     "login": "sarah.chen@cal.example.com",
                     "department": "billing"}}
MARCUS = {"id": "00u00000001", "status": "ACTIVE",
          "profile": {"firstName": "Marcus", "lastName": "Okafor",
                      "email": "marcus.okafor@cal.example.com",
                      "login": "marcus.okafor@cal.example.com",
                      "department": "billing"}}

GROUPS = [{"id": "grp00000001", "profile": {"name": "eng-billing"}},
          {"id": "grp00000002", "profile": {"name": "db-staging-read"}},
          {"id": "grp00000003", "profile": {"name": "db-prod-write"}}]


@pytest.fixture
def directory(monkeypatch):
    """A tiny in-memory Okta. Returns a handle the test can inspect and steer."""
    state = {"users": [NADIA, SARAH, MARCUS], "factors": {}, "assigned": []}

    def users():
        return state["users"]

    def factors(uid):
        return state["factors"].get(uid, [])

    def assign(gid, uid, why=None, by=None):
        state["assigned"].append({"gid": gid, "uid": uid, "why": why, "by": by})
        return 204

    def gid_by_name(name):
        return next((g["id"] for g in GROUPS if g["profile"]["name"] == name), None)

    def user_groups(uid):
        """Derived from what was assigned, so before/after counts are real."""
        held = {a["gid"] for a in state["assigned"] if a["uid"] == uid}
        return [g for g in GROUPS if g["id"] in held]

    monkeypatch.setattr(okta, "user_groups", user_groups)
    monkeypatch.setattr(okta, "users", users)
    monkeypatch.setattr(okta, "factors", factors)
    monkeypatch.setattr(okta, "assign", assign)
    monkeypatch.setattr(okta, "gid_by_name", gid_by_name)
    monkeypatch.setattr(okta, "groups", lambda fresh=False: GROUPS)
    monkeypatch.setattr(execute.okta, "factors", factors)

    state["enroll"] = lambda uid: state["factors"].__setitem__(
        uid, [{"factorType": "push", "provider": "OKTA", "status": "ACTIVE"}])
    return state


PACKET = """---
subject: nadia.rahimi@cal.example.com
name: Nadia Rahimi
team: billing
start_date: 2026-09-14
manager: sarah.chen@cal.example.com
generated: 2026-09-12T14:00:00Z
status: awaiting-approval
access:
  derived:
    - {group: db-staging-read, because: "packages/prisma/auto-migrations.ts:21"}
  conventional:
    - {group: eng-billing, because: "8/9 peers active in last 30d"}
  declined:
    - {group: db-prod-write, because: "production-level access with no code path"}
---

# Nadia Rahimi — billing team
"""


@pytest.fixture
def packet(tmp_path, monkeypatch):
    """A packet on disk, inside the directory approve() is willing to read from."""
    packets = tmp_path / "packets"
    packets.mkdir()
    monkeypatch.setitem(CFG, "_packets", packets)
    monkeypatch.setitem(CFG, "_root", tmp_path)
    p = packets / "nadia-rahimi.md"
    p.write_text(PACKET)
    return p
