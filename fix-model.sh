#!/usr/bin/env bash
# Ask the inference server what it is actually serving and write that into
# config.yaml. OpenAI-shaped APIs reject a model name they don't recognise, and
# the rejection surfaces as "unreachable" rather than "wrong model" - so guessing
# the string costs more time than asking for it.
set -uo pipefail
cd "$(dirname "$0")"
[ -x ".venv/bin/python" ] && PY=".venv/bin/python" || PY="python3"

BASE="${1:-http://localhost:8081/v1}"
KEY="${2:-}"

case "$BASE" in
  https://localhost*|https://127.0.0.1*)
    echo "NOTE: local servers speak plain HTTP. Rewriting https:// -> http://"
    BASE="http://${BASE#https://}" ;;
esac

"$PY" - "$BASE" "$KEY" <<'PY'
import sys, json, re, pathlib, urllib.request
base = sys.argv[1].rstrip("/")
key  = sys.argv[2] if len(sys.argv) > 2 else ""
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))   # never proxy localhost
hdrs = {"Authorization": f"Bearer {key}"} if key else {}

served = None
for url in (f"{base}/models", base.removesuffix("/v1") + "/v1/models"):
    try:
        with opener.open(urllib.request.Request(url, headers=hdrs), timeout=8) as r:
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
newline = (f'  primary:  {{kind: vllm, base: "{base}", model: "{served}"'
           + (f', api_key: "{key}"' if key else "") + "}}")
s2 = re.sub(r"^\s*primary:.*$", newline, s, count=1, flags=re.M)
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
