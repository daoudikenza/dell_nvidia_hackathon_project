"""
Visible work.

A result that appears instantly with nothing in between looks hardcoded --
to an audience, and honestly to anyone. This prints what the agent is actually
doing as it does it: which files are opened, which HTTP calls go out, what the
model was asked and how long it took.

Off by default (clean output for scripting), on with -v.
"""
import sys, time

ENABLED = False
_t0 = None

C = {"scan": "\033[36m", "okta": "\033[35m", "llm": "\033[33m",
     "peer": "\033[32m", "pkt": "\033[34m", "gate": "\033[31m",
     "dim": "\033[2m", "off": "\033[0m", "b": "\033[1m"}

def on():
    global ENABLED, _t0
    ENABLED, _t0 = True, time.time()

def _color(): return sys.stderr.isatty()

def log(tag, msg, detail=""):
    if not ENABLED: return
    el = f"{time.time() - _t0:6.2f}s"
    if _color():
        c = C.get(tag, "")
        line = (f"{C['dim']}{el}{C['off']}  {c}{tag:<5}{C['off']}  {msg}"
                + (f"  {C['dim']}{detail}{C['off']}" if detail else ""))
    else:
        line = f"{el}  {tag:<5}  {msg}" + (f"  {detail}" if detail else "")
    print(line, file=sys.stderr, flush=True)

def step(msg):
    """A heading between phases."""
    if not ENABLED: return
    if _color():
        print(f"\n{C['b']}── {msg}{C['off']}", file=sys.stderr, flush=True)
    else:
        print(f"\n-- {msg}", file=sys.stderr, flush=True)

class timer:
    def __init__(self, tag, msg): self.tag, self.msg = tag, msg
    def __enter__(self): self.t = time.time(); return self
    def __exit__(self, *a):
        log(self.tag, self.msg, f"{(time.time()-self.t)*1000:.0f}ms")
