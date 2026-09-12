"""
Cross-check: does the onboarding half mention something the access half missed?

This is the only finding that requires BOTH halves to exist, which is the whole
argument for building one product instead of two features. Deliberately blunt --
surface-match known systems named in the prose against what was proposed.
"""
import re
from . import okta

# system named in prose -> group that grants it
MENTIONS = {
    r"\banalytics\b|\bwarehouse\b":      "analytics-dashboard",
    r"\bgrafana\b|\bdashboards?\b":      "grafana-billing",
    r"\bsentry\b":                       "sentry-eng",
    r"\bdatadog\b|\bAPM\b":              "datadog-eng",
    r"\bpagerduty\b|\bon-?call\b":       "pagerduty-oncall",
    r"\bjira\b":                         "jira-eng",
    r"\bfigma\b":                        "figma-viewer",
    r"\bproduction database\b":          "db-prod-read",
}

def prose_only(md):
    """
    Only the KNOWLEDGE half counts as a mention.

    The access section names groups by design -- scanning it would report the
    packet's own declined and unknown lists as gaps, which is a false positive
    and exactly the kind of thing that detonates on stage.
    """
    # drop YAML frontmatter first -- it names every declined group explicitly
    if md.startswith("---"):
        parts = md.split("---", 2)
        md = parts[2] if len(parts) > 2 else md
    out, keep = [], True
    for line in md.splitlines():
        if line.startswith("## "):
            keep = line.strip() not in ("## Access requested", "## Summary")
        if keep: out.append(line)
    return "\n".join(out)

def gaps(packet_body, proposed_groups, _already_trimmed=False):
    if not _already_trimmed: packet_body = prose_only(packet_body)
    found = []
    for rx, group in MENTIONS.items():
        m = re.search(rx, packet_body, re.I)
        if m and group not in proposed_groups:
            line = packet_body[:m.start()].count("\n") + 1
            found.append({
                "group": group, "phrase": m.group(0), "line": line,
                "note": (f'packet references "{m.group(0)}" but no access request '
                         f'covers `{group}` — new hire will be blocked')})
    return found
