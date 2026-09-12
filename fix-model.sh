#!/usr/bin/env bash
# Ask the inference server what it is actually serving and write that into
# config.yaml. OpenAI-shaped APIs reject a model name they don't recognise, and
# the rejection surfaces as "unreachable" rather than "wrong model" - so guessing
# the string costs more time than asking for it.
set -uo pipefail
cd "$(dirname "$0")"
[ -x ".venv/bin/python" ] && PY=".venv/bin/python" || PY="python3"

BASE="${1:-http://localhost:8081/v1}"

"$PY" - "$BASE" <<'PY'
import sys, json, re, pathlib, urllib.request
base = sys.argv[1].rstrip("/")
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))   # never proxy localhost

served = None
for url in (f"{base}/models", base.removesuffix("/v1") + "/v1/models"):
    try:
        with opener.open(url, timeout=8) as r:
            body = json.loads(r.read())
        ids = [d.get("id") for d in (body.get("data") or []) if d.get("id")]
        if ids:
            served = ids[0]
            print(f"{url} serves: {', '.join(ids)}")
            break
    except Exception as e:
        print(f"{url} -> {type(e).__name__}: {e}")

if not served:
    print("\nCould not read a model id. Is the server up on that address?")
    sys.exit(1)

p = pathlib.Path("config.yaml"); s = p.read_text()
s2 = re.sub(r'(primary:\s*\{kind:\s*vllm,\s*base:\s*")[^"]*(",\s*model:\s*")[^"]*(")',
            rf'\g<1>{base}\g<2>{served}\g<3>', s, count=1)
if s2 == s:
    print("\nCould not rewrite config.yaml automatically. Set these by hand:")
    print(f'  base:  "{base}"')
    print(f'  model: "{served}"')
    sys.exit(1)
p.write_text(s2)
print(f"\nconfig.yaml updated:\n  base:  {base}\n  model: {served}")
PY

echo
"$PY" -m agent status
