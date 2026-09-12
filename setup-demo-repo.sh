#!/usr/bin/env bash
# Fetch the demo codebase if it isn't already on this machine.
#
# cal.com is NOT part of the NemoClaw/OpenClaw/OpenShell stack -- it is demo
# data, and it has to arrive separately. The scanner needs the files AND some
# git history: "Who owns what" comes from git log, so a --depth 1 clone
# silently produces an empty section.
set -uo pipefail
cd "$(dirname "$0")"

PY_BIN="${PYTHON:-python3}"
if ! "$PY_BIN" -c "import yaml" 2>/dev/null; then
  echo "dependencies missing. run first:  pip3 install -r requirements.txt"
  echo "(or set PYTHON=/path/to/python if you use a venv)"
  exit 1
fi

TARGET="${1:-$HOME/hack-stage/demo-repos/cal.com}"

if [ -d "$TARGET/.git" ]; then
  n=$(git -C "$TARGET" rev-list --count HEAD 2>/dev/null || echo 0)
  f=$(git -C "$TARGET" ls-files 2>/dev/null | wc -l | tr -d ' ')
  echo "already present: $TARGET"
  echo "  $f files, $n commits of history"
  [ "$n" -lt 20 ] && echo "  WARNING: very shallow - 'Who owns what' will be thin"
else
  echo "cloning cal.com -> $TARGET  (a few hundred MB, needs network)"
  mkdir -p "$(dirname "$TARGET")"
  git clone --depth 100 https://github.com/calcom/cal.com.git "$TARGET" || {
    echo "clone FAILED. Options:"
    echo "  - copy ~/hack-stage/demo-repos/cal.com from a teammate's laptop"
    echo "  - or point config.yaml at any other real repo you already have"
    exit 1; }
fi

# make config.yaml agree with reality
"$PY_BIN" - "$TARGET" <<'PY'
import sys, pathlib, re
target = sys.argv[1].replace(str(pathlib.Path.home()), "~")
p = pathlib.Path("config.yaml"); s = p.read_text()
new = re.sub(r"^repo:.*$", f"repo: {target}", s, count=1, flags=re.M)
if new != s: p.write_text(new); print(f"config.yaml repo: -> {target}")
else: print(f"config.yaml already points at {target}")
PY

echo
echo "verifying the scanner can actually read it..."
"$PY_BIN" -c "
import sys; sys.path.insert(0,'.')
from agent.scanner import scan, TEAM_PATHS
from agent.config import CFG
missing = [p for p in TEAM_PATHS['billing'] if not (CFG['repo']/p).exists()]
hits = scan(TEAM_PATHS['billing'])
print(f'  {len(hits)} access signals found')
for h in hits:
    c = h['citations'][0]
    print(f\"    {h['group']:<22} {c['file']}:{c['line']}\")
if not hits:
    print('  NO SIGNALS - wrong repo, or TEAM_PATHS needs updating for it')
    sys.exit(1)
"
