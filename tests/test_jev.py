"""Jev client: validation, fail-fast, bounded retries, fallback."""

from __future__ import annotations

import json
from threading import Event

from jev_governor import jev


def _ok_body(**overrides):
    body = {
        "model": "jev-1.13.0",
        "answers": {
            "failure_pattern": {
                "type": "choice",
                "choice": "possible_repeated_attempt",
                "probabilities": {
                    "possible_repeated_attempt": 0.7,
                    "meaningful_investigation": 0.2,
                    "insufficient_evidence": 0.1,
                },
                "confidence": 0.6,
            },
            "hypothesis_repetition": {"type": "noul", "noul": 0.8},
        },
        "usage": {"input_tokens": 300, "output_tokens": 20},
    }
    body.update(overrides)
    return (200, {}, json.dumps(body).encode())


def _run(script, **kwargs):
    params = {
        "state": {"fixture": True},
        "model": "jev-1.13.0",
        "api_key": "test-key",
        "transport": jev.FakeTransport(script),
        "max_attempts": 3,
        "deadline_s": 10.0,
        "per_attempt_timeout_s": 5.0,
        "sleep_fn": lambda s: None,
    }
    params.update(kwargs)
    return jev.evaluate(**params)


def test_ok_path_validates_and_counts_one_attempt():
    result = _run([_ok_body()])
    assert result.ok
    assert result.attempts == 1
    assert result.model_served == "jev-1.13.0"
    assert result.features["failure_pattern"] == "possible_repeated_attempt"
    assert result.features["hypothesis_repetition"] == 0.8
    assert result.usage == {"input_tokens": 300, "output_tokens": 20}


def test_insufficient_evidence_maps_to_none():
    body = _ok_body()
    data = json.loads(body[2].decode())
    data["answers"]["failure_pattern"]["choice"] = "insufficient_evidence"
    result = _run([(200, {}, json.dumps(data).encode())])
    assert result.ok
    assert result.features["failure_pattern"] is None


def test_401_and_422_fail_fast():
    for status, kind in ((401, "unauthorized"), (422, "invalid")):
        result = _run([(status, {}, b"{}")])
        assert not result.ok
        assert result.error_kind == kind
        assert result.attempts == 1


def test_429_retries_then_succeeds_within_budget():
    result = _run([(429, {"retry-after": "0"}, b"{}"), _ok_body()])
    assert result.ok
    assert result.attempts == 2


def test_retry_budget_exhausted_reports_last_error():
    result = _run([(529, {}, b"{}")] * 3)
    assert not result.ok
    assert result.error_kind == "overloaded"
    assert result.attempts == 3


def test_zero_attempts_refuses_without_traffic():
    transport = jev.FakeTransport([_ok_body()])
    result = _run([], transport=transport, max_attempts=0)
    assert not result.ok
    assert result.error_kind == "attempt-budget"
    assert transport.calls == 0


def test_timeout_and_transient_count_attempts():
    result = _run([TimeoutError("t"), ConnectionError("c"), _ok_body()])
    assert result.ok
    assert result.attempts == 3


def test_cancellation_between_attempts():
    cancel = Event()
    cancel.set()
    result = _run([(529, {}, b"{}"), _ok_body()], cancel=cancel)
    assert not result.ok
    assert result.error_kind == "cancelled"
    assert result.attempts == 0


def test_malformed_responses_rejected():
    good = json.loads(_ok_body()[2].decode())

    bad_choice = json.loads(json.dumps(good))
    bad_choice["answers"]["failure_pattern"]["choice"] = "not-an-option"
    result = _run([(200, {}, json.dumps(bad_choice).encode())])
    assert result.error_kind == "malformed-response"

    bad_sum = json.loads(json.dumps(good))
    bad_sum["answers"]["failure_pattern"]["probabilities"]["possible_repeated_attempt"] = 0.1
    result = _run([(200, {}, json.dumps(bad_sum).encode())])
    assert result.error_kind == "malformed-response"

    missing = json.loads(json.dumps(good))
    del missing["answers"]["hypothesis_repetition"]
    result = _run([(200, {}, json.dumps(missing).encode())])
    assert result.error_kind == "malformed-response"

    result = _run([(200, {}, b"not json")])
    assert result.error_kind == "malformed-response"


def test_oversized_response_rejected():
    result = _run([(200, {}, b"x" * (jev.MAX_RESPONSE_BYTES + 10))])
    assert result.error_kind == "oversized-response"


def test_state_builder_is_minimal():
    state = jev.build_state(
        {"same_assert_after_distinct_patches": 2, "transcript": "should-not-appear"}
    )
    assert "transcript" not in state
    assert state["same_assertion_after_distinct_patches"] == 2
