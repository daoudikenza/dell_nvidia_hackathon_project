#!/usr/bin/env python3
"""
MCP server exposing Least's capabilities as tools OpenClaw's agent can call.

This is the bridge that turns a CLI into an agent. Without it a human picks the
command; with it the model decides -- someone says "Nadia starts Monday" and the
agent works out that it needs to scan the repo, check MFA, then build a packet.

Speaks MCP over stdio (JSON-RPC 2.0). No dependencies, so it runs inside the
OpenShell sandbox without installing anything.

Register with:  mcporter add least -- python3 /path/to/mcp/server.py
"""
import sys, json, pathlib, traceback
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

PROTOCOL = "2024-11-05"

TOOLS = [
  {"name": "current_practice",
   "description": ("What a new hire would be granted TODAY, by a manager cloning a "
                   "senior teammate's permissions. Use this to establish the baseline "
                   "before proposing anything."),
   "inputSchema": {"type":"object","properties":{"team":{"type":"string"}},"required":["team"]}},

  {"name": "scan_repo",
   "description": ("Scan the codebase for access the code demonstrably requires. Returns "
                   "groups with file:line citations. These are FACTS from the repository -- "
                   "never invent or paraphrase a citation."),
   "inputSchema": {"type":"object","properties":{"team":{"type":"string"}},"required":["team"]}},

  {"name": "peer_usage",
   "description": ("Groups that at least 75% of the team ACTIVELY USES (not merely holds). "
                   "Covers access that is real but not visible in code, e.g. dashboards."),
   "inputSchema": {"type":"object","properties":{"team":{"type":"string"}},"required":["team"]}},

  {"name": "check_mfa",
   "description": ("Whether a user has Okta Verify enrolled. If this fails you MUST NOT "
                   "propose or apply any grant. It is a gate, not a warning."),
   "inputSchema": {"type":"object","properties":{"user_id":{"type":"string"}},"required":["user_id"]}},

  {"name": "build_packet",
   "description": ("Produce the onboarding packet: knowledge plus a justified access "
                   "proposal. Writes a markdown file and returns a summary."),
   "inputSchema": {"type":"object","properties":{
       "user_id":{"type":"string","description":"Okta id, email, or name"},
       "team":{"type":"string"}},"required":["user_id","team"]}},

  {"name": "find_gaps",
   "description": ("Cross-check a packet: systems the onboarding prose tells the new hire "
                   "to use, that no access request covers. Run after build_packet."),
   "inputSchema": {"type":"object","properties":{"packet":{"type":"string"}},"required":["packet"]}},

  {"name": "access_drift",
   "description": ("Find grants nobody has used, ranked by blast radius. This is the "
                   "nightly job -- run it unprompted and report anything production-level."),
   "inputSchema": {"type":"object","properties":{
       "unused_days":{"type":"integer","default":90}}}},

  {"name": "apply_access",
   "description": ("Apply an APPROVED packet. Requires an approver email -- never call "
                   "this without explicit human approval in the thread."),
   "inputSchema": {"type":"object","properties":{
       "packet":{"type":"string"},"approver":{"type":"string"}},"required":["packet","approver"]}},

  {"name": "find_user",
   "description": "Look up a person by name or email. Returns their Okta id and team.",
   "inputSchema": {"type":"object","properties":{"q":{"type":"string"}},"required":["q"]}},
]

def call(name, a):
    from agent import okta, peers, gate, packet as pk, crosscheck, execute
    from agent.baseline import clone_a_teammate
    from agent.scanner import scan, TEAM_PATHS
    from agent.config import CFG

    if name == "current_practice":
        b = clone_a_teammate(a["team"])
        return {"donor": b["donor"], "n_grants": len(b["grants"]), "grants": b["grants"],
                "elevated": b["elevated"], "justified": 0, "typical_days": b["typical_days"],
                "note": "This is what happens today. Nothing here carries a justification."}

    if name == "scan_repo":
        return {"signals": scan(TEAM_PATHS.get(a["team"], []))}

    if name == "peer_usage":
        return {"conventional": peers.conventional(a["team"])}

    if name == "check_mfa":
        return gate.check(okta.resolve(a["user_id"])["id"])

    if name == "build_packet":
        p = pk.build(a["user_id"], a["team"])
        out = pk.write(p)
        return {"packet": str(out.relative_to(CFG["_root"])),
                "proposed": len(p["derived"]) + len(p["conventional"]),
                "declined": [d["group"] for d in p["declined"]],
                "gate_passed": p["gate"]["passed"], "gate_reason": p["gate"]["reason"],
                "baseline_grants": len(p["baseline"]["grants"])}

    if name == "find_gaps":
        md = (CFG["_root"] / a["packet"]).read_text()
        fm = execute.parse_frontmatter_groups(md)
        return {"gaps": crosscheck.gaps(md, set(fm["derived"]) | set(fm["conventional"]))}

    if name == "access_drift":
        from agent.drift import analyse
        org = json.loads((CFG["_root"]/"services/mock_okta/org.json").read_text())
        fs = analyse(org, a.get("unused_days", 90))
        return {"total": len(fs),
                "production": [f for f in fs if f["sensitivity"] == 2],
                "elevated":   [f for f in fs if f["sensitivity"] == 1][:5]}

    if name == "apply_access":
        md_path = CFG["_root"] / a["packet"]; md = md_path.read_text()
        fm = execute.parse_frontmatter_groups(md)
        groups = fm["derived"] + fm["conventional"]
        email = next((l.split(":",1)[1].strip() for l in md.splitlines()
                      if l.startswith("subject:")), "")
        uid = next((u["id"] for u in okta.users() if u["profile"]["login"] == email), None)
        res = execute.apply(uid, groups, a["approver"], md_path.name)
        pr  = execute.open_pr(md_path, email, groups, dry_run=True)
        return {**res, "pr_branch": pr.get("branch")}

    if name == "find_user":
        q = a["q"].lower()
        hits = [{"id": u["id"], "name": f'{u["profile"]["firstName"]} {u["profile"]["lastName"]}',
                 "email": u["profile"]["login"], "team": u["profile"].get("department"),
                 "status": u["status"]}
                for u in okta.users()
                if q in json.dumps(u["profile"]).lower()]
        return {"matches": hits[:8]}

    raise ValueError(f"unknown tool: {name}")

def send(obj):
    sys.stdout.write(json.dumps(obj) + "\n"); sys.stdout.flush()

def main():
    for line in sys.stdin:
        line = line.strip()
        if not line: continue
        try: msg = json.loads(line)
        except Exception: continue
        mid, method = msg.get("id"), msg.get("method")

        if method == "initialize":
            send({"jsonrpc":"2.0","id":mid,"result":{
                "protocolVersion": PROTOCOL,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "least", "version": "0.1.0"}}})
        elif method == "tools/list":
            send({"jsonrpc":"2.0","id":mid,"result":{"tools": TOOLS}})
        elif method == "tools/call":
            p = msg.get("params", {})
            try:
                out = call(p.get("name"), p.get("arguments") or {})
                send({"jsonrpc":"2.0","id":mid,"result":{
                    "content":[{"type":"text","text":json.dumps(out, indent=2, default=str)}]}})
            except Exception as e:
                send({"jsonrpc":"2.0","id":mid,"result":{
                    "content":[{"type":"text","text":f"ERROR {type(e).__name__}: {e}\n"
                                                     f"{traceback.format_exc()[-500:]}"}],
                    "isError": True}})
        elif mid is not None:
            send({"jsonrpc":"2.0","id":mid,"error":{"code":-32601,"message":method}})

if __name__ == "__main__":
    main()
