"""
Local-first, demonstrated rather than asserted.

A quarter of the rubric is "local-first design", and the pitch notes are explicit
that the answer is not "it runs on the box" but "it could not run anywhere else",
shown rather than claimed. So this produces three pieces of evidence a judge can
watch happen:

  1. the model id read back from the loopback inference endpoint, so the thing
     answering is named by the endpoint itself rather than by our config file;
  2. `nvidia-smi`, so the GPU doing it is visible;
  3. every established outbound connection this process's host holds, classified,
     so "no LLM traffic leaves the box" is a list you can read rather than a
     promise.

Written to degrade honestly. On a laptop with no GPU and no inference server it
prints what is absent and says so, because a proof that silently passes when the
thing it proves is missing is not a proof.
"""
import shutil
import socket
import subprocess
import urllib.parse

from . import llm
from .config import CFG

#: Hosts the product is allowed to talk to, and what for. Slack is a message
#: transport: it carries the manager's question and the agent's answer. It never
#: carries a prompt to a model and never returns a completion.
ALLOWED = {"slack.com": "Slack — message transport only, never inference",
           "slack-msgs.com": "Slack — message transport only, never inference",
           "slack-edge.com": "Slack — static assets"}

LOOPBACK = {"127.0.0.1", "::1", "localhost", "0.0.0.0", "[::1]"}


def _run(cmd, timeout=10):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout or r.stderr)
    except FileNotFoundError:
        return 127, ""
    except subprocess.TimeoutExpired:
        return 124, ""


def inference():
    """
    Ask each configured endpoint what it is serving, and report what answered.

    The model id comes from the endpoint's own /models response, not from
    config.yaml. Reading back our own configuration would prove nothing.
    """
    out = []
    for role in ("primary", "fallback"):
        spec = CFG["inference"][role]
        base = spec["base"]
        host = urllib.parse.urlparse(base).hostname or ""
        url, body = llm.probe(base, spec.get("api_key"))
        served = []
        if isinstance(body, dict):
            served = [d.get("id") or d.get("name")
                      for d in (body.get("data") or body.get("models") or [])]
        out.append({"role": role, "kind": spec["kind"], "base": base,
                    "loopback": host in LOOPBACK,
                    "configured": spec["model"],
                    "serving": [s for s in served if s],
                    "reachable": bool(url)})
    return out


def gpu():
    """nvidia-smi, or a plain statement that there is no GPU here."""
    if not shutil.which("nvidia-smi"):
        return {"present": False,
                "note": f"nvidia-smi is not on this host ({socket.gethostname()}). "
                        f"This is not the GB10 — run it there for the GPU evidence."}
    rc, out = _run(["nvidia-smi", "--query-gpu=name,memory.used,memory.total,utilization.gpu",
                    "--format=csv,noheader"])
    if rc != 0:
        return {"present": True, "note": f"nvidia-smi failed (rc={rc})", "raw": out.strip()}
    rows = [l.strip() for l in out.splitlines() if l.strip()]
    return {"present": True, "gpus": rows, "raw": _run(["nvidia-smi"])[1]}


def egress(scope="agent"):
    """
    Established outbound connections, classified.

    Rule 02 is about the agent's runtime path, so that is what is scoped by
    default: every Python process on the box, which covers the agent, the Slack
    bot, the daemon, the MCP server and mock Okta. Scoping to the whole host
    instead would make the evidence depend on whether someone left a browser
    open, which proves nothing either way about this program.

    scope="host" gives the unscoped view for context.

    lsof is the portable-enough option across the Mac this was written on and
    the Ubuntu box it runs on. Anything that is neither loopback nor an allowed
    transport is a finding, because that is the claim under test.
    """
    cmd = ["lsof", "-i", "-P", "-n"]
    if scope == "agent":
        cmd += ["-a", "-c", "python", "-c", "python3", "-c", "Python"]
    rc, out = _run(cmd, timeout=20)
    if rc == 127:
        return {"checked": False, "note": "lsof not installed; cannot enumerate connections"}

    loopback, allowed, findings = [], [], []
    for line in out.splitlines():
        if "ESTABLISHED" not in line:
            continue
        parts = line.split()
        conn = next((p for p in parts if "->" in p), None)
        if not conn:
            continue
        proc = parts[0]
        remote = conn.split("->", 1)[1]
        rhost = remote.rsplit(":", 1)[0].strip("[]")
        entry = f"{proc:<16} -> {remote}"
        if rhost in LOOPBACK:
            loopback.append(entry)
            continue
        why = next((v for k, v in ALLOWED.items() if k in rhost.lower()), None)
        if why:
            allowed.append(f"{entry}   ({why})")
        else:
            findings.append(entry)
    return {"checked": True, "scope": scope, "loopback": loopback,
            "allowed": allowed, "findings": findings}


def report():
    """The whole thing as text. The terminal prints it; Slack posts the same."""
    L = ["LOCAL-FIRST — evidence, not assertion", ""]

    L.append("1. Inference endpoints (model id read back from the endpoint itself)")
    endpoints = inference()          # probed once; each call is a live HTTP round trip
    for e in endpoints:
        where = "loopback" if e["loopback"] else "OFF-BOX"
        if not e["reachable"]:
            L.append(f"   {e['role']:<9} {e['kind']:<7} {e['base']}  [{where}]  nothing responding")
            continue
        serving = ", ".join(e["serving"]) or "responded, named no model"
        L.append(f"   {e['role']:<9} {e['kind']:<7} {e['base']}  [{where}]")
        L.append(f"             serving: {serving}")
        if e["serving"] and e["configured"] not in e["serving"]:
            L.append(f"             configured as {e['configured']} — MISMATCH")
    off = [e for e in endpoints if not e["loopback"]]
    L.append("   -> every inference endpoint is on loopback" if not off
             else f"   -> {len(off)} inference endpoint(s) are NOT on loopback")
    L.append("")

    L.append("2. GPU")
    g = gpu()
    if not g["present"]:
        L.append(f"   {g['note']}")
    elif "gpus" in g:
        for row in g["gpus"]:
            L.append(f"   {row}")
    else:
        L.append(f"   {g['note']}")
    L.append("")

    L.append("3. Outbound connections held by the agent's own processes")
    e = egress("agent")
    if not e["checked"]:
        L.append(f"   {e['note']}")
    else:
        L.append(f"   loopback          : {len(e['loopback'])}")
        for x in e["loopback"][:8]:
            L.append(f"      {x}")
        L.append(f"   allowed transport : {len(e['allowed'])}")
        for x in e["allowed"][:8]:
            L.append(f"      {x}")
        if e["findings"]:
            L.append(f"   UNEXPECTED        : {len(e['findings'])}")
            for x in e["findings"]:
                L.append(f"      {x}")
            L.append("   -> these are not loopback and not the Slack transport. "
                     "Check them before claiming local-only.")
        else:
            L.append("   unexpected        : 0")
            L.append("   -> the agent holds no connection off this box except the "
                     "Slack message transport.")
    L.append("")
    L.append("Slack carries the manager's question and the agent's answer. It never "
             "carries a prompt to a model and never returns a completion. Rule 02 is "
             "about the inference path, and the inference path is line 1.")
    return "\n".join(L)


if __name__ == "__main__":
    print(report())
