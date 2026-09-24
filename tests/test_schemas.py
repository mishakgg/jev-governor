"""Envelope validation and bounds."""

from __future__ import annotations

import pytest

from jev_governor.schemas import SchemaError, validate_envelope


def _envelope(**overrides):
    base = {
        "schema_version": 1,
        "event_id": "e1",
        "session_id": "s1",
        "event_type": "session.started",
        "source": "test",
        "source_version": "1",
        "observed_at": "2026-01-01T00:00:00Z",
        "provenance": "imported",
        "payload": {},
    }
    base.update(overrides)
    return base


def test_valid_envelope_passes():
    assert validate_envelope(_envelope())["event_id"] == "e1"


def test_missing_field_rejected():
    bad = _envelope()
    del bad["event_id"]
    with pytest.raises(SchemaError):
        validate_envelope(bad)


def test_unsupported_schema_version_rejected():
    with pytest.raises(SchemaError):
        validate_envelope(_envelope(schema_version=99))


def test_unknown_event_type_rejected():
    with pytest.raises(SchemaError):
        validate_envelope(_envelope(event_type="bogus.event"))


def test_unknown_provenance_rejected():
    with pytest.raises(SchemaError):
        validate_envelope(_envelope(provenance="definitely-trustworthy"))


def test_bad_timestamp_rejected():
    with pytest.raises(SchemaError):
        validate_envelope(_envelope(observed_at="not-a-time"))


def test_oversized_payload_string_rejected():
    with pytest.raises(SchemaError):
        validate_envelope(_envelope(payload={"blob": "x" * 9000}))


def test_oversized_payload_list_rejected():
    with pytest.raises(SchemaError):
        validate_envelope(_envelope(payload={"items": [1] * 600}))
