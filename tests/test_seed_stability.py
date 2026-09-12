"""
SETUP.md says re-running seed.py gives an identical demo state. It did not.

Group ids came from Python's hash(), which is randomised per process, so every
reseed renamed every group id. Three runs of the old derivation gave 49329903,
73538338 and 77757592 for the same input. Anything holding an id across a reseed
-- the long-lived Slack bot, the MCP server, the daemon -- then resolved to ids
that no longer existed.

This runs seed.py in separate interpreters, which is the only way to catch it:
within one process hash() is self-consistent and the bug is invisible.
"""
import json
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SEED = ROOT / "services" / "mock_okta" / "seed.py"
ORG = ROOT / "services" / "mock_okta" / "org.json"


@pytest.fixture(autouse=True)
def preserve_org():
    """
    seed.py writes the repo's real org.json, and these tests run it ten times.
    Running pytest during a demo would therefore wipe live state: enrollments
    made with `agent enroll`, grants applied through `approve`. Snapshot and
    restore around every test in this file.
    """
    saved = ORG.read_bytes() if ORG.exists() else None
    try:
        yield
    finally:
        if saved is not None:
            ORG.write_bytes(saved)


def _reseed_in_a_fresh_process():
    r = subprocess.run([sys.executable, str(SEED)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return json.loads(ORG.read_text())


def test_group_ids_are_identical_across_processes():
    a = _reseed_in_a_fresh_process()
    b = _reseed_in_a_fresh_process()
    ids_a = {g["profile"]["name"]: g["id"] for g in a["groups"]}
    ids_b = {g["profile"]["name"]: g["id"] for g in b["groups"]}
    assert ids_a == ids_b


def test_memberships_still_point_at_groups_that_exist_after_a_reseed():
    """
    The failure that actually bit: ids held from before a reseed no longer
    resolve. Cross-checking one run's memberships against the next run's groups
    is the same shape as a running process outliving the reseed.
    """
    a = _reseed_in_a_fresh_process()
    b = _reseed_in_a_fresh_process()
    live = {g["id"] for g in b["groups"]}
    dangling = {m["groupId"] for m in a["memberships"]} - live
    assert not dangling, f"{len(dangling)} group ids from the previous seed are now dead"


def test_the_whole_document_is_reproducible():
    """`random.seed(42)` is in seed.py precisely so this holds."""
    a = _reseed_in_a_fresh_process()
    b = _reseed_in_a_fresh_process()
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_ids_do_not_depend_on_the_hash_seed():
    """
    PYTHONHASHSEED is the direct probe. If any id still comes from hash(), these
    two runs disagree.
    """
    def run(seed):
        import os
        env = {**os.environ, "PYTHONHASHSEED": seed}
        r = subprocess.run([sys.executable, str(SEED)], capture_output=True,
                           text=True, env=env)
        assert r.returncode == 0, r.stderr
        return json.loads(ORG.read_text())

    assert json.dumps(run("0"), sort_keys=True) == json.dumps(run("12345"), sort_keys=True)
