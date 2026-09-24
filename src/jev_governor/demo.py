"""One-command clearly synthetic offline demo.

Shows: a repeated-failure loop, a productive expensive investigation, a stale
passing check after a patch change, a budget-exhausted session, and a live
trusted-check verification flow. No credentials, no network, no Jev, no Codex.
This demonstrates mechanics only -- never measured savings.
"""

from __future__ import annotations

import sqlite3
import subprocess
import tempfile
from collections.abc import Callable
from importlib import resources
from pathlib import Path
from typing import Any

from . import advisor, checks, ingest, reporting

FIXTURE_SESSIONS = (
    (
        "demo-loop",
        "demo-loop.jsonl",
        "ESCALATE_DIAGNOSIS",
        "Repeated-failure loop: the same pytest check failed after two "
        "distinct patches with no new diagnostics.",
    ),
    (
        "demo-productive",
        "demo-productive.jsonl",
        "CONTINUE",
        "Productive expensive investigation: high token spend, but a changed "
        "hypothesis and new diagnostics show movement -- not waste.",
    ),
    (
        "demo-stale",
        "demo-stale.jsonl",
        "VERIFY_NOW",
        "Stale passing check: pytest passed, then a relevant patch changed "
        "the evaluated state, invalidating the old evidence.",
    ),
    (
        "demo-budget",
        "demo-budget.jsonl",
        "PAUSE_REPLAN",
        "Budget exhaustion: observed cumulative usage passed the configured "
        "token budget, so the outcome is unresolved -- never success.",
    ),
)

EXPECTED_OUTCOMES = {
    "demo-loop": "incomplete",
    "demo-productive": "incomplete",
    "demo-stale": "incomplete",
    "demo-budget": "unresolved_budget",
}


def fixture_path(name: str) -> Path:
    return resources.files("jev_governor.fixtures").joinpath(name)  # type: ignore[return-value]


def run_demo(
    conn: sqlite3.Connection,
    *,
    out: Callable[[str], None] = print,
    include_verify_flow: bool = True,
) -> dict[str, Any]:
    out("Jev Governor offline demo -- all sessions below are clearly synthetic.")
    out("No credentials, network, Jev, or Codex involved.")
    out("")
    results: dict[str, Any] = {"sessions": {}, "verify_flow": None}
    for session_id, filename, expected, narrative in FIXTURE_SESSIONS:
        path = fixture_path(filename)
        summary = ingest.import_jsonl(conn, session_id, Path(str(path)), fixture=True)
        decision = advisor.issue_recommendation(conn, session_id)
        view = reporting.ledger_view(conn, session_id)
        match = decision["selected"] == expected
        outcome_ok = view["terminal_outcome"] == EXPECTED_OUTCOMES[session_id]
        results["sessions"][session_id] = {
            "expected": expected,
            "selected": decision["selected"],
            "match": match,
            "terminal_outcome": view["terminal_outcome"],
            "outcome_ok": outcome_ok,
            "imported": summary.accepted,
            "duplicates": summary.duplicates,
        }
        out(f"--- {session_id} ---")
        out(narrative)
        out(
            f"imported={summary.accepted} duplicates={summary.duplicates} "
            f"rejected={summary.rejected}"
        )
        out(
            f"recommendation: {decision['selected']} "
            f"[{' '.join(decision['rationale_codes'])}] "
            f"uncertainty={decision['uncertainty']} (expected {expected})"
        )
        out(f"reason: {decision['reason']}")
        out(f"terminal: {view['terminal_outcome']} ({view['terminal_reason']})")
        out("")
    if include_verify_flow:
        results["verify_flow"] = run_verify_flow(conn, out=out)
    out("Demo mechanics complete. Nothing here measures real-world savings.")
    return results


