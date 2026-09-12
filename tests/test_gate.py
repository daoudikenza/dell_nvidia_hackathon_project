"""
The MFA gate's failure taxonomy.

An unenrolled person and an unreachable directory are different problems with
different remedies, and for most of a hackathon day they were the same opaque
traceback. These tests keep them apart. They run offline: okta.factors is
replaced, so nothing here needs mock Okta on :8081.
"""
import urllib.error, io
import pytest
from agent import gate


def _http_error(code):
    return urllib.error.HTTPError("http://localhost:8081/api/v1/users/x/factors",
                                  code, "Not Found", {}, io.BytesIO(b""))


@pytest.fixture
def factors(monkeypatch):
    """Replace the directory call. Pass a value to return or an exception to raise."""
    def _set(outcome):
        def fake(uid):
            if isinstance(outcome, Exception):
                raise outcome
            return outcome
        monkeypatch.setattr(gate.okta, "factors", fake)
    return _set


ACTIVE = [{"factorType": "push", "provider": "OKTA", "status": "ACTIVE"}]


def test_enrolled_passes(factors):
    factors(ACTIVE)
    g = gate.check("00uNEWHIRE01", person="Nadia Rahimi")
    assert g["passed"] is True
    assert g["status"] == "enrolled"
    assert g["factors"] == ["push"]


def test_pending_factor_does_not_count(factors):
    """Okta returns a factor the moment enrollment starts. Started is not finished."""
    factors([{"factorType": "push", "provider": "OKTA", "status": "PENDING_ACTIVATION"}])
    g = gate.check("00uNEWHIRE01", person="Nadia Rahimi")
    assert g["passed"] is False
    assert g["status"] == "not_enrolled"


def test_not_enrolled_names_the_person_and_the_remedy(factors):
    """The reason a human reads has to carry both, or they go hunting."""
    factors([])
    g = gate.check("00uNEWHIRE01", person="Nadia Rahimi", handle="nadia.rahimi@cal.example.com")
    assert g["passed"] is False
    assert g["status"] == "not_enrolled"
    assert "Nadia Rahimi" in g["reason"]
    assert "python3 -m agent enroll nadia.rahimi@cal.example.com" in g["reason"]
    assert g["remedy"]


def test_unknown_user_is_not_reported_as_unreachable(factors):
    """
    The directory answered. It said this person does not exist. Saying 'Okta
    unreachable' here sends whoever reads it to debug the wrong system.
    """
    factors(_http_error(404))
    g = gate.check("00uSTALEID00", person="00uSTALEID00")
    assert g["passed"] is False
    assert g["status"] == "no_such_user"
    assert "00uSTALEID00" in g["reason"]
    assert "unreachable" not in g["reason"].lower()
    assert "did not answer" not in g["reason"].lower()


def test_directory_down_says_nothing_was_checked(factors):
    """
    Nothing was learned about this person's enrollment. The message must not
    imply it was, and must not blame them.
    """
    factors(urllib.error.URLError("[Errno 61] Connection refused"))
    g = gate.check("00uNEWHIRE01", person="Nadia Rahimi")
    assert g["passed"] is False
    assert g["status"] == "directory_unreachable"
    assert "not enrolled" not in g["reason"].lower()
    assert "run.sh" in g["reason"]


def test_every_outcome_carries_the_same_keys(factors):
    """Callers render g['reason'] blind. Every path has to populate it."""
    for outcome in (ACTIVE, [], _http_error(404), _http_error(500),
                    urllib.error.URLError("refused")):
        factors(outcome)
        g = gate.check("00uX", person="Someone")
        assert set(g) >= {"passed", "status", "factors", "reason", "remedy"}
        assert isinstance(g["passed"], bool)
        if not g["passed"]:
            assert g["reason"], f"empty reason for {g['status']}"


def test_a_failure_never_reads_as_a_pass(factors):
    """A gate that fails open is worse than no gate."""
    for outcome in (_http_error(404), _http_error(500), urllib.error.URLError("x")):
        factors(outcome)
        assert gate.check("00uX", person="Someone")["passed"] is False
