"""JSONL ingestion: validation, provenance enforcement, idempotent projections."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import accounting, evidence
from .schemas import MAX_EVENT_BYTES, SchemaError, validate_envelope
from .storage import SessionRow, ensure_session, get_session, insert_event

MAX_IMPORT_BYTES = 64 * 1024 * 1024

# Provenance values the file-import path may assign. Anything stronger claimed
# inside the file is stripped back to ``imported`` with a diagnostic.
IMPORT_PROVENANCE = "imported"
FIXTURE_PROVENANCE = "synthetic"


@dataclass
class ImportSummary:
    session_id: str
    accepted: int = 0
    duplicates: int = 0
    rejected: int = 0
    diagnostics: list[str] = field(default_factory=list)


def _payload(row: sqlite3.Row) -> dict[str, Any]:
    return evidence.payload_json(row)


def apply_projection(conn: sqlite3.Connection, session_id: str, event: sqlite3.Row) -> None:
    """Apply one stored event to the derived tables (deterministic)."""
    etype = event["event_type"]
    payload = _payload(event)
    seq = int(event["seq"])
    provenance = event["provenance"]

    if etype == "session.started":
        ensure_session(
            conn,
            SessionRow(
                session_id=session_id,
                workspace=str(payload.get("workspace", ""))[:512],
                base_rev=str(payload.get("base_rev", ""))[:256],
                adapter=str(payload.get("adapter", ""))[:128],
                adapter_version=str(payload.get("adapter_version", ""))[:128],
                label=str(payload.get("label", ""))[:256],
                fixture=provenance == FIXTURE_PROVENANCE,
                budget=payload.get("budget") if isinstance(payload.get("budget"), dict) else {},
            ),
        )
        # Merge budget if the session row already existed without one.
        if isinstance(payload.get("budget"), dict) and payload["budget"]:
            conn.execute(
                "UPDATE sessions SET budget_json=? WHERE session_id=? AND budget_json='{}'",
                (json.dumps(payload["budget"]), session_id),
            )
        # Merge session identity fields (import creates the row first, so an
        # UPDATE is required; only non-empty values overwrite).
        identity = {}
        for key, column, width in (
            ("workspace", "workspace", 512),
            ("base_rev", "base_rev", 256),
            ("adapter", "adapter", 128),
            ("adapter_version", "adapter_version", 128),
            ("label", "label", 256),
        ):
            value = str(payload.get(key, ""))[:width]
            if value:
                identity[column] = value
        if identity:
            assignments = ", ".join(f"{column}=?" for column in identity)
            conn.execute(
                f"UPDATE sessions SET {assignments} WHERE session_id=?",
                (*identity.values(), session_id),
            )
    elif etype in (
        "requirement.proposed",
        "requirement.accepted",
        "requirement.updated",
        "requirement.blocked",
    ):
        req_id = str(payload.get("req_id", ""))[:256]
        if not req_id:
            return
        origin = str(payload.get("origin", "inferred"))
        if origin not in ("user", "inferred"):
            origin = "inferred"
        row = conn.execute(
            "SELECT COALESCE(MAX(version), 0) AS m FROM requirements "
            "WHERE session_id=? AND req_id=?",
            (session_id, req_id),
        ).fetchone()
        current = conn.execute(
            "SELECT origin, text_ref, acceptance_json, state FROM requirements "
            "WHERE session_id=? AND req_id=? ORDER BY version DESC LIMIT 1",
            (session_id, req_id),
        ).fetchone()
        base_origin = current["origin"] if current else origin
        # Origin is sticky: only an explicit user statement at proposal time
        # sets user origin; later claims cannot flip inferred -> user silently.
        if current is None:
            base_origin = origin
        text_ref = str(payload.get("text_ref", current["text_ref"] if current else ""))[:2048]
        acceptance = payload.get("acceptance", None)
        if not isinstance(acceptance, dict):
            try:
                acceptance = json.loads(current["acceptance_json"]) if current else {}
            except ValueError:
                acceptance = {}
        state = "unknown"
        if etype == "requirement.blocked":
            state = "blocked"
        elif etype in ("requirement.accepted", "requirement.updated"):
            state = "candidate"
        conn.execute(
            """
            INSERT INTO requirements(session_id, req_id, version, origin, text_ref,
                                     acceptance_json, state, updated_seq)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                req_id,
                int(row["m"]) + 1,
                base_origin,
                text_ref,
                json.dumps(acceptance),
                state,
                seq,
            ),
        )
    elif etype in ("check.completed", "tool.completed"):
        check_id = str(payload.get("check_id", "") or event["event_id"])[:256]
        req_ids = payload.get("req_ids", [])
        if not isinstance(req_ids, list):
            req_ids = []
        exit_status = payload.get("exit_status")
        if not isinstance(exit_status, int) or isinstance(exit_status, bool):
            exit_status = None
        conn.execute(
            """
            INSERT INTO checks(check_id, session_id, req_ids_json, recipe_id, executor,
                               exit_status, disposition, env_fp, repo_fp_json,
                               started_at, ended_at, provenance, event_seq)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id, check_id) DO NOTHING
            """,
            (
                check_id,
                session_id,
                json.dumps([str(r) for r in req_ids if isinstance(r, str)][:64]),
                str(payload.get("recipe_id", ""))[:256],
                str(payload.get("executor", ""))[:256],
                exit_status,
                str(payload.get("disposition", "completed"))[:64],
                str(payload.get("env_fp", ""))[:512],
                json.dumps(
                    payload.get("repo_fp", {}) if isinstance(payload.get("repo_fp"), dict) else {}
                ),
                str(payload.get("started_at", ""))[:64],
                str(payload.get("ended_at", ""))[:64],
                provenance,
                seq,
            ),
        )
    elif etype == "usage.reported":
        usage = accounting.normalize_usage(
            payload.get("usage", payload.get("raw")), str(payload.get("provider", ""))
        )
        kind = str(payload.get("kind", "unknown"))
        if kind not in ("delta", "cumulative", "governor", "unknown"):
            kind = "unknown"
        stream_seq = payload.get("stream_seq", 0)
        if not isinstance(stream_seq, int) or isinstance(stream_seq, bool):
            stream_seq = 0
        elapsed = payload.get("elapsed_ms")
        if not isinstance(elapsed, int) or isinstance(elapsed, bool):
            elapsed = None
        conn.execute(
            """
            INSERT INTO usage_ledger(session_id, event_id, stream_id, epoch, stream_seq,
                                     kind, provider, model_requested, model_served, effort,
                                     in_tokens, cached_in_tokens, out_tokens,
                                     reasoning_out_tokens, total_tokens, complete,
                                     elapsed_ms, raw_json, note)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(event_id) DO NOTHING
            """,
            (
                session_id,
                event["event_id"],
                str(payload.get("stream_id", ""))[:256],
                str(payload.get("epoch", ""))[:256],
                stream_seq,
                kind,
                str(payload.get("provider", ""))[:128],
                str(payload.get("model_requested", ""))[:256],
                str(payload.get("model_served", ""))[:256],
                str(payload.get("effort", ""))[:64],
                usage.in_tokens,
                usage.cached_in_tokens,
                usage.out_tokens,
                usage.reasoning_out_tokens,
                usage.total_tokens,
                1 if usage.complete else 0,
                elapsed,
                json.dumps(payload.get("usage", payload.get("raw", {}))),
                usage.note[:512],
            ),
        )
    elif etype == "evaluation.completed":
        outcome = str(payload.get("outcome", ""))
        if outcome not in (
            "verified_success",
            "failed_evaluation",
            "unresolved_budget",
            "blocked",
            "cancelled",
            "evaluation_unavailable",
        ):
            outcome = "failed_evaluation"
        conn.execute(
            """
            INSERT INTO evaluations(eval_id, session_id, outcome, evaluator,
                                    evaluator_version, repo_fp_json, coverage_json,
                                    independent, created_at)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(eval_id) DO NOTHING
            """,
            (
                str(payload.get("eval_id", "") or event["event_id"])[:256],
                session_id,
                outcome,
                str(payload.get("evaluator", ""))[:256],
                str(payload.get("evaluator_version", ""))[:128],
                json.dumps(
                    payload.get("repo_fp", {}) if isinstance(payload.get("repo_fp"), dict) else {}
                ),
                json.dumps(
                    payload.get("coverage", {}) if isinstance(payload.get("coverage"), dict) else {}
                ),
                1 if payload.get("independent") else 0,
                event["observed_at"],
            ),
        )
    elif etype == "feedback.recorded":
        conn.execute(
            """
            INSERT INTO feedback(feedback_id, session_id, kind, text, created_at)
            VALUES(?, ?, ?, ?, ?)
            ON CONFLICT(feedback_id) DO NOTHING
            """,
            (
                str(payload.get("feedback_id", "") or event["event_id"])[:256],
                session_id,
                str(payload.get("kind", "note"))[:64],
                str(payload.get("text", ""))[:4096],
                event["observed_at"],
            ),
        )


