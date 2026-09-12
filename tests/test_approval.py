"""
The approval chokepoint.

`execute.approve` is the only way a grant ever reaches the directory. Slack, the
CLI and the MCP tool all route through it, so these refusals hold on every
surface rather than on whichever one someone remembered to guard.

Every test asserts on the *effect* -- what reached the directory -- not only on
the refusal message. A control that reports a refusal and provisions anyway is
the bug this file exists to prevent.
"""
import pytest

from agent import execute


def approver(email, source="slack", slack_id=None, display=None):
    return execute.Approver(email=email, source=source, slack_id=slack_id,
                            display=display or email)


MANAGER = "sarah.chen@cal.example.com"
SUBJECT = "nadia.rahimi@cal.example.com"
OTHER = "marcus.okafor@cal.example.com"


def test_enrolled_subject_approved_by_manager_is_granted(directory, packet):
    directory["enroll"]("00uNEWHIRE01")
    res = execute.approve(packet, approver(MANAGER))
    assert sorted(res["applied"]) == ["db-staging-read", "eng-billing"]
    assert len(directory["assigned"]) == 2
    assert (res["before"], res["after"]) == (0, 2)


def test_declined_groups_are_never_applied(directory, packet):
    directory["enroll"]("00uNEWHIRE01")
    execute.approve(packet, approver(MANAGER))
    assert "grp00000003" not in [a["gid"] for a in directory["assigned"]]


def test_unenrolled_subject_is_refused_and_nothing_is_granted(directory, packet):
    """The headline: the gate is a control, not a warning printed earlier."""
    with pytest.raises(execute.Refused) as e:
        execute.approve(packet, approver(MANAGER))
    assert e.value.code == "mfa_gate"
    assert directory["assigned"] == []


def test_gate_is_rechecked_at_approve_time(directory, packet):
    """
    The packet says awaiting-approval because the gate passed when it was built.
    If enrollment lapsed since, approving must still refuse. Trusting the
    packet's own status field would make the check decorative.
    """
    assert "status: awaiting-approval" in packet.read_text()
    with pytest.raises(execute.Refused) as e:
        execute.approve(packet, approver(MANAGER))
    assert e.value.code == "mfa_gate"
    assert directory["assigned"] == []


def test_subject_cannot_approve_their_own_access(directory, packet):
    directory["enroll"]("00uNEWHIRE01")
    with pytest.raises(execute.Refused) as e:
        execute.approve(packet, approver(SUBJECT))
    assert e.value.code == "self_approval"
    assert directory["assigned"] == []


def test_self_approval_is_refused_even_when_subject_is_the_named_manager(directory, packet, tmp_path):
    """Being the approver does not make you eligible to approve yourself."""
    directory["enroll"]("00uNEWHIRE01")
    packet.write_text(packet.read_text().replace(f"manager: {MANAGER}", f"manager: {SUBJECT}"))
    with pytest.raises(execute.Refused) as e:
        execute.approve(packet, approver(SUBJECT))
    assert e.value.code == "self_approval"
    assert directory["assigned"] == []


def test_a_bystander_cannot_approve(directory, packet):
    """Anyone who can see the message could click the button. Seeing is not approving."""
    directory["enroll"]("00uNEWHIRE01")
    with pytest.raises(execute.Refused) as e:
        execute.approve(packet, approver(OTHER))
    assert e.value.code == "not_approver"
    assert directory["assigned"] == []
    assert MANAGER in e.value.message, "the refusal has to say who can approve"


def test_a_configured_approver_may_approve(directory, packet):
    directory["enroll"]("00uNEWHIRE01")
    res = execute.approve(packet, approver(OTHER), approvers=[OTHER])
    assert res["applied"]


def test_approver_matching_ignores_case_and_whitespace(directory, packet):
    directory["enroll"]("00uNEWHIRE01")
    res = execute.approve(packet, approver("  Sarah.Chen@CAL.example.com "))
    assert res["applied"]


def test_an_approver_with_no_email_is_refused(directory, packet):
    """
    A Slack profile without an email is the normal case for guests and some
    bots. No email means no identity, and no identity means no approval.
    """
    directory["enroll"]("00uNEWHIRE01")
    with pytest.raises(execute.Refused) as e:
        execute.approve(packet, approver(None))
    assert e.value.code == "no_approver_identity"
    assert directory["assigned"] == []


def test_the_recorded_approver_is_the_verified_identity(directory, packet):
    """
    A Slack display name is chosen by its owner and can read 'Sarah Chen'.
    The audit record has to carry the id and the email, not the name.
    """
    directory["enroll"]("00uNEWHIRE01")
    execute.approve(packet, approver(MANAGER, slack_id="U123ABC", display="Sarah Chen"))
    by = directory["assigned"][0]["by"]
    assert "U123ABC" in by and MANAGER in by
    assert by != "Sarah Chen"


def test_a_packet_outside_the_packets_directory_is_refused(directory, packet, tmp_path):
    """The path arrives in a Slack button payload. It is not trusted input."""
    outside = tmp_path / "secrets.md"
    outside.write_text("subject: nadia.rahimi@cal.example.com\n")
    directory["enroll"]("00uNEWHIRE01")
    with pytest.raises(execute.Refused) as e:
        execute.approve(outside, approver(MANAGER))
    assert e.value.code == "bad_packet_path"


def test_path_traversal_out_of_the_packets_directory_is_refused(directory, packet):
    directory["enroll"]("00uNEWHIRE01")
    with pytest.raises(execute.Refused) as e:
        execute.approve("packets/../../../etc/passwd", approver(MANAGER))
    assert e.value.code == "bad_packet_path"
    assert directory["assigned"] == []


def test_a_missing_packet_is_refused_by_name(directory, packet):
    directory["enroll"]("00uNEWHIRE01")
    with pytest.raises(execute.Refused) as e:
        execute.approve("packets/nobody.md", approver(MANAGER))
    assert e.value.code == "no_such_packet"


def test_a_packet_with_no_subject_is_refused(directory, packet):
    directory["enroll"]("00uNEWHIRE01")
    packet.write_text(packet.read_text().replace(f"subject: {SUBJECT}", "subject:"))
    with pytest.raises(execute.Refused) as e:
        execute.approve(packet, approver(MANAGER))
    assert e.value.code == "no_subject"


def test_refusal_order_puts_the_subject_before_the_approver(directory, packet):
    """
    An unenrolled subject and a bystander approver are both wrong. Reporting the
    gate first is the more useful message: it is about the request, not the
    reader, and it is the one that stays wrong after the reader walks away.
    """
    with pytest.raises(execute.Refused) as e:
        execute.approve(packet, approver(OTHER))
    assert e.value.code == "mfa_gate"


def test_every_refusal_carries_a_message_a_human_can_act_on(directory, packet):
    cases = [
        (approver(None), {}),
        (approver(SUBJECT), {}),
        (approver(OTHER), {}),
    ]
    directory["enroll"]("00uNEWHIRE01")
    for who, kw in cases:
        with pytest.raises(execute.Refused) as e:
            execute.approve(packet, who, **kw)
        assert len(e.value.message) > 40, e.value.code
        assert e.value.code
