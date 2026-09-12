"""
Execute an approved packet: assign groups in Okta, then file the access request
the way an engineering org actually does it -- as a reviewable commit.

The new hire cannot file this request herself. On day one she does not know the
billing service reads Stripe keys from Vault. The agent is the only participant
that has read the code.
"""
import re, subprocess, pathlib
from . import okta
from .config import CFG

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