def run_verify_flow(
    conn: sqlite3.Connection, *, out: Callable[[str], None] = print
) -> dict[str, Any]:
    """Scripted trusted-check + evaluation flow in a temp mini-repo."""
    out("--- demo-verify ---")
    out(
        "Trusted verification flow: a real local check executes against a "
        "throwaway synthetic repo, then a labeled demo evaluation is recorded."
    )
    tmp = Path(tempfile.mkdtemp(prefix="jev-demo-verify-"))
    script = tmp / "check_demo.py"
    script.write_text("print('synthetic check target: ok')\n", encoding="utf-8")
    git_ok = False
    try:
        subprocess.run(
            ["git", "init", "-q", str(tmp)], capture_output=True, timeout=30, check=False
        )
        subprocess.run(
            ["git", "-C", str(tmp), "add", "."],
            capture_output=True,
            timeout=30,
            check=False,
        )
        proc = subprocess.run(
            [
                "git",
                "-C",
                str(tmp),
                "-c",
                "user.email=demo@local",
                "-c",
                "user.name=demo",
                "commit",
                "-qm",
                "demo",
            ],
            capture_output=True,
            timeout=30,
            check=False,
        )
        git_ok = proc.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        git_ok = False
    session_id = "demo-verify"
    envelopes = [
        {
            "schema_version": 1,
            "event_id": "verify-e1",
            "session_id": session_id,
            "event_type": "session.started",
            "source": "demo-fixture",
            "source_version": "1",
            "observed_at": "2026-01-09T13:00:00Z",
            "provenance": "synthetic",
            "payload": {
                "workspace": "demo://verify",
                "label": "trusted verification flow (synthetic)",
            },
        },
        {
            "schema_version": 1,
            "event_id": "verify-e2",
            "session_id": session_id,
            "event_type": "requirement.proposed",
            "source": "demo-fixture",
            "source_version": "1",
            "observed_at": "2026-01-09T13:01:00Z",
            "provenance": "synthetic",
            "payload": {
                "req_id": "R1",
                "origin": "user",
                "text_ref": "synthetic: demo script exits zero",
                "acceptance": {"check_recipe_ids": ["python-file"], "required": "all"},
            },
        },
        {
            "schema_version": 1,
            "event_id": "verify-e3",
            "session_id": session_id,
            "event_type": "requirement.accepted",
            "source": "demo-fixture",
            "source_version": "1",
            "observed_at": "2026-01-09T13:02:00Z",
            "provenance": "synthetic",
            "payload": {"req_id": "R1"},
        },
    ]
    ingest.import_envelopes(conn, session_id, envelopes, source_path="demo:verify", fixture=True)
    check = checks.run_check(
        conn,
        session_id,
        recipe_id="python-file",
        workspace=tmp,
        req_ids=["R1"],
        paths=["check_demo.py"],
        env_fp="demo",
    )
    out(
        f"trusted check: {check['check_id']} exit={check['exit_status']} "
        f"disposition={check['disposition']}"
    )
    # Evaluator ingress: labeled demo attestor, explicitly not independent.
    from .ingest import apply_projection
    from .storage import insert_event  # local import: layering

    existing = conn.execute(
        "SELECT eval_id FROM evaluations WHERE session_id=? LIMIT 1", (session_id,)
    ).fetchone()
    if existing is None:
        seq = insert_event(
            conn,
            event_id="verify-eval-1",
            session_id=session_id,
            event_type="evaluation.completed",
            provenance="evaluator",
            source="demo-attestor",
            source_version="1",
            observed_at="2026-01-09T13:05:00Z",
            payload={
                "eval_id": "demo-eval-1",
                "outcome": "verified_success",
                "evaluator": "demo-attestor",
                "evaluator_version": "1",
                "independent": False,
                "coverage": {"R1": "verified"},
            },
        )
        assert seq is not None
        row = conn.execute("SELECT * FROM events WHERE event_id='verify-eval-1'").fetchone()
        assert row is not None
        apply_projection(conn, session_id, row)
        conn.commit()
    view = reporting.ledger_view(conn, session_id)
    out(f"terminal: {view['terminal_outcome']} ({view['terminal_reason']})")
    out("")
    return {
        "session_id": session_id,
        "check": check,
        "terminal_outcome": view["terminal_outcome"],
        "git_available": git_ok,
        "tmp": str(tmp),
    }