def import_envelopes(
    conn: sqlite3.Connection,
    session_id: str,
    envelopes: list[dict[str, Any]],
    *,
    source_path: str,
    fixture: bool = False,
    max_diagnostics: int = 50,
) -> ImportSummary:
    """Import pre-built envelope dicts (e.g. from an adapter converter)."""
    summary = ImportSummary(session_id=session_id)
    ensure_session(conn, SessionRow(session_id=session_id, fixture=fixture))
    provenance = FIXTURE_PROVENANCE if fixture else IMPORT_PROVENANCE
    for lineno, raw in enumerate(envelopes, start=1):
        try:
            event = validate_envelope(raw)
        except SchemaError as exc:
            summary.rejected += 1
            if len(summary.diagnostics) < max_diagnostics:
                summary.diagnostics.append(f"item-{lineno}:schema:{exc}")
            continue
        if event["session_id"] != session_id:
            summary.rejected += 1
            if len(summary.diagnostics) < max_diagnostics:
                summary.diagnostics.append(f"item-{lineno}:cross-session:{event['session_id']}")
            continue
        claimed = event["provenance"]
        if claimed in ("trusted", "evaluator", "observed", "human") and not fixture:
            if len(summary.diagnostics) < max_diagnostics:
                summary.diagnostics.append(
                    f"item-{lineno}:provenance-claim-stripped:{claimed}->imported"
                )
        seq = insert_event(
            conn,
            event_id=event["event_id"],
            session_id=session_id,
            event_type=event["event_type"],
            provenance=provenance,
            source=event["source"],
            source_version=event["source_version"],
            observed_at=event["observed_at"],
            payload=event["payload"],
        )
        if seq is None:
            summary.duplicates += 1
            continue
        row = conn.execute("SELECT * FROM events WHERE event_id=?", (event["event_id"],)).fetchone()
        assert row is not None
        apply_projection(conn, session_id, row)
        summary.accepted += 1
    conn.execute(
        """
        INSERT INTO import_runs(session_id, source_path, accepted, duplicates,
                                rejected, diagnostics_json, created_at)
        VALUES(?, ?, ?, ?, ?, ?, datetime('now'))
        """,
        (
            session_id,
            source_path,
            summary.accepted,
            summary.duplicates,
            summary.rejected,
            json.dumps(summary.diagnostics[:max_diagnostics]),
        ),
    )
    conn.commit()
    return summary


