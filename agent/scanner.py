"""
Repo scanner: code -> access signals.

Deterministic on purpose. Finding `process.env.STRIPE_PRIVATE_KEY` is grep's
job, not a language model's -- it is faster, it cannot hallucinate a credential
that isn't there, and a citation the judge can click beats a paraphrase.

The POLICY table below is the piece a customer would own: it maps what the code
reaches for onto the group that grants it. Shipping it as config rather than
inference is deliberate -- a security team must be able to read and edit it.
"""
import re, pathlib
from .config import CFG
from . import trace

# The customer-owned mapping. Each signal in the code can imply up to three
# different things, and conflating them is what makes onboarding docs useless:
#
#   group   - IAM group membership. The agent can grant this after approval.
#   account - a login that does not exist in the identity provider. Somebody
#             has to invite them. The agent can only tell you who to ask.
#   setup   - something the new hire does on their own machine.
#
# A list of IAM groups is not onboarding. "Ask Mandar for a Stripe dashboard
# invite, then run this" is.
POLICY = [
    (r"STRIPE_(PRIVATE|SECRET)_KEY",  "vault-billing-read",  "reads Stripe API credentials",
     ("Stripe Dashboard", "billing lead", "read-only on the test account"),
     "pull test keys from Vault: `vault kv get secret/billing/stripe-test`"),
    (r"STRIPE_WEBHOOK_SECRET",        "vault-billing-read",  "verifies Stripe webhooks",
     None, "run `stripe listen --forward-to localhost:3000` to test webhooks locally"),
    (r"DATABASE_URL|POSTGRES_URL",    "db-staging-read",     "connects to Postgres",
     None, "point DATABASE_URL at staging, never production"),
    (r"SENTRY_(DSN|AUTH_TOKEN)",      "sentry-eng",          "reports errors to Sentry",
     ("Sentry", "platform team", "member seat on the cal.com org"), None),
    (r"GRAFANA|PROMETHEUS",           "grafana-billing",     "queries dashboards",
     ("Grafana", "infra team", "viewer on billing dashboards"), None),
    (r"DATADOG|DD_API_KEY",           "datadog-eng",         "emits APM traces",
     ("Datadog", "infra team", "read on APM"), None),
    (r"ANALYTICS|SEGMENT_|POSTHOG",   "analytics-dashboard", "writes product analytics",
     ("PostHog", "product analytics owner", "member"), None),
    (r"VERCEL_|DEPLOY_TOKEN",         "deploy-staging",      "deploys the service",
     ("Vercel", "infra team", "member on the cal.com team"), None),
]
ENV  = re.compile(r"process\.env\.([A-Z0-9_]{4,})")
CIS  = re.compile(r"secrets\.([A-Z0-9_]{4,})")
CODE = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".prisma"}
SKIP = {"node_modules", ".git", "dist", "build", ".next", "coverage", "__snapshots__"}

def _walk(root, subpaths):
    for sub in subpaths:
        base = root / sub
        if not base.exists(): continue
        for f in base.rglob("*"):
            if not f.is_file(): continue
            if SKIP & set(f.parts): continue
            if f.suffix in CODE or f.suffix in {".yml", ".yaml"}:
                yield f

def accounts_and_setup(signals):
    """Split the signals into things a human must create and things to run."""
    accounts, setup = [], []
    for h in signals:
        c = h["citations"][0]
        if h.get("account"):
            name, ask, level = h["account"]
            accounts.append({"service": name, "ask": ask, "level": level,
                             "because": f'{c["file"]}:{c["line"]} uses {c["var"]}'})
        if h.get("setup"):
            setup.append({"step": h["setup"], "because": f'{c["var"]}'})
    seen, uniq = set(), []
    for a in accounts:
        if a["service"] in seen: continue
        seen.add(a["service"]); uniq.append(a)
    return uniq, setup

def scan(team_paths, root=None, max_files=4000):
    """Return access signals with file:line citations."""
    root = pathlib.Path(root or CFG["repo"])
    trace.step(f"scanning {root.name} — {len(team_paths)} paths")
    hits, seen, n = {}, set(), 0
    for f in _walk(root, team_paths):
        n += 1
        if n % 250 == 0: trace.log("scan", f"{n} files read…")
        if n > max_files: break
        try: text = f.read_text(errors="ignore")
        except Exception: continue
        pat = CIS if f.suffix in {".yml", ".yaml"} else ENV
        for m in pat.finditer(text):
            var = m.group(1)
            for rx, group, why, account, setup in POLICY:
                if not re.search(rx, var): continue
                line = text[:m.start()].count("\n") + 1
                key = (group, var)
                if key in seen: continue
                seen.add(key)
                hits.setdefault(group, {"group": group, "why": why, "citations": [],
                                        "account": account, "setup": setup})
                rel = str(f.relative_to(root))
                trace.log("scan", f"HIT  {var}", f"{rel}:{line} -> {group}")
                hits[group]["citations"].append({
                    "var": var, "file": rel, "line": line})
    trace.log("scan", f"{n} files read, {len(hits)} access signals")
    for h in hits.values():
        h["citations"] = h["citations"][:3]
        c = h["citations"][0]
        h["because"] = f'{c["file"]}:{c["line"]} — {h["why"]} ({c["var"]})'
    return sorted(hits.values(), key=lambda x: x["group"])

# Verified against the actual cal.com tree -- not guessed.
TEAM_PATHS = {
    "billing":   ["packages/app-store/stripepayment", "packages/prisma",
                  "apps/api", "packages/features/ee"],
    "bookings":  ["packages/features/bookings", "apps/web/modules/bookings"],
    "platform":  ["packages/lib", "packages/ui"],
    "app-store": ["packages/app-store"],
    "infra":     [".github/workflows", "packages/prisma"],
}

if __name__ == "__main__":
    import sys, json
    team = sys.argv[1] if len(sys.argv) > 1 else "billing"
    out = scan(TEAM_PATHS.get(team, []))
    print(json.dumps(out, indent=2))
