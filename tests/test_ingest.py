"""Ingestion: idempotency, malformed input, forged trust, cross-session."""

from __future__ import annotations

from pathlib import Path

from jev_governor import ingest, reporting

DATA = Path(__file__).parent / "data"


def test_malformed_file_reports_diagnostics(conn):
    summary = ingest.import_jsonl(conn, "test-malformed", DATA / "malformed.jsonl")
    assert summary.accepted == 2
    assert summary.rejected == 5
    text = " ".join(summary.diagnostics)
    assert "invalid-json" in text
    assert "unsupported schema_version" in text or "schema" in text
    assert "cross-session" in text


def test_idempotent_reimport_counts_duplicates(conn):
    first = ingest.import_jsonl(conn, "test-malformed", DATA / "malformed.jsonl")
    second = ingest.import_jsonl(conn, "test-malformed", DATA / "malformed.jsonl")
    assert first.accepted == 2
    assert second.accepted == 0
    assert second.duplicates == 2
    assert second.rejected == first.rejected


def test_forged_trust_stripped_and_never_verified(conn):
    summary = ingest.import_jsonl(conn, "test-forged", DATA / "forged.jsonl")
    assert summary.accepted == 5
    assert any("provenance-claim-stripped" in d for d in summary.diagnostics)
    view = reporting.ledger_view(conn, "test-forged")
    assert view["requirements"][0]["state"] in ("candidate", "partially_verified")
    assert view["requirements"][0]["state"] != "verified"
    assert view["terminal_outcome"] == "incomplete"
    stored = conn.execute("SELECT provenance FROM checks WHERE session_id='test-forged'").fetchone()
    assert stored["provenance"] == "imported"


def test_missing_file_reported(conn, tmp_path):
    summary = ingest.import_jsonl(conn, "s-missing", tmp_path / "nope.jsonl")
    assert summary.rejected == 1
    assert "file-not-found" in summary.diagnostics[0]


def test_oversized_line_rejected(conn, tmp_path):
    path = tmp_path / "big.jsonl"
    path.write_text('{"event_id": "x", "blob": "' + "y" * 70000 + '"}\n', encoding="utf-8")
    summary = ingest.import_jsonl(conn, "s-big", path)
    assert summary.accepted == 0
    assert summary.rejected == 1


def test_rebuild_is_deterministic(conn):
    ingest.import_jsonl(conn, "test-forged", DATA / "forged.jsonl")
    before = reporting.ledger_view(conn, "test-forged")
    count = ingest.rebuild_session(conn, "test-forged")
    after = reporting.ledger_view(conn, "test-forged")
    assert count == 5
    assert before == after
