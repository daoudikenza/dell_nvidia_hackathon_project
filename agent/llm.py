"""
Inference client. vLLM primary, Ollama fallback, both OpenAI-ish.

Everything runs on the GB10. If this module ever reaches the internet it is a
bug -- local-only is the product premise, not a rule we are satisfying.
"""
import json, urllib.request, urllib.error
from .config import CFG

class Offline(Exception): pass

# Local inference must never go through a host proxy -- see agent/okta.py.
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))

def _post(url, payload, timeout=180):
    req = urllib.request.Request(url, method="POST",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    with _OPENER.open(req, timeout=timeout) as r:
        return json.loads(r.read())

def _vllm(spec, system, prompt):
    out = _post(f"{spec['base']}/chat/completions", {
        "model": spec["model"],
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": prompt}],
        "temperature": CFG["inference"]["temperature"],
        "max_tokens": CFG["inference"]["max_tokens"]})
    return out["choices"][0]["message"]["content"]

def _ollama(spec, system, prompt):
    out = _post(f"{spec['base']}/api/chat", {
        "model": spec["model"], "stream": False,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": prompt}],
        "options": {"temperature": CFG["inference"]["temperature"]}})
    return out["message"]["content"]

def which(verbose=False):
    """
    Report the backend actually answering.

    On failure, say WHY per backend. "none reachable" with no reason sends you
    hunting through three possible causes; the actual error usually names it.
    """
    errors = []
    for name in ("primary", "fallback"):
        spec = CFG["inference"][name]
        try:
            ask("ok", "reply with the single word: ready", _only=spec)
            return (name, spec["kind"], spec["model"], errors) if verbose \
                   else (name, spec["kind"], spec["model"])
        except Exception as e:
            errors.append((name, spec["kind"], spec["base"], spec["model"],
                           f"{type(e).__name__}: {e}"))
    return (None, None, None, errors) if verbose else (None, None, None)

def probe(base):
    """What does this endpoint actually serve? Used to diagnose a wrong URL."""
    for path in ("/models", "/v1/models", "/api/tags", "/health"):
        url = base.rstrip("/").removesuffix("/v1") + path
        try:
            with _OPENER.open(url, timeout=6) as r:
                return url, json.loads(r.read())
        except Exception:
            continue
    return None, None

def ask(system, prompt, _only=None):
    specs = [_only] if _only else [CFG["inference"]["primary"], CFG["inference"]["fallback"]]
    last = None
    for spec in specs:
        try:
            fn = _vllm if spec["kind"] == "vllm" else _ollama
            return fn(spec, system, prompt).strip()
        except Exception as e:
            last = e
    raise Offline(f"no local inference backend reachable: {last}")
