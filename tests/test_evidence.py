"""Ledger states, freshness, and terminal outcomes."""

from __future__ import annotations

from jev_governor import evidence


def _req(**overrides):
    base = {
        "req_id": "R1",
        "version": 1,
        "origin": "user",
        "text_ref": "t",
        "acceptance": {"check_recipe_ids": ["pytest"], "required": "all"},
        "updated_seq": 1,
        "blocked": False,
    }
    base.update(overrides)
    return evidence.RequirementVersion(**base)


def _check(seq=2, exit_status=0, provenance="trusted", paths=None, complete=True):
    return evidence.CheckRecord(
        check_id=f"c{seq}",
        req_ids=["R1"],
        recipe_id="pytest",
        executor="runner",
        exit_status=exit_status,
        disposition="completed",
        env_fp="",
        repo_fp=evidence.RepoFingerprint(
            commit="abc",
            relevant_paths=paths if paths is not None else ["a.py"],
            complete=complete,
        ),
        started_at="",
        ended_at="",
        provenance=provenance,
        seq=seq,
    )


def test_verified_requires_authoritative_fresh_pass():
    state, _, _ = evidence.requirement_state(_req(), [_check()], [])
    assert state == "verified"


def test_imported_pass_is_not_verified():
    state, _, notes = evidence.requirement_state(_req(), [_check(provenance="imported")], [])
    assert state == "partially_verified"
    assert any("untrusted-provenance" in n for n in notes)


def test_failed_check_fails_requirement():
    state, _, _ = evidence.requirement_state(_req(), [_check(exit_status=1)], [])
    assert state == "failed"


def test_relevant_patch_makes_check_stale():
    check = _check(seq=2)
    patch = evidence.PatchRecord(patch_id="p1", paths=["a.py"], seq=3)
    status, reason = evidence.check_freshness(check, [patch])
    assert status == evidence.STALE
    state, _, _ = evidence.requirement_state(_req(), [check], [patch])
    assert state == "candidate"


def test_disjoint_patch_keeps_freshness():
    check = _check(seq=2)
    patch = evidence.PatchRecord(patch_id="p1", paths=["other.py"], seq=3)
    status, _ = evidence.check_freshness(check, [patch])
    assert status == evidence.FRESH


def test_unknown_patch_scope_is_conservatively_stale():
    check = _check(seq=2)
    patch = evidence.PatchRecord(patch_id="p1", paths=None, seq=3)
    status, _ = evidence.check_freshness(check, [patch])
    assert status == evidence.STALE


def test_missing_fingerprint_reduces_assurance():
    check = _check(complete=False)
    status, reason = evidence.check_freshness(check, [])
    assert status == evidence.STALE
    assert "fingerprint" in reason
    state, _, _ = evidence.requirement_state(_req(), [check], [])
    assert state == "candidate"


def test_blocked_and_unknown_states():
    state, _, _ = evidence.requirement_state(_req(blocked=True), [], [])
    assert state == "blocked"
    state, _, _ = evidence.requirement_state(_req(acceptance={}), [], [])
    assert state == "unknown"


def test_exit_code_alone_proves_nothing_without_mapping():
    # A passing check for an unmapped recipe cannot verify the requirement.
    check = _check()
    check = evidence.CheckRecord(**{**check.__dict__, "recipe_id": "other-tool"})
    state, _, _ = evidence.requirement_state(_req(), [check], [])
    assert state == "candidate"


def test_terminal_outcomes_never_invent_success():
    out, _ = evidence.derive_terminal_outcome(
        req_states={"R1": "verified"},
        evaluation=None,
        session_ended=True,
        budget_exhausted=False,
        cancelled=False,
    )
    assert out == "incomplete"  # ledger coverage without evaluation is not success
    out, _ = evidence.derive_terminal_outcome(
        req_states={"R1": "candidate"},
        evaluation=None,
        session_ended=False,
        budget_exhausted=True,
        cancelled=False,
    )
    assert out == "unresolved_budget"
    out, _ = evidence.derive_terminal_outcome(
        req_states={"R1": "candidate"},
        evaluation={"outcome": "verified_success"},
        session_ended=True,
        budget_exhausted=False,
        cancelled=False,
    )
    assert out == "failed_evaluation"  # success claim without coverage
    out, _ = evidence.derive_terminal_outcome(
        req_states={"R1": "verified"},
        evaluation={"outcome": "verified_success"},
        session_ended=True,
        budget_exhausted=False,
        cancelled=False,
    )
    assert out == "verified_success"
    out, _ = evidence.derive_terminal_outcome(
        req_states={},
        evaluation=None,
        session_ended=False,
        budget_exhausted=False,
        cancelled=True,
    )
    assert out == "cancelled"
