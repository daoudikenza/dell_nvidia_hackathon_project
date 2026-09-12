"""
The always-on loop. This is what makes Least an agent rather than a script:
it runs whether or not anyone asks it to.

  nightly   drift scan -> post findings, draft revocations
  hourly    repo watch -> if code changed under a documented area, regenerate
"""
import time, subprocess, json, pathlib, datetime as dt, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from agent.config import CFG
from agent.drift import analyse

STATE = CFG["_root"] / ".loop-state.json"

def repo_head():
    r = subprocess.run(["git", "-C", str(CFG["repo"]), "rev-parse", "HEAD"],
                       capture_output=True, text=True)
    return r.stdout.strip()

def load(): return json.loads(STATE.read_text()) if STATE.exists() else {}
def save(d): STATE.write_text(json.dumps(d, indent=2))

def tick():
    st, now = load(), dt.datetime.utcnow()
    org = json.loads((CFG["_root"]/"services/mock_okta/org.json").read_text())
    fs = analyse(org)
    prod = [f for f in fs if f["sensitivity"] == 2]
    print(f'[{now:%H:%M:%S}] drift: {len(fs)} stale, {len(prod)} production-level')
    for f in prod[:3]:
        print(f'           {f["group"]} · {f["name"]} · '
              f'{"never used" if f["never_used"] else str(f["idle_days"])+"d idle"}')
    head = repo_head()
    if st.get("head") and st["head"] != head:
        print(f'[{now:%H:%M:%S}] repo moved {st["head"][:8]} -> {head[:8]} — packets stale')
    st["head"], st["last"] = head, now.isoformat()
    save(st)

if __name__ == "__main__":
    every = int(sys.argv[1]) if len(sys.argv) > 1 else 3600
    print(f"least daemon — every {every}s. ctrl-c to stop.")
    while True:
        try: tick()
        except Exception as e: print("  tick failed:", e)
        time.sleep(every)
