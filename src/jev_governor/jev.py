"""Optional Jev (TypeSafe) semantic feature provider.

Disabled by default. A live call requires ALL of: explicit enablement, a
present key, an approved payload scope, and a bounded attempt/deadline plan.
Credential presence alone is never authorization.

Transport is stdlib urllib with exactly one retry budget owned by this module
(no SDK layering). Every attempt -- including retries and timeouts -- is
counted and its usage preserved (timeouts keep unknown usage).
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from threading import Event
from typing import Any

from .config import JEV_ENDPOINT, JEV_RUBRIC_VERSION

MAX_RESPONSE_BYTES = 256 * 1024

FAILURE_PATTERN_OPTIONS = (
    "possible_repeated_attempt",
    "meaningful_investigation",
    "insufficient_evidence",
)

RUBRICS = {
    JEV_RUBRIC_VERSION: {
        "failure_pattern": {
            "type": "choice",
            "instructions": (
                "Classify only the observed pattern. Do not authorize actions "
                "or certify task success. Use insufficient_evidence when these "
                "fields do not support a classification."
            ),
            "criteria": {
                "possible_repeated_attempt": (
                    "Repeated failure with no recorded diagnostic or hypothesis change"
                ),
                "meaningful_investigation": (
                    "New diagnostic evidence or a changed hypothesis is recorded"
                ),
                "insufficient_evidence": (
                    "The supplied observation is insufficient or contradictory"
                ),
            },
        },
        "hypothesis_repetition": {
            "type": "noul",
            "instructions": (
                "Does the latest recorded hypothesis repeat an earlier one "
                "without new supporting evidence?"
            ),
            "criteria": {
                "true": "Same hypothesis restated with no new evidence",
                "false": "New or changed hypothesis, or new evidence recorded",
            },
        },
    }
}


class JevError(Exception):
    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind


@dataclass
class JevResult:
    ok: bool
    features: dict[str, Any] = field(default_factory=dict)
    model_requested: str = ""
    model_served: str = ""
    rubric_version: str = JEV_RUBRIC_VERSION
    usage: dict[str, int] = field(default_factory=dict)
    latency_ms: int = 0
    attempts: int = 0
    error_kind: str = ""
    error: str = ""


class UrllibTransport:
    """Single-attempt HTTPS POST. Retries are owned by the caller."""

    def post(
        self, url: str, headers: dict[str, str], body: bytes, timeout_s: float
    ) -> tuple[int, dict[str, str], bytes]:
        request = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=timeout_s) as response:
                status = int(response.status)
                resp_headers = {k.lower(): v for k, v in response.headers.items()}
                payload = response.read(MAX_RESPONSE_BYTES + 1)
        except urllib.error.HTTPError as exc:
            try:
                payload = exc.read(MAX_RESPONSE_BYTES + 1)
            except Exception:
                payload = b""
            headers_out = {k.lower(): v for k, v in exc.headers.items()} if exc.headers else {}
            return int(exc.code), headers_out, payload
        return status, resp_headers, payload


class FakeTransport:
    """Scripted transport for tests. Never touches the network."""

    def __init__(self, script: list[Any]) -> None:
        self.script = list(script)
        self.calls = 0

    def post(
        self, url: str, headers: dict[str, str], body: bytes, timeout_s: float
    ) -> tuple[int, dict[str, str], bytes]:
        self.calls += 1
        assert "Authorization" in headers and headers["Authorization"].startswith("Bearer ")
        assert url.startswith("https://api.typesafe.ai/v1/systemone")
        if not self.script:
            raise AssertionError("fake transport script exhausted")
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item  # type: ignore[return-value]


def build_questions(rubric_version: str = JEV_RUBRIC_VERSION) -> dict[str, Any]:
    rubric = RUBRICS.get(rubric_version)
    if rubric is None:
        raise JevError("unknown-rubric", f"unknown rubric version: {rubric_version}")
    return json.loads(json.dumps(rubric))


def build_state(features: dict[str, Any]) -> dict[str, Any]:
    """Project a small structured observation. Never includes transcripts."""
    return {
        "fixture": bool(features.get("fixture", False)),
        "same_assertion_after_distinct_patches": int(
            features.get("same_assert_after_distinct_patches", 0) or 0
        ),
        "new_diagnostics_since_last_patch": int(
            features.get("new_diagnostics_since_last_patch", 0) or 0
        ),
        "hypothesis_changed": bool(features.get("hypothesis_changed", False)),
        "n_failed_now": int(features.get("n_failed_now", 0) or 0),
        "n_remaining": int(features.get("n_remaining", 0) or 0),
    }


def _validate_choice(answer: Any, options: tuple[str, ...], qid: str) -> dict[str, Any]:
    if not isinstance(answer, dict):
        raise JevError("malformed-response", f"{qid}: answer must be an object")
    if answer.get("type") != "choice":
        raise JevError("malformed-response", f"{qid}: expected type=choice")
    choice = answer.get("choice")
    if choice not in options:
        raise JevError("malformed-response", f"{qid}: invalid choice {choice!r}")
    probs = answer.get("probabilities", {})
    if not isinstance(probs, dict) or set(probs) != set(options):
        raise JevError("malformed-response", f"{qid}: probabilities must cover options")
    total = 0.0
    for key, value in probs.items():
        if not isinstance(value, int | float) or isinstance(value, bool):
            raise JevError("malformed-response", f"{qid}: bad probability for {key}")
        if not 0.0 <= float(value) <= 1.0:
            raise JevError("malformed-response", f"{qid}: probability out of range")
        total += float(value)
    if abs(total - 1.0) > 1e-3:
        raise JevError("malformed-response", f"{qid}: probabilities sum to {total}")
    confidence = answer.get("confidence")
    if (
        not isinstance(confidence, int | float)
        or isinstance(confidence, bool)
        or not 0.0 <= float(confidence) <= 1.0
    ):
        raise JevError("malformed-response", f"{qid}: bad confidence")
    return {"choice": choice, "probabilities": probs, "confidence": float(confidence)}


def _validate_noul(answer: Any, qid: str) -> dict[str, Any]:
    if not isinstance(answer, dict):
        raise JevError("malformed-response", f"{qid}: answer must be an object")
    if answer.get("type") != "noul":
        raise JevError("malformed-response", f"{qid}: expected type=noul")
    value = answer.get("noul")
    if (
        not isinstance(value, int | float)
        or isinstance(value, bool)
        or not 0.0 <= float(value) <= 1.0
    ):
        raise JevError("malformed-response", f"{qid}: bad noul value")
    return {"noul": float(value)}


def validate_response(
    body: bytes, expected_questions: dict[str, Any]
) -> tuple[str, dict[str, Any], dict[str, int]]:
    """Strict typed validation. Returns (model_served, features, usage)."""
    if len(body) > MAX_RESPONSE_BYTES:
        raise JevError("oversized-response", "response exceeds size bound")
    try:
        data = json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise JevError("malformed-response", f"response is not JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise JevError("malformed-response", "response must be an object")
    model_served = data.get("model")
    if not isinstance(model_served, str) or not model_served:
        raise JevError("malformed-response", "missing served model id")
    answers = data.get("answers")
    if not isinstance(answers, dict):
        raise JevError("malformed-response", "missing answers map")
    features: dict[str, Any] = {}
    for qid in expected_questions:
        if qid not in answers:
            raise JevError("malformed-response", f"missing answer: {qid}")
    choice = _validate_choice(
        answers["failure_pattern"], FAILURE_PATTERN_OPTIONS, "failure_pattern"
    )
    features["failure_pattern"] = (
        None if choice["choice"] == "insufficient_evidence" else choice["choice"]
    )
    features["failure_pattern_confidence"] = choice["confidence"]
    features["hypothesis_repetition"] = _validate_noul(
        answers["hypothesis_repetition"], "hypothesis_repetition"
    )["noul"]
    usage: dict[str, int] = {}
    raw_usage = data.get("usage", {})
    if isinstance(raw_usage, dict):
        for key in ("input_tokens", "output_tokens"):
            value = raw_usage.get(key)
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                usage[key] = value
    return model_served, features, usage


def evaluate(
    *,
    state: dict[str, Any],
    model: str,
    api_key: str,
    transport: Any,
    max_attempts: int,
    deadline_s: float,
    per_attempt_timeout_s: float,
    rubric_version: str = JEV_RUBRIC_VERSION,
    cancel: Event | None = None,
    sleep_fn: Any = None,
) -> JevResult:
    """Run one bounded Jev evaluation. Single retry budget, fail-fast auth."""
    started = time.monotonic()
    questions = build_questions(rubric_version)
    body = json.dumps({"model": model, "state": state, "questions": questions}).encode("utf-8")
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    sleep = sleep_fn or time.sleep
    result = JevResult(ok=False, model_requested=model, rubric_version=rubric_version)
    if max_attempts < 1:
        result.error_kind = "attempt-budget"
        result.error = "live attempts not authorized (max_attempts<1)"
        return result
    attempt = 0
    last_error = "no-attempt"
    last_kind = "attempt-budget"
    while attempt < max_attempts:
        if cancel is not None and cancel.is_set():
            last_kind, last_error = "cancelled", "cancelled before attempt"
            break
        remaining = deadline_s - (time.monotonic() - started)
        if remaining <= 0:
            last_kind, last_error = "timeout", "absolute deadline exceeded"
            break
        attempt += 1
        result.attempts = attempt
        try:
            status, resp_headers, payload = transport.post(
                JEV_ENDPOINT, headers, body, min(per_attempt_timeout_s, remaining)
            )
        except TimeoutError as exc:
            last_kind, last_error = "timeout", f"attempt {attempt} timed out: {exc}"
            continue
        except (ConnectionError, OSError) as exc:
            last_kind, last_error = "transient", f"attempt {attempt} network error: {exc}"
            continue
        except Exception as exc:  # fake-transport scripted errors surface here
            name = type(exc).__name__
            if name in ("TimeoutError", "timeout"):
                last_kind, last_error = "timeout", f"attempt {attempt} timed out"
            else:
                last_kind, last_error = "transient", f"attempt {attempt}: {name}: {exc}"
            continue
        if status == 401:
            last_kind, last_error = "unauthorized", "401: missing or invalid API key"
            break
        if status == 422:
            last_kind, last_error = "invalid", "422: request failed validation"
            break
        if status in (429, 529):
            last_kind = "rate-limited" if status == 429 else "overloaded"
            last_error = f"{status}: back off and retry within budget"
            if attempt < max_attempts:
                try:
                    delay = float(resp_headers.get("retry-after", "1"))
                except ValueError:
                    delay = 1.0
                delay = min(max(delay, 0.1), max(0.0, deadline_s - (time.monotonic() - started)))
                if delay > 0:
                    sleep(min(delay, 5.0))
            continue
        if status == 200:
            try:
                served, features, usage = validate_response(payload, questions)
            except JevError as exc:
                last_kind, last_error = exc.kind, str(exc)
                break
            result.ok = True
            result.features = features
            result.model_served = served
            result.usage = usage
            result.latency_ms = int((time.monotonic() - started) * 1000)
            return result
        if 500 <= status < 600:
            last_kind, last_error = "server", f"{status}: server failure"
            if attempt < max_attempts:
                sleep(min(1.0, max(0.0, deadline_s - (time.monotonic() - started))))
            continue
        last_kind, last_error = "unexpected-status", f"{status}: unexpected status"
        break
    result.error_kind = last_kind
    result.error = last_error
    result.latency_ms = int((time.monotonic() - started) * 1000)
    return result
