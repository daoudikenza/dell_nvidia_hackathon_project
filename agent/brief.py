"""
The manager-facing answer.

A manager asking "what does my new hire need?" in Slack does not want a
four-page packet in the channel. They want the shape of it, the one thing that
needs their decision, and a link. This renders that.
"""

def render(p, packet_path=None):
    prof = p["user"]["profile"]
    n_grant = len(p["derived"]) + len(p["conventional"])
    L = []
    L.append(f'*{prof["firstName"]} {prof["lastName"]}* — {p["team"]} team, '
             f'starts {prof.get("startDate","soon")}')
    L.append("")
    if not p["gate"]["passed"]:
        L.append(f'⛔ *Blocked* — {p["gate"]["reason"]}')
        L.append("")
    L.append(f'Today you would clone a teammate: *{len(p["baseline"]["grants"])} grants, '
             f'none justified*. I propose *{n_grant}*, each with a reason.')
    L.append("")
    L.append("*Access I can grant once you approve*")
    for d in p["derived"]:
        L.append(f'  • `{d["group"]}` — {d["because"]}')
    for c in p["conventional"]:
        L.append(f'  • `{c["group"]}` — {c["because"]}')
    if p["declined"]:
        L.append("")
        L.append("*Declined* — a teammate has these, nothing justifies them for a new hire")
        for d in p["declined"]:
            L.append(f'  • ~{d["group"]}~ — {d["because"]}')
    if p.get("accounts"):
        L.append("")
        L.append("*Accounts I cannot create — someone has to invite her*")
        for a in p["accounts"]:
            L.append(f'  • {a["service"]} — ask {a["ask"]} ({a["level"]})')
    if p.get("setup_steps"):
        L.append("")
        L.append("*Her first-day setup*")
        for x in p["setup_steps"]:
            L.append(f'  • {x["step"]}')
    L.append("")
    L.append("*I cannot tell* — Salesforce, Figma, anything outside the identity provider. Your call.")
    if packet_path:
        L.append("")
        L.append(f'Full packet with citations: `{packet_path}`')
    L.append("Reply *approve* and I will provision the access.")
    return "\n".join(L)
