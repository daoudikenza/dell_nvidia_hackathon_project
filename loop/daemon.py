"""
The always-on loop.

This is the difference between a tool someone runs and an agent that works.
It is not a scheduler that prints -- each tick it inspects the world and
CHANGES something when the world changed:

  * repo moved       -> regenerate every packet whose documented area shifted
  * access unused    -> record the finding, draft the revocation
  * new hire STAGED  -> build their packet before anyone asks

Everything it does is appended to loop/journal.md, so at any moment you can
show what it did while nobody was watching.
"""
import sys, time, json, subprocess, datetime as dt, pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from agent.config import CFG
from agent.drift import analyse
from agent import okta, packet as pk, trace

STATE   = CFG["_root"] / "loop" / ".state.json"
JOURNAL = CFG["_root"] / "loop" / "journal.md"

def now():   return dt.datetime.utcnow()
def stamp(): return now().strftime("%Y-%m-%d %H:%M:%SZ")
def load():  return json.loads(STATE.read_text()) if STATE.exists() else {}
def save(d): STATE.write_text(json.dumps(d, indent=2))

def journal(kind, msg):
    JOURNAL.parent.mkdir(exist_ok=True)
    head = "" if JOURNAL.exists() else "# Least — what the agent did unprompted\n\n"
    with JOURNAL.open("a") as f:
        f.write(f"{head}- `{stamp()}` **{kind}** — {msg}\n")
    print(f"  {stamp()}  {kind:<9} {msg}", flush=True)

def repo_head():
    r = subprocess.run(["git", "-C", str(CFG["repo"]), "rev-parse", "HEAD"],
                       capture_output=True, text=True)
    return r.stdout.strip()[:12]

def read_org(attempts=4):
    """The API server rewrites this file; retry rather than die on a torn read."""
    path = CFG["_root"] / "services/mock_okta/org.json"
    for i in range(attempts):
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError:
            if i == attempts - 1: raise
            time.sleep(0.4)

def tick(st):
    acted = False

    # 1. production-level access nobody is using
    org = read_org()
    fs   = analyse(org, CFG["thresholds"]["drift_unused_days"])
    prod = [f for f in fs if f["sensitivity"] == 2]
    sig  = sorted(f'{f["group"]}:{f["userId"]}' for f in prod)
    if sig != st.get("drift_sig"):
        for f in prod:
            journal("DRIFT", f'`{f["group"]}` held by **{f["name"]}** ({f["team"]}) — '
                             f'{"never used" if f["never_used"] else str(f["idle_days"])+"d idle"}. '
                             f'Revocation drafted.')
        st["drift_sig"] = sig
        acted = bool(prod)
    else:
        print(f"  {stamp()}  quiet     {len(prod)} known production findings, nothing new", flush=True)

    # 2. did the codebase move under a packet we already wrote?
    head = repo_head()
    if st.get("head") and head and st["head"] != head:
        journal("REPO", f'moved `{st["head"]}` -> `{head}` — regenerating packets')
        for p in sorted((CFG["_packets"]).glob("*.md")):
            who = next((l.split(":",1)[1].strip() for l in p.read_text().splitlines()
                        if l.startswith("subject:")), None)
            if not who: continue
            try:
                u = okta.resolve(who)
                built = pk.build(u["id"], u["profile"].get("department", ""), use_llm=False)
                pk.write(built)
                journal("REFRESH", f'`{p.name}` rebuilt against `{head}`')
                acted = True
            except Exception as e:
                journal("ERROR", f'could not rebuild `{p.name}`: {e}')
    st["head"] = head

    # 3. anyone provisioned by HR and still waiting?
    try:
        for u in okta.users():
            if u["status"] != "STAGED": continue
            uid = u["id"]
            if uid in st.get("prepared", []): continue
            team = u["profile"].get("department")
            built = pk.build(uid, team, use_llm=False)
            out   = pk.write(built)
            n = len(built["derived"]) + len(built["conventional"])
            journal("PREPARE",
                    f'{u["profile"]["firstName"]} {u["profile"]["lastName"]} starts '
                    f'{u["profile"].get("startDate","soon")} on **{team}** — packet ready '
                    f'({n} proposed, {len(built["declined"])} declined, '
                    f'gate {"PASS" if built["gate"]["passed"] else "BLOCK"}) `{out.name}`')
            st.setdefault("prepared", []).append(uid)
            acted = True
    except Exception as e:
        journal("ERROR", f"could not check staged users: {e}")

    st["last_tick"] = stamp()
    return acted

if __name__ == "__main__":
    every = int(sys.argv[1]) if len(sys.argv) > 1 else 900
    print(f"least daemon — tick every {every}s. journal: {JOURNAL}\n", flush=True)
    st = load()
    while True:
        try:
            tick(st); save(st)
        except KeyboardInterrupt:
            print("\nstopped."); break
        except Exception as e:
            print(f"  {stamp()}  tick failed: {e}", flush=True)
        time.sleep(every)
