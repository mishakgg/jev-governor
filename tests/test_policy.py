"""Deterministic policy rules."""

from __future__ import annotations

from jev_governor import policy


def _features(**overrides):
    base = {
        "n_requirements": 1,
        "n_failed_now": 0,
        "n_remaining": 1,
        "distinct_patches": 0,
        "same_assert_after_distinct_patches": 0,
        "new_diagnostics_since_last_patch": 0,
        "hypothesis_changed": False,
        "n_checks": 0,
        "n_stale_checks": 0,
        "n_fresh_pass_checks": 0,
        "total_input_tokens": 100,
        "total_output_tokens": 10,
        "unknown_usage_ops": 0,
        "usage_resets": 0,
        "elapsed_s": 10.0,
    }
    base.update(overrides)
    return base


def test_loop_escalates():
    decision = policy.decide(
        _features(n_failed_now=1, distinct_patches=2, same_assert_after_distinct_patches=2),
        policy.PolicyContext(),
    )
    assert decision.selected == "ESCALATE_DIAGNOSIS"
    assert decision.advisory


def test_productive_expensive_continues_not_paused():
    decision = policy.decide(
        _features(
            total_input_tokens=34000,
            total_output_tokens=5000,
            hypothesis_changed=True,
            new_diagnostics_since_last_patch=1,
            distinct_patches=1,
        ),
        policy.PolicyContext(),
    )
    assert decision.selected == "CONTINUE"


def test_stale_evidence_verifies():
    decision = policy.decide(_features(n_stale_checks=1, n_checks=1), policy.PolicyContext())
    assert decision.selected == "VERIFY_NOW"


def test_budget_exhaustion_pauses_and_is_unresolved():
    decision = policy.decide(
        _features(total_input_tokens=9000, total_output_tokens=2000),
        policy.PolicyContext(budget={"max_total_tokens": 10000}),
    )
    assert decision.selected == "PAUSE_REPLAN"
    assert "budget-exhausted" in decision.rationale_codes


def test_economical_only_when_configured():
    steady = _features()
    assert policy.decide(steady, policy.PolicyContext()).selected == "CONTINUE"
    decision = policy.decide(steady, policy.PolicyContext(economical_available="cheap-target"))
    assert decision.selected == "ECONOMICAL_CONTINUE"
    assert decision.intended_config["target"] == "cheap-target"


def test_abstain_without_requirements():
    decision = policy.decide(_features(n_requirements=0, n_remaining=0), policy.PolicyContext())
    assert decision.selected is None
    assert decision.abstained


def test_unsupported_action_falls_back():
    # VERIFY_NOW is the natural pick here but is not permitted.
    decision = policy.decide(
        _features(n_failed_now=1, new_diagnostics_since_last_patch=1),
        policy.PolicyContext(permitted=["CONTINUE", "PAUSE_REPLAN"]),
    )
    assert decision.selected in ("CONTINUE", "PAUSE_REPLAN")
    assert "unsupported-action-fallback" in decision.rationale_codes


def test_repeated_unchanged_advice_suppressed():
    first = policy.decide(_features(), policy.PolicyContext())
    second = policy.decide(
        _features(),
        policy.PolicyContext(
            last_selected=first.selected,
            last_codes=first.rationale_codes,
            new_events_since_last=False,
        ),
    )
    assert second.suppressed
    third = policy.decide(
        _features(),
        policy.PolicyContext(
            last_selected=first.selected,
            last_codes=first.rationale_codes,
            new_events_since_last=True,
        ),
    )
    assert not third.suppressed


def test_jev_pattern_can_flag_loop():
    decision = policy.decide(
        _features(
            n_failed_now=1,
            distinct_patches=2,
            same_assert_after_distinct_patches=1,
            jev_failure_pattern="possible_repeated_attempt",
        ),
        policy.PolicyContext(),
    )
    assert decision.selected == "ESCALATE_DIAGNOSIS"
