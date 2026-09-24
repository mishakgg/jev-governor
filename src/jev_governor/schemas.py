"""Versioned event envelope, vocabularies, and validation bounds (schema v1)."""

from __future__ import annotations

from datetime import UTC, datetime

SCHEMA_VERSION = 1

MAX_EVENT_BYTES = 65_536
MAX_STRING_LEN = 8_192
MAX_LIST_LEN = 512
MAX_PAYLOAD_KEYS = 128

EVENT_TYPES = frozenset(
    {
        "session.started",
        "session.ended",
        "requirement.proposed",
        "requirement.accepted",
        "requirement.updated",
        "requirement.blocked",
        "checkpoint.observed",
        "usage.reported",
        "tool.completed",
        "check.completed",
        "patch.observed",
        "hypothesis.recorded",
        "diagnostic.recorded",
        "recommendation.issued",
        "intervention.requested",
        "intervention.applied",
        "intervention.failed",
        "intervention.unknown",
        "feedback.recorded",
        "evaluation.completed",
        "evaluation.unavailable",
    }
)

PROVENANCE_VALUES = frozenset(
    {"synthetic", "imported", "observed", "trusted", "evaluator", "human"}
)

# Provenance values that may support a verified requirement state.
AUTHORITATIVE_PROVENANCE = frozenset({"trusted", "evaluator"})

REQUIREMENT_STATES = frozenset(
    {"unknown", "candidate", "partially_verified", "verified", "failed", "blocked"}
)

REQUIREMENT_ORIGINS = frozenset({"user", "inferred"})

TERMINAL_OUTCOMES = frozenset(
    {
        "verified_success",
        "failed_evaluation",
        "unresolved_budget",
        "blocked",
        "cancelled",
        "evaluation_unavailable",
        "incomplete",
    }
)

RECIPES = ("CONTINUE", "ECONOMICAL_CONTINUE", "ESCALATE_DIAGNOSIS", "VERIFY_NOW", "PAUSE_REPLAN")

USAGE_KINDS = frozenset({"delta", "cumulative", "governor", "unknown"})

ENVELOPE_REQUIRED = (
    "schema_version",
    "event_id",
    "session_id",
    "event_type",
    "source",
    "source_version",
    "observed_at",
    "provenance",
)


class SchemaError(ValueError):
    """Raised when a record violates the versioned schema."""


def utcnow_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def parse_observed_at(value: object) -> datetime:
    if not isinstance(value, str) or not value:
        raise SchemaError("observed_at must be a non-empty ISO-8601 string")
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise SchemaError(f"observed_at is not valid ISO-8601: {value!r}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def check_string_bound(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise SchemaError(f"{field} must be a string")
    if len(value) > MAX_STRING_LEN:
        raise SchemaError(f"{field} exceeds {MAX_STRING_LEN} characters")
    return value


def validate_envelope(raw: dict) -> dict:
    """Validate the event envelope; return a normalized shallow copy.

    The payload is bounds-checked but its per-type semantics are validated by
    the ingestion layer. Unknown provenance never upgrades: callers decide the
    effective provenance from the ingress path, not from this field alone.
    """
    if not isinstance(raw, dict):
        raise SchemaError("event must be a JSON object")
    for key in ENVELOPE_REQUIRED:
        if key not in raw:
            raise SchemaError(f"missing required field: {key}")
    if raw["schema_version"] != SCHEMA_VERSION:
        raise SchemaError(f"unsupported schema_version: {raw.get('schema_version')!r}")
    event_type = raw["event_type"]
    if event_type not in EVENT_TYPES:
        raise SchemaError(f"unsupported event_type: {event_type!r}")
    provenance = raw["provenance"]
    if provenance not in PROVENANCE_VALUES:
        raise SchemaError(f"unsupported provenance: {provenance!r}")
    for key in ("event_id", "session_id", "source", "source_version"):
        check_string_bound(raw[key], key)
        if not str(raw[key]).strip():
            raise SchemaError(f"{key} must be non-empty")
    parse_observed_at(raw["observed_at"])
    payload = raw.get("payload", {})
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        raise SchemaError("payload must be an object")
    if len(payload) > MAX_PAYLOAD_KEYS:
        raise SchemaError("payload has too many keys")
    for key, value in payload.items():
        if not isinstance(key, str) or len(key) > 256:
            raise SchemaError("payload key must be a short string")
        if isinstance(value, str) and len(value) > MAX_STRING_LEN:
            raise SchemaError(f"payload.{key} exceeds {MAX_STRING_LEN} characters")
        if isinstance(value, list) and len(value) > MAX_LIST_LEN:
            raise SchemaError(f"payload.{key} exceeds {MAX_LIST_LEN} items")
    normalized = dict(raw)
    normalized["payload"] = payload
    return normalized
