"""
Execute an approved packet: assign groups in Okta, then file the access request
the way an engineering org actually does it -- as a reviewable commit.

The new hire cannot file this request herself. On day one she does not know the
billing service reads Stripe keys from Vault. The agent is the only participant
that has read the code.
"""
import re, subprocess, pathlib
from collections import namedtuple

from . import okta, gate
from .config import CFG


class Refused(Exception):
    """
    An approval that will not happen, and why.

    `code` is for callers that branch (the Slack bot styles a self-approval
    differently from a bystander). `message` is for the human.
    """
    def __init__(self, code, message):
        self.code, self.message = code, message
        super().__init__(message)


#: Who is approving. `email` is the identity and the only field ever matched
#: against; `display` is chosen by its owner and is therefore decoration.
Approver = namedtuple("Approver", "email source slack_id display")
Approver.__new__.__defaults__ = (None, "cli", None, None)


def _norm(email):
    return (email or "").strip().lower()


def _field(md, key):
    """Read one scalar out of the packet frontmatter."""
    head = md.split("---")[1] if md.count("---") >= 2 else ""
    for line in head.splitlines():
        if line.startswith(f"{key}:"):
            return line.split(":", 1)[1].strip()
    return ""


def _packet_path(packet):
    """
    Resolve a packet path that arrived from outside.

    In Slack this string is the button's `value`, which is round-tripped through
    the client. Treating it as a path to open is how a button becomes a file
    read, so it has to land inside the packets directory or not at all.
    """
    packets = pathlib.Path(CFG["_packets"]).resolve()
    p = pathlib.Path(packet)
    if not p.is_absolute():
        p = pathlib.Path(CFG["_root"]) / p
    try:
        p = p.resolve()
        p.relative_to(packets)
    except (ValueError, OSError):
        raise Refused("bad_packet_path",
                      f"`{packet}` is not inside the packets directory. I only approve "
                      f"packets I generated, and I will not read a path handed to me "
                      f"from a message.")
    if not p.is_file():
        raise Refused("no_such_packet",
                      f"There is no packet at `{packet}`. Packets are regenerated on "
                      f"every onboard, so this one was probably cleared — re-run the "
                      f"onboard and approve the new one.")
    return p


def approve(packet, approver, approvers=None):
    """
    The one place access is ever granted.

    slackbot.core.approve, mcp apply_access and `python3 -m agent approve` all
    come through here, so the refusals below hold on every surface instead of on
    whichever one someone remembered to guard. Hiding the Slack button is not
    enforcement: the handler is reachable with any payload, so the packet is
    re-read and the gate re-run against the live directory every time.

    Raises Refused. Returns the same shape as apply().
    """
    approvers = [_norm(a) for a in (approvers if approvers is not None
                                    else CFG.get("approvers") or [])]
    path = _packet_path(packet)
    md = path.read_text()

    subject = _field(md, "subject")
    if not subject:
        raise Refused("no_subject",
                      f"`{path.name}` has no `subject:` in its frontmatter, so I cannot "
                      f"tell who it is about. I will not guess at whose access this is.")

    u = okta.resolve(subject)
    prof = u["profile"]
    who = f'{prof["firstName"]} {prof["lastName"]}'

    # 1. The gate, re-run now. The packet's own status field is a record of what
    #    was true when it was written, not a licence.
    g = gate.check(u["id"], person=who, handle=prof["login"])
    if not g["passed"]:
        raise Refused("mfa_gate", g["reason"])

    # 2. Identity before authority: an approver with no email has no identity.
    if not _norm(approver.email):
        raise Refused("no_approver_identity",
                      "I could not read an email address for whoever approved this. "
                      "Access is recorded against a person, so I will not apply a grant "
                      "I cannot attribute. Add an email to the Slack profile and click again.")

    # 3. Nobody approves their own access, including a subject who happens to be
    #    the named manager.
    if _norm(approver.email) == _norm(prof["login"]):
        raise Refused("self_approval",
                      f"{who} cannot approve their own access. This one needs "
                      f"{_field(md, 'manager') or 'an approver'}, or anyone else on the "
                      f"approver list.")

    # 4. Authority.
    manager = _norm(_field(md, "manager"))
    allowed = {a for a in ([manager] if manager and manager != "-" else []) + approvers if a}
    if _norm(approver.email) not in allowed:
        named = ", ".join(sorted(allowed)) or "nobody — the packet names no manager"
        raise Refused("not_approver",
                      f"{approver.email} is not an approver for {who}'s access. "
                      f"This packet can be approved by: {named}.")

    groups = parse_frontmatter_groups(md)
    by = f'{approver.source}:{approver.slack_id or approver.email} <{approver.email}>'
    before = len(okta.user_groups(u["id"]))
    res = apply(u["id"], groups["derived"] + groups["conventional"], by, path.name)
    return {**res, "subject": prof["login"], "name": who, "path": path,
            "before": before, "after": len(okta.user_groups(u["id"])),
            "declined": groups["declined"], "approver_email": approver.email,
            "approver_display": approver.display or approver.email}


def parse_frontmatter_groups(md):
    """Pull proposed groups out of the packet's frontmatter."""
    head = md.split("---")[1] if md.count("---") >= 2 else ""
    out, section = {"derived": [], "conventional": [], "declined": []}, None
    for line in head.splitlines():
        s = line.strip()
        if s.rstrip(":") in out and s.endswith(":"): section = s.rstrip(":"); continue
        m = re.search(r"group:\s*([A-Za-z0-9_\-]+)", s)
        if m and section: out[section].append(m.group(1))
    return out

def apply(user_id, groups, approver, packet_path=None):
    applied, failed = [], []
    for g in groups:
        gid = okta.gid_by_name(g)
        if not gid: failed.append((g, "no such group")); continue
        try:
            okta.assign(gid, user_id, why=f"approved via packet {packet_path}", by=approver)
            applied.append(g)
        except Exception as e:
            failed.append((g, str(e)))
    return {"applied": applied, "failed": failed, "approver": approver}

def open_pr(packet_path, user_email, groups, dry_run=True):
    """File the access request as a PR. The diff IS the audit trail."""
    branch = "access/" + user_email.split("@")[0].replace(".", "-")
    body = (f"Access request filed by the agent on behalf of {user_email}.\n\n"
            f"Proposed groups:\n" + "\n".join(f"- `{g}`" for g in groups) +
            f"\n\nFull justification with code citations: `{packet_path}`\n\n"
            f"Approving this PR provisions the access. Reverting it revokes.\n")
    # -f because packets/*.md is gitignored: only the packet a human actually
    # approved becomes part of the record, not every regeneration.
    cmds = [["git", "checkout", "-b", branch],
            ["git", "add", "-f", str(packet_path)],
            ["git", "commit", "-m", f"Access request: {user_email}"],
            ["git", "push", "-u", "origin", branch],
            ["gh", "pr", "create", "--title", f"Access request: {user_email}",
             "--body", body]]
    if dry_run:
        return {"dry_run": True, "branch": branch, "body": body,
                "commands": [" ".join(c) for c in cmds]}
    out = []
    for c in cmds:
        r = subprocess.run(c, cwd=CFG["_root"], capture_output=True, text=True)
        out.append({"cmd": " ".join(c), "rc": r.returncode,
                    "out": (r.stdout or r.stderr).strip()[:300]})
    return {"dry_run": False, "steps": out}
