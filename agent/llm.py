"""
Inference client. vLLM primary, Ollama fallback, both OpenAI-ish.

Everything runs on the GB10. If this module ever reaches the internet it is a
bug -- local-only is the product premise, not a rule we are satisfying.
"""
import json, urllib.request, urllib.error
from .config import CFG

class Offline(Exception): pass

def _post(url, payload, timeout=180):
    req = urllib.request.Request(url, method="POST",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
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

def which():
    """Report the backend actually answering, for the demo's activity panel."""
    for name in ("primary", "fallback"):
        spec = CFG["inference"][name]
        try:
            ask("ok", "reply with the single word: ready", _only=spec)
            return name, spec["kind"], spec["model"]
        except Exception:
            continue
    return None, None, None

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
