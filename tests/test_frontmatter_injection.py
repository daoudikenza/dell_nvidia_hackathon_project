"""
Frontmatter injection into the approval decision.

The packet's frontmatter is written by interpolating directory profile strings,
and it was read back with a hand-rolled parser that returned the FIRST matching
key. A newline inside a profile field -- a surname, a team, a start date -- could
therefore inject an earlier `manager:` line that won the match, and an earlier
`access: derived:` block whose groups were applied.

Proven end to end before the fix: POSTing a user whose lastName contained
`\\nmanager: mallory@evil.example.com\\naccess:\\n  derived:\\n    - {group:
infra-admin}` produced a packet where approve() read mallory as the authorised
approver and infra-admin as a proposed group.

Two independent defences, either of which alone stops it, because this is the
authorisation boundary:

  1. approve() takes the approver from the live directory, not the packet.
  2. render() cannot emit a newline into frontmatter at all.
"""
import pytest

from agent import execute, packet as pk


EVIL = ("Rahimi\nmanager: mallory@evil.example.com\naccess:\n"
        "  derived:\n    - {group: infra-admin, because: \"x\"}")


def _packet_with(profile_extra, tmp_path, monkeypatch):
    from agent.config import CFG
    packets = tmp_path / "packets"
    packets.mkdir()
    monkeypatch.setitem(CFG, "_packets", packets)
    monkeypatch.setitem(CFG, "_root", tmp_path)
    p = {"user": {"id": "00uEVIL", "profile": {
            "firstName": "Pwn", "login": "pwn@cal.example.com",
            "manager": "sarah.chen@cal.example.com", "startDate": "2026-09-15",
            **profile_extra}},
         "team": "billing", "derived": [], "conventional": [], "declined": [],
         "accounts": [], "setup_steps": [], "owners": [], "paths": [],
         "baseline": {"grants": [], "donor": "x", "elevated": [], "typical_days": 1},
         "gate": {"passed": True, "status": "enrolled", "factors": ["push"],
                  "reason": None, "remedy": None, "statement": None},
         "prose": {}, "generated": "2026-09-12T00:00:00Z"}
    return p


def _keys(md):
    """Frontmatter keys, as the parsers see them: lines that START with a key."""
    return [l.split(":", 1)[0] for l in md.split("---")[1].splitlines()
            if l and not l.startswith((" ", "\t")) and ":" in l]


def test_render_cannot_emit_a_newline_into_frontmatter(tmp_path, monkeypatch):
    """
    The injected text survives as inert content on the name line -- a mangled
    name is visible, which is the point. What it must not do is become a line of
    its own, because both parsers key on the start of a line.
    """
    md = pk.render(_packet_with({"lastName": EVIL}, tmp_path, monkeypatch))
    head = md.split("---")[1]
    assert "\n" not in head.split("name:")[1].split("\n")[0].replace("\n", "")
    assert _keys(md).count("manager") == 1
    assert "infra-admin" not in " ".join(
        l for l in head.splitlines() if l.strip().startswith("- {group:"))


def test_the_injected_manager_does_not_become_the_approver(tmp_path, monkeypatch):
    p = _packet_with({"lastName": EVIL}, tmp_path, monkeypatch)
    md = pk.render(p)
    assert execute._field(md, "manager") == "sarah.chen@cal.example.com"


def test_injected_groups_are_not_proposed(tmp_path, monkeypatch):
    p = _packet_with({"lastName": EVIL}, tmp_path, monkeypatch)
    groups = execute.parse_frontmatter_groups(pk.render(p))
    assert "infra-admin" not in groups["derived"] + groups["conventional"]


@pytest.mark.parametrize("field", ["lastName", "firstName", "startDate", "login"])
def test_every_interpolated_profile_field_is_neutralised(field, tmp_path, monkeypatch):
    md = pk.render(_packet_with({"lastName": "Rahimi", field: EVIL},
                                tmp_path, monkeypatch))
    assert _keys(md).count("manager") == 1
    assert execute._field(md, "manager") == "sarah.chen@cal.example.com"


def test_a_packet_claiming_a_second_manager_is_refused(directory, packet):
    """
    Defence in depth. Even if something else ever writes a packet with two
    manager lines, the parser refuses rather than silently picking one.
    """
    directory["enroll"]("00uNEWHIRE01")
    packet.write_text(packet.read_text().replace(
        "manager: sarah.chen@cal.example.com",
        "manager: mallory@evil.example.com\nmanager: sarah.chen@cal.example.com"))
    with pytest.raises(execute.Refused) as e:
        execute.approve(packet, execute.Approver(
            email="mallory@evil.example.com", source="slack", display="M"))
    assert e.value.code in {"malformed_packet", "not_approver"}
    assert directory["assigned"] == []


def test_the_approver_is_checked_against_the_live_directory(directory, packet):
    """
    The packet says sarah.chen is the manager. The directory is the authority on
    that, so a packet that disagrees with the directory does not win.
    """
    directory["enroll"]("00uNEWHIRE01")
    packet.write_text(packet.read_text().replace(
        "manager: sarah.chen@cal.example.com", "manager: mallory@evil.example.com"))
    with pytest.raises(execute.Refused) as e:
        execute.approve(packet, execute.Approver(
            email="mallory@evil.example.com", source="slack", display="M"))
    assert e.value.code == "not_approver"
    assert directory["assigned"] == []
