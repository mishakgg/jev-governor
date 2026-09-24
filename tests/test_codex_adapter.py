"""Codex adapter: probe shape and rollout conversion."""

from __future__ import annotations

from pathlib import Path

from jev_governor import codex_adapter, ingest, reporting

DATA = Path(__file__).parent / "data"


def test_probe_missing_binary_reports_unavailable():
    probe = codex_adapter.probe(codex_bin="definitely-not-a-real-binary-xyz")
    assert probe["present"] is False
    assert probe["version"] == ""
    statuses = {c["name"]: c["status"] for c in probe["capabilities"]}
    assert statuses["runtime.present"] == "unavailable"
    assert statuses["control.apply"] == "unsupported"


def test_probe_never_contains_secrets():
    probe = codex_adapter.probe()
    blob = str(probe)
    assert "Bearer" not in blob
    assert "sk-" not in blob
    assert "api_key" not in blob.lower()


def test_rollout_conversion_is_minimal_and_cumulative(conn):
    conv = codex_adapter.convert_rollout(DATA / "sample_rollout.jsonl", "s-codex")
    assert conv.cli_version == "0.146.0-test"
    assert conv.rejected == 0
    kinds = [e["event_type"] for e in conv.envelopes]
    assert "session.started" in kinds
    assert kinds.count("usage.reported") == 2
    assert kinds.count("checkpoint.observed") >= 2
    # Content-bearing records are dropped, never imported.
    assert "SECRET-CONTENT" not in str(conv.envelopes)
    summary = ingest.import_envelopes(conn, "s-codex", conv.envelopes, source_path="test:rollout")
    assert summary.accepted == len(conv.envelopes)
    view = reporting.ledger_view(conn, "s-codex")
    # Cumulative thread totals differenced: 1500 in / 80 out.
    assert view["usage"]["input_tokens"] == 1500
    assert view["usage"]["output_tokens"] == 80
    assert view["usage"]["cached_input_tokens_subset"] == 150
    assert view["usage"]["reasoning_output_tokens_subset"] == 20
    assert view["adapter"] == "codex-cli"
