#!/usr/bin/env bash
# Start everything Least needs on the GB10. Run from the repo root.
set -uo pipefail
cd "$(dirname "$0")"

echo "== mock Okta :8081 =="
pkill -f "uvicorn services.mock_okta" 2>/dev/null
python3 services/mock_okta/seed.py
(uvicorn services.mock_okta.app:app --port 8081 --log-level warning &)

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
python3 -m agent status
