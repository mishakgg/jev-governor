"""SQLite persistence: append-only logical events plus derived projections.

Derived tables (requirements, checks, usage, decisions, ...) are deterministic
projections of the events table. :func:`rebuild_session` re-derives them so
reports can be rebuilt from stored events; tests assert incremental ingestion
matches a full rebuild.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import Settings, ensure_data_dir
from .schemas import SCHEMA_VERSION, utcnow_iso

STORE_VERSION = 1


def db_path(settings: Settings) -> Path:
    ensure_data_dir(settings)
    return settings.data_dir / "governor.sqlite3"


def connect(settings: Settings) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path(settings)))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    init_schema(conn)
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            workspace TEXT NOT NULL DEFAULT '',
            base_rev TEXT NOT NULL DEFAULT '',
            adapter TEXT NOT NULL DEFAULT '',
            adapter_version TEXT NOT NULL DEFAULT '',
            label TEXT NOT NULL DEFAULT '',
            fixture INTEGER NOT NULL DEFAULT 0,
            budget_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS events (
            event_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            provenance TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT '',
            source_version TEXT NOT NULL DEFAULT '',
            observed_at TEXT NOT NULL,
            payload_json TEXT NOT NULL DEFAULT '{}',
            seq INTEGER NOT NULL,
            UNIQUE(session_id, seq)
        );
        CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id, seq);
        CREATE TABLE IF NOT EXISTS requirements (
            session_id TEXT NOT NULL,
            req_id TEXT NOT NULL,
            version INTEGER NOT NULL,
            origin TEXT NOT NULL,
            text_ref TEXT NOT NULL DEFAULT '',
            acceptance_json TEXT NOT NULL DEFAULT '{}',
            state TEXT NOT NULL DEFAULT 'unknown',
            updated_seq INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (session_id, req_id, version)
        );
        CREATE TABLE IF NOT EXISTS checks (
            session_id TEXT NOT NULL,
            check_id TEXT NOT NULL,
            req_ids_json TEXT NOT NULL DEFAULT '[]',
            recipe_id TEXT NOT NULL DEFAULT '',
            executor TEXT NOT NULL DEFAULT '',
            exit_status INTEGER,
            disposition TEXT NOT NULL DEFAULT 'completed',
            env_fp TEXT NOT NULL DEFAULT '',
            repo_fp_json TEXT NOT NULL DEFAULT '{}',
            started_at TEXT NOT NULL DEFAULT '',
            ended_at TEXT NOT NULL DEFAULT '',
            provenance TEXT NOT NULL DEFAULT 'imported',
            event_seq INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (session_id, check_id)
        );
        CREATE INDEX IF NOT EXISTS idx_checks_session ON checks(session_id, event_seq);
        CREATE TABLE IF NOT EXISTS usage_ledger (
            row_id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            event_id TEXT NOT NULL UNIQUE,
            stream_id TEXT NOT NULL DEFAULT '',
            epoch TEXT NOT NULL DEFAULT '',
            stream_seq INTEGER NOT NULL DEFAULT 0,
            kind TEXT NOT NULL DEFAULT 'unknown',
            provider TEXT NOT NULL DEFAULT '',
            model_requested TEXT NOT NULL DEFAULT '',
            model_served TEXT NOT NULL DEFAULT '',
            effort TEXT NOT NULL DEFAULT '',
            in_tokens INTEGER,
            cached_in_tokens INTEGER,
            out_tokens INTEGER,
            reasoning_out_tokens INTEGER,
            total_tokens INTEGER,
            complete INTEGER NOT NULL DEFAULT 1,
            elapsed_ms INTEGER,
            raw_json TEXT NOT NULL DEFAULT '{}',
            note TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_usage_session ON usage_ledger(session_id, row_id);
        CREATE TABLE IF NOT EXISTS decisions (
            decision_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            cutoff_seq INTEGER NOT NULL,
            features_json TEXT NOT NULL DEFAULT '{}',
            feature_schema TEXT NOT NULL DEFAULT '',
            policy_version TEXT NOT NULL DEFAULT '',
            permitted_json TEXT NOT NULL DEFAULT '[]',
            selected TEXT,
            intended_config_json TEXT NOT NULL DEFAULT '{}',
            rationale_json TEXT NOT NULL DEFAULT '{}',
            uncertainty REAL,
            abstained INTEGER NOT NULL DEFAULT 0,
            advisory INTEGER NOT NULL DEFAULT 1,
            suppressed INTEGER NOT NULL DEFAULT 0,
            shadow INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_decisions_session ON decisions(session_id, cutoff_seq);
        CREATE TABLE IF NOT EXISTS feedback (
            feedback_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            kind TEXT NOT NULL,
            text TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS evaluations (
            eval_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            outcome TEXT NOT NULL,
            evaluator TEXT NOT NULL DEFAULT '',
            evaluator_version TEXT NOT NULL DEFAULT '',
            repo_fp_json TEXT NOT NULL DEFAULT '{}',
            coverage_json TEXT NOT NULL DEFAULT '{}',
            independent INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS import_runs (
            run_id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            source_path TEXT NOT NULL DEFAULT '',
            accepted INTEGER NOT NULL DEFAULT 0,
            duplicates INTEGER NOT NULL DEFAULT 0,
            rejected INTEGER NOT NULL DEFAULT 0,
            diagnostics_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL
        );
        """
    )
    row = conn.execute("SELECT value FROM meta WHERE key='store_version'").fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO meta(key, value) VALUES('store_version', ?)", (str(STORE_VERSION),)
        )
    elif row["value"] != str(STORE_VERSION):
        raise RuntimeError(f"unsupported store version: {row['value']}")
    row = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO meta(key, value) VALUES('schema_version', ?)", (str(SCHEMA_VERSION),)
        )
    conn.commit()


