#!/usr/bin/env bash
# Start everything Least needs on the GB10. Run from the repo root.
set -uo pipefail
cd "$(dirname "$0")"

# Ubuntu refuses pip into system python (PEP 668), so a local .venv is the
# normal outcome. Find it rather than making every command depend on the user
# having remembered to activate it.
if [ -x ".venv/bin/python" ]; then
  PY=".venv/bin/python"
elif [ -n "${VIRTUAL_ENV:-}" ]; then
  PY="$VIRTUAL_ENV/bin/python"
else
  PY="python3"
fi
echo "python: $PY"

if ! "$PY" -c "import yaml, fastapi" 2>/dev/null; then
  echo
  echo "  dependencies missing. Run:"
  echo "    python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
  echo
  exit 1
fi

# Port comes from config.yaml so there is ONE place to change it. If something
# else on the box already owns it (another service, another team), edit the
# okta: line in config.yaml and everything follows.
OKTA_PORT=$("$PY" -c "import yaml;print(yaml.safe_load(open('config.yaml'))['okta'].rsplit(':',1)[1])")

echo "== mock Okta :$OKTA_PORT =="
pkill -f "uvicorn services.mock_okta" 2>/dev/null
sleep 1
if ss -ltn 2>/dev/null | grep -q ":$OKTA_PORT " || lsof -i ":$OKTA_PORT" >/dev/null 2>&1; then
  echo "   PORT $OKTA_PORT IS ALREADY IN USE by something else."
  echo "   Find it:  ss -ltnp | grep $OKTA_PORT"
  echo "   Then either kill it, or edit config.yaml:"
  echo "       okta: http://localhost:8091"
  echo "   and re-run ./run.sh"
  exit 1
fi
"$PY" services/mock_okta/seed.py
("$PY" -m uvicorn services.mock_okta.app:app --port "$OKTA_PORT" --log-level warning &)

echo "== Vault dev :8200 =="
if command -v vault >/dev/null; then
  (vault server -dev -dev-root-token-id=least-dev -dev-listen-address=127.0.0.1:8200 \
     >/tmp/vault.log 2>&1 &)
  export VAULT_ADDR=http://127.0.0.1:8200 VAULT_TOKEN=least-dev
  echo "   vault dev started (token: least-dev)"
else
  echo "   vault binary not found - policy generation will run in dry-run"
fi

echo "== inference =="
if curl -sf localhost:8000/v1/models >/dev/null 2>&1; then
  echo "   vLLM up on :8000  <- primary"
elif curl -sf localhost:11434/api/tags >/dev/null 2>&1; then
  echo "   vLLM down, Ollama up on :11434  <- fallback"
else
  echo "   NEITHER vLLM nor Ollama reachable. Start one:"
  echo "     nemoclaw / vllm serve ...        (preferred, the 35B)"
  echo "     ollama serve && ollama pull llama3.2"
fi

sleep 2
echo
"$PY" -m agent status
