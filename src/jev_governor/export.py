"""Privacy-safe export: manifest + decision/outcome records as JSONL.

Default exports carry structured minimal observations (features, decisions,
totals) -- never raw prompts, transcripts, source files, or auth details.
Full event dumps require explicit --include-raw and are still local files.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from . import reporting
from .schemas import SCHEMA_VERSION

EXPORT_VERSION = 1


def _redact_text(value: str, keep: int = 120) -> str:
    return value[:keep]


def export_session(
    conn: sqlite3.Connection,
    session_id: str,
    out_path: Path,
    *,
    include_raw: bool = False,
    group_id: str | None = None,
) -> dict[str, Any]:
    view = reporting.ledger_view(conn, session_id)
    decisions = [
        dict(r)
        for r in conn.execute(
            "SELECT * FROM decisions WHERE session_id=? ORDER BY cutoff_seq",
            (session_id,),
        ).fetchall()
    ]
    feedback_rows = [
        dict(r)
        for r in conn.execute(
            "SELECT kind, text FROM feedback WHERE session_id=?", (session_id,)
        ).fetchall()
    ]
    lines: list[str] = []
    manifest = {
        "record": "manifest",
        "export_version": EXPORT_VERSION,
        "schema_version": SCHEMA_VERSION,
        "session_id": session_id,
        "group_id": group_id or session_id,
        "fixture": view["fixture"],
        "provenance": "synthetic" if view["fixture"] else "local-session",
        "include_raw": include_raw,
        "usage_completeness": {
            "unknown_ops": view["usage"]["unknown_ops"],
            "resets": len(view["usage"]["resets"]),
        },
    }
    lines.append(json.dumps(manifest))
    for decision in decisions:
        try:
            features = json.loads(decision["features_json"] or "{}")
        except ValueError:
            features = {}
        lines.append(
            json.dumps(
                {
                    "record": "decision",
                    "decision_id": decision["decision_id"],
                    "session_id": session_id,
                    "group_id": group_id or session_id,
                    "cutoff_seq": decision["cutoff_seq"],
                    "features": features,
                    "feature_schema": decision["feature_schema"],
                    "policy_version": decision["policy_version"],
                    "permitted": json.loads(decision["permitted_json"] or "[]"),
                    "selected": decision["selected"],
                    "rationale": json.loads(decision["rationale_json"] or "{}"),
                    "uncertainty": decision["uncertainty"],
                    "abstained": bool(decision["abstained"]),
                    "advisory": bool(decision["advisory"]),
                    "shadow": bool(decision["shadow"]),
                }
            )
        )
    lines.append(
        json.dumps(
            {
                "record": "outcome",
                "session_id": session_id,
                "group_id": group_id or session_id,
                "terminal_outcome": view["terminal_outcome"],
                "terminal_reason": view["terminal_reason"],
                "total_tokens": view["usage"]["total_tokens"],
                "unknown_ops": view["usage"]["unknown_ops"],
                "feedback": [
                    {"kind": f["kind"], "text": _redact_text(f["text"])} for f in feedback_rows
                ],
            }
        )
    )
    if include_raw:
        for event in conn.execute(
            "SELECT * FROM events WHERE session_id=? ORDER BY seq", (session_id,)
        ).fetchall():
            lines.append(
                json.dumps(
                    {
                        "record": "event",
                        "event_id": event["event_id"],
                        "event_type": event["event_type"],
                        "provenance": event["provenance"],
                        "observed_at": event["observed_at"],
                        "payload": json.loads(event["payload_json"] or "{}"),
                    }
                )
            )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(lines) + "\n"
    out_path.write_text(text, encoding="utf-8")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return {
        "path": str(out_path),
        "sha256": digest,
        "records": len(lines),
        "include_raw": include_raw,
    }
