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

echo "== mock Okta :8081 =="
pkill -f "uvicorn services.mock_okta" 2>/dev/null
"$PY" services/mock_okta/seed.py
("$PY" -m uvicorn services.mock_okta.app:app --port 8081 --log-level warning &)

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
