"""Persistence: restart, retention, export safety, unknown usage."""

from __future__ import annotations

import json
from pathlib import Path

from jev_governor import config, ingest, reporting, storage
from jev_governor import demo as demo_mod
from jev_governor import export as export_mod

FIXTURES = Path(demo_mod.fixture_path("demo-loop.jsonl")).parent


def test_restart_preserves_state(settings):
    conn = storage.connect(settings)
    ingest.import_jsonl(conn, "demo-loop", FIXTURES / "demo-loop.jsonl", fixture=True)
    conn.close()
    reopened = storage.connect(settings)
    view = reporting.ledger_view(reopened, "demo-loop")
    assert view["event_count"] == 9
    assert view["requirements"][0]["req_id"] == "R1"
    reopened.close()


def test_export_default_has_no_raw_transcript(conn, tmp_path):
    ingest.import_jsonl(conn, "s-exp", FIXTURES / "demo-loop.jsonl", fixture=True)
    out = tmp_path / "exp.jsonl"
    result = export_mod.export_session(conn, "s-exp", out)
    assert result["records"] >= 2
    text = out.read_text(encoding="utf-8")
    assert "TYPESAFE_API_KEY" not in text
    assert "api_key" not in text.lower()
    first = json.loads(text.splitlines()[0])
    assert first["record"] == "manifest"
    assert first["include_raw"] is False


def test_missing_terminal_usage_flagged(conn):
    envelopes = [
        {
            "schema_version": 1,
            "event_id": f"u-e{i}",
            "session_id": "s-nousage",
            "event_type": t,
            "source": "test",
            "source_version": "1",
            "observed_at": "2026-01-01T00:00:00Z",
            "provenance": "synthetic",
            "payload": p,
        }
        for i, (t, p) in enumerate(
            [
                ("session.started", {"workspace": "demo://x"}),
                ("usage.reported", {"kind": "unknown", "provider": "openai-codex"}),
                ("session.ended", {"reason": "done"}),
            ]
        )
    ]
    ingest.import_envelopes(conn, "s-nousage", envelopes, source_path="test", fixture=True)
    view = reporting.ledger_view(conn, "s-nousage")
    assert view["usage"]["unknown_ops"] == 1
    assert view["usage"]["total_tokens"] == 0
    assert view["terminal_outcome"] == "incomplete"


def test_prune_and_delete(conn, settings):
    ingest.import_jsonl(conn, "demo-loop", FIXTURES / "demo-loop.jsonl", fixture=True)
    conn.execute(
        "UPDATE sessions SET created_at='2020-01-01T00:00:00+00:00' " "WHERE session_id='demo-loop'"
    )
    conn.commit()
    removed = storage.prune_sessions_older_than(conn, "2021-01-01T00:00:00+00:00")
    assert removed == ["demo-loop"]
    assert storage.get_session(conn, "demo-loop") is None
    assert conn.execute("SELECT COUNT(*) AS c FROM events").fetchone()["c"] == 0


def test_settings_never_carry_secret(monkeypatch, tmp_path):
    monkeypatch.setenv("TYPESAFE_API_KEY", "super-secret-value")
    settings = config.load_settings(tmp_path)
    assert settings.api_key_present is True
    assert "super-secret-value" not in repr(settings)
    assert "super-secret-value" not in str(settings.__dict__)
