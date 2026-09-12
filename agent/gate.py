"""MFA gate. A refusal, not a warning -- nothing is proposed for an unenrolled user."""
from . import okta

def check(uid):
    fs = okta.factors(uid)
    active = [f for f in fs if f.get("status") == "ACTIVE"]
    return {
        "passed": bool(active),
        "factors": [f["factorType"] for f in active],
        "reason": None if active else
                  "No Okta Verify factor enrolled. All grants blocked until enrollment completes.",
    }
