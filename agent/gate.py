"""
MFA gate. A refusal, not a warning -- nothing is granted for an unenrolled user.

Three outcomes fail, and they are three different problems:

  not_enrolled           the directory answered, this person has no active factor
  no_such_user           the directory answered, it has never heard of this id
  directory_unreachable  the directory did not answer, so nothing was checked

Collapsing them cost a working afternoon: an unenrolled user surfaced as a bare
404 traceback, which reads as "Okta is down" and sends you to debug the wrong
system. Every failure below names the person, says which of the three happened,
and gives the next command to type.
"""
import urllib.error

from . import okta

#: enrollment started is not enrollment finished. Okta hands back a factor in
#: PENDING_ACTIVATION the moment someone scans the QR code.
ACTIVE = "ACTIVE"


def _result(passed, status, reason, remedy=None, factors=()):
    """
    `reason` always carries the remedy too.

    Callers render `reason` blind -- brief.py, packet.py and the Slack bot all
    print it and nothing else. Keeping the next action in a separate field is
    how it got swallowed. `remedy` stays available for surfaces that want to
    style it apart, but it is never the only place the remedy appears.
    """
    return {"passed": passed, "status": status, "factors": list(factors),
            "reason": " ".join(x for x in (reason, remedy) if x) or None,
            "statement": reason, "remedy": remedy}


def check(uid, person=None, handle=None):
    """
    Is this person allowed to receive a grant?

    person  display name, for the message. Falls back to the id.
    handle  what a human would type to name them again -- email or name. Used to
            build the enrollment command, so it has to be copy-pasteable.
    """
    label = person or uid
    typeable = handle or person or uid

    try:
        found = okta.factors(uid)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return _result(
                False, "no_such_user",
                f"The directory has no user {uid} ({label}). It answered; it does not "
                f"know this person. This is not an outage. Most often the demo was "
                f"reseeded under a running process, which changes nothing about who "
                f"exists but does invalidate ids held in memory.",
                remedy=f"Look them up again: `python3 -m agent onboard \"{typeable}\" <team>`. "
                       f"If they genuinely are not in the directory, HR provisions "
                       f"identities, not this agent: `python3 -m agent stage <First> <Last> <team>`.")
        return _result(
            False, "directory_error",
            f"The directory refused the enrollment check for {label} with HTTP {e.code}. "
            f"Nothing was granted and nothing is known about their enrollment.",
            remedy="Check the identity provider's logs, then re-run the same command.")
    except urllib.error.URLError as e:
        return _result(
            False, "directory_unreachable",
            f"The directory at {okta.BASE} did not answer ({e.reason}). Nothing was "
            f"checked, so this says nothing about {label} either way.",
            remedy="Start it with `./run.sh`, or point `okta:` in config.yaml at a "
                   "directory that is running, then re-run the same command.")

    active = [f for f in found if f.get("status") == ACTIVE]
    if active:
        return _result(True, "enrolled", None, factors=[f["factorType"] for f in active])

    started = [f for f in found if f.get("status") != ACTIVE]
    part_way = (" Enrollment has been started but not completed"
                f" ({', '.join(f.get('status','?') for f in started)})." if started else "")
    return _result(
        False, "not_enrolled",
        f"{label} has no active Okta Verify factor, so every grant is blocked."
        f"{part_way} The directory answered normally; this is an enrollment gap, "
        f"not an outage.",
        remedy=f"{label} completes Okta Verify setup on their phone. To stand that in "
               f"for the demo: `python3 -m agent enroll {typeable}`.")