def import_jsonl(
    conn: sqlite3.Connection,
    session_id: str,
    path: Path,
    *,
    fixture: bool = False,
    max_diagnostics: int = 50,
) -> ImportSummary:
    """Import a JSONL file into a session. Idempotent on re-import."""
    summary = ImportSummary(session_id=session_id)
    try:
        size = path.stat().st_size
    except FileNotFoundError:
        summary.rejected = 1
        summary.diagnostics.append(f"file-not-found:{path}")
        return summary
    if size > MAX_IMPORT_BYTES:
        summary.rejected = 1
        summary.diagnostics.append(f"file-too-large:{size}-bytes")
        return summary
    ensure_session(conn, SessionRow(session_id=session_id, fixture=fixture))
    provenance = FIXTURE_PROVENANCE if fixture else IMPORT_PROVENANCE
    with path.open("r", encoding="utf-8") as handle:
        for lineno, line in enumerate(handle, start=1):
            if len(line.encode("utf-8")) > MAX_EVENT_BYTES + 1024:
                summary.rejected += 1
                if len(summary.diagnostics) < max_diagnostics:
                    summary.diagnostics.append(f"line-{lineno}:event-too-large")
                continue
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
            except ValueError:
                summary.rejected += 1
                if len(summary.diagnostics) < max_diagnostics:
                    summary.diagnostics.append(f"line-{lineno}:invalid-json")
                continue
            try:
                event = validate_envelope(raw)
            except SchemaError as exc:
                summary.rejected += 1
                if len(summary.diagnostics) < max_diagnostics:
                    summary.diagnostics.append(f"line-{lineno}:schema:{exc}")
                continue
            if event["session_id"] != session_id:
                summary.rejected += 1
                if len(summary.diagnostics) < max_diagnostics:
                    summary.diagnostics.append(f"line-{lineno}:cross-session:{event['session_id']}")
                continue
            claimed = event["provenance"]
            if claimed in ("trusted", "evaluator", "observed", "human") and not fixture:
                # Forged authority via file import is stripped, never honored.
                if len(summary.diagnostics) < max_diagnostics:
                    summary.diagnostics.append(
                        f"line-{lineno}:provenance-claim-stripped:{claimed}->imported"
                    )
            effective = provenance
            seq = insert_event(
                conn,
                event_id=event["event_id"],
                session_id=session_id,
                event_type=event["event_type"],
                provenance=effective,
                source=event["source"],
                source_version=event["source_version"],
                observed_at=event["observed_at"],
                payload=event["payload"],
            )
            if seq is None:
                summary.duplicates += 1
                continue
            row = conn.execute(
                "SELECT * FROM events WHERE event_id=?", (event["event_id"],)
            ).fetchone()
            assert row is not None
            apply_projection(conn, session_id, row)
            summary.accepted += 1
    conn.execute(
        """
        INSERT INTO import_runs(session_id, source_path, accepted, duplicates,
                                rejected, diagnostics_json, created_at)
        VALUES(?, ?, ?, ?, ?, ?, datetime('now'))
        """,
        (
            session_id,
            str(path),
            summary.accepted,
            summary.duplicates,
            summary.rejected,
            json.dumps(summary.diagnostics[:max_diagnostics]),
        ),
    )
    conn.commit()
    return summary


def rebuild_session(conn: sqlite3.Connection, session_id: str) -> int:
    """Re-derive all projections from stored events. Returns event count."""
    if get_session(conn, session_id) is None:
        return 0
    for table in (
        "requirements",
        "checks",
        "usage_ledger",
        "decisions",
        "feedback",
        "evaluations",
        "import_runs",
    ):
        conn.execute(f"DELETE FROM {table} WHERE session_id=?", (session_id,))
    rows = conn.execute(
        "SELECT * FROM events WHERE session_id=? ORDER BY seq", (session_id,)
    ).fetchall()
    for row in rows:
        apply_projection(conn, session_id, row)
    conn.commit()
    return len(rows)