@dataclass
class SessionRow:
    session_id: str
    workspace: str = ""
    base_rev: str = ""
    adapter: str = ""
    adapter_version: str = ""
    label: str = ""
    fixture: bool = False
    budget: dict[str, Any] | None = None


def ensure_session(conn: sqlite3.Connection, session: SessionRow) -> None:
    conn.execute(
        """
        INSERT INTO sessions(session_id, workspace, base_rev, adapter, adapter_version,
                             label, fixture, budget_json, created_at)
        VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(session_id) DO NOTHING
        """,
        (
            session.session_id,
            session.workspace,
            session.base_rev,
            session.adapter,
            session.adapter_version,
            session.label,
            1 if session.fixture else 0,
            json.dumps(session.budget or {}),
            utcnow_iso(),
        ),
    )


def get_session(conn: sqlite3.Connection, session_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM sessions WHERE session_id=?", (session_id,)).fetchone()


def list_sessions(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return list(conn.execute("SELECT * FROM sessions ORDER BY created_at, session_id"))


def next_seq(conn: sqlite3.Connection, session_id: str) -> int:
    row = conn.execute(
        "SELECT COALESCE(MAX(seq), 0) AS m FROM events WHERE session_id=?", (session_id,)
    ).fetchone()
    return int(row["m"]) + 1


def insert_event(
    conn: sqlite3.Connection,
    *,
    event_id: str,
    session_id: str,
    event_type: str,
    provenance: str,
    source: str,
    source_version: str,
    observed_at: str,
    payload: dict[str, Any],
) -> int | None:
    """Insert an event; return its seq, or None if it is a duplicate."""
    seq = next_seq(conn, session_id)
    try:
        conn.execute(
            """
            INSERT INTO events(event_id, session_id, event_type, provenance, source,
                               source_version, observed_at, payload_json, seq)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                session_id,
                event_type,
                provenance,
                source,
                source_version,
                observed_at,
                json.dumps(payload),
                seq,
            ),
        )
    except sqlite3.IntegrityError:
        return None
    return seq


def session_events(conn: sqlite3.Connection, session_id: str) -> list[sqlite3.Row]:
    return list(conn.execute("SELECT * FROM events WHERE session_id=? ORDER BY seq", (session_id,)))


def delete_session(conn: sqlite3.Connection, session_id: str) -> None:
    for table, col in (
        ("evaluations", "session_id"),
        ("feedback", "session_id"),
        ("decisions", "session_id"),
        ("usage_ledger", "session_id"),
        ("checks", "session_id"),
        ("requirements", "session_id"),
        ("events", "session_id"),
        ("import_runs", "session_id"),
        ("sessions", "session_id"),
    ):
        conn.execute(f"DELETE FROM {table} WHERE {col}=?", (session_id,))


def prune_sessions_older_than(conn: sqlite3.Connection, cutoff_iso: str) -> list[str]:
    rows = conn.execute(
        "SELECT session_id FROM sessions WHERE created_at < ?", (cutoff_iso,)
    ).fetchall()
    removed = [str(r["session_id"]) for r in rows]
    for session_id in removed:
        delete_session(conn, session_id)
    return removed
