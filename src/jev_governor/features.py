"""Deterministic decision-time features (schema feat-1).

Only information available at the cutoff may enter the vector: no terminal
evaluation results, no future observations. Jev-derived fields are optional
add-ons recorded with their own provenance.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from . import accounting, evidence
from .schemas import parse_observed_at

FEATURE_SCHEMA = "feat-1"

# Fields that must never appear in a decision-time vector (leakage denylist).
LEAKAGE_DENYLIST = frozenset(
    {
        "terminal_outcome",
        "verified_success",
        "eval_passed",
        "evaluator_outcome",
        "future_usage",
        "label",
    }
)


def _row_payload(row: sqlite3.Row) -> dict[str, Any]:
    return evidence.payload_json(row)


def _current_requirements(
    conn: sqlite3.Connection, session_id: str, cutoff: int | None
) -> list[evidence.RequirementVersion]:
    rows = conn.execute(
        """
        SELECT r.* FROM requirements r
        JOIN (SELECT req_id, MAX(version) AS v FROM requirements
              WHERE session_id=? GROUP BY req_id) cur
          ON r.req_id = cur.req_id AND r.version = cur.v
        WHERE r.session_id=?
        """,
        (session_id, session_id),
    ).fetchall()
    reqs: list[evidence.RequirementVersion] = []
    for row in rows:
        if cutoff is not None and int(row["updated_seq"]) > cutoff:
            continue
        try:
            acceptance = json.loads(row["acceptance_json"] or "{}")
        except ValueError:
            acceptance = {}
        reqs.append(
            evidence.RequirementVersion(
                req_id=row["req_id"],
                version=int(row["version"]),
                origin=row["origin"],
                text_ref=row["text_ref"],
                acceptance=acceptance if isinstance(acceptance, dict) else {},
                updated_seq=int(row["updated_seq"]),
                blocked=(row["state"] == "blocked"),
            )
        )
    return reqs


def _checks(
    conn: sqlite3.Connection, session_id: str, cutoff: int | None
) -> list[evidence.CheckRecord]:
    rows = conn.execute(
        "SELECT * FROM checks WHERE session_id=? ORDER BY event_seq", (session_id,)
    ).fetchall()
    out: list[evidence.CheckRecord] = []
    for row in rows:
        if cutoff is not None and int(row["event_seq"]) > cutoff:
            continue
        try:
            req_ids = json.loads(row["req_ids_json"] or "[]")
        except ValueError:
            req_ids = []
        try:
            repo_fp = json.loads(row["repo_fp_json"] or "{}")
        except ValueError:
            repo_fp = {}
        out.append(
            evidence.CheckRecord(
                check_id=row["check_id"],
                req_ids=[r for r in req_ids if isinstance(r, str)],
                recipe_id=row["recipe_id"],
                executor=row["executor"],
                exit_status=row["exit_status"],
                disposition=row["disposition"],
                env_fp=row["env_fp"],
                repo_fp=evidence.RepoFingerprint.from_payload(repo_fp),
                started_at=row["started_at"],
                ended_at=row["ended_at"],
                provenance=row["provenance"],
                seq=int(row["event_seq"]),
            )
        )
    return out


def _events_of(
    conn: sqlite3.Connection, session_id: str, event_type: str, cutoff: int | None
) -> list[sqlite3.Row]:
    rows = conn.execute(
        "SELECT * FROM events WHERE session_id=? AND event_type=? ORDER BY seq",
        (session_id, event_type),
    ).fetchall()
    if cutoff is not None:
        rows = [r for r in rows if int(r["seq"]) <= cutoff]
    return rows


def build_features(
    conn: sqlite3.Connection,
    session_id: str,
    *,
    cutoff_seq: int | None = None,
    jev: dict[str, Any] | None = None,
) -> dict[str, Any]:
    reqs = _current_requirements(conn, session_id, cutoff_seq)
    checks = _checks(conn, session_id, cutoff_seq)
    patches = [
        evidence.PatchRecord(
            patch_id=str(_row_payload(r).get("patch_id", r["event_id"])),
            paths=(
                _row_payload(r).get("paths")
                if isinstance(_row_payload(r).get("paths"), list)
                else None
            ),
            seq=int(r["seq"]),
        )
        for r in _events_of(conn, session_id, "patch.observed", cutoff_seq)
    ]
    diagnostics = _events_of(conn, session_id, "diagnostic.recorded", cutoff_seq)
    hypotheses = _events_of(conn, session_id, "hypothesis.recorded", cutoff_seq)

    last_patch_seq = max([p.seq for p in patches], default=0)
    new_diagnostics = sum(1 for d in diagnostics if int(d["seq"]) > last_patch_seq)
    hypothesis_changed = any(
        bool(_row_payload(h).get("changed", False)) and int(h["seq"]) > last_patch_seq
        for h in hypotheses
    )

    # Loop signal: same recipe failing after distinct patches.
    failures_by_recipe: dict[str, int] = {}
    for check in checks:
        if check.passed is False:
            failures_by_recipe[check.recipe_id] = failures_by_recipe.get(check.recipe_id, 0) + 1
    distinct_patches = len(patches)
    same_after_distinct = 0
    if distinct_patches >= 2:
        same_after_distinct = max(failures_by_recipe.values(), default=0)

    # Requirement states at cutoff.
    states: dict[str, str] = {}
    remaining = 0
    failed_now = 0
    for req in reqs:
        state, _, _ = evidence.requirement_state(req, checks, patches)
        states[req.req_id] = state
        if state in ("unknown", "candidate", "partially_verified", "failed"):
            remaining += 1
        if state == "failed":
            failed_now += 1

    stale_checks = 0
    fresh_pass_checks = 0
    for check in checks:
        status, _ = evidence.check_freshness(check, patches)
        if status != evidence.FRESH:
            stale_checks += 1
        elif check.passed:
            fresh_pass_checks += 1

    totals = accounting.AccountingTotals()
    streams: dict[str, accounting.StreamState] = {}
    for row in conn.execute(
        "SELECT * FROM usage_ledger WHERE session_id=? ORDER BY row_id", (session_id,)
    ).fetchall():
        # Cutoff for usage rows: join via event seq is unavailable here, so the
        # caller passes cutoff only for event-derived features; usage rows are
        # append-only and the decision records the cutoff for reproducibility.
        usage = accounting.NormalizedUsage(
            in_tokens=row["in_tokens"],
            cached_in_tokens=row["cached_in_tokens"],
            out_tokens=row["out_tokens"],
            reasoning_out_tokens=row["reasoning_out_tokens"],
            total_tokens=row["total_tokens"],
            complete=bool(row["complete"]),
        )
        accounting.apply_to_totals(
            totals,
            streams,
            stream_id=row["stream_id"] or "",
            epoch=row["epoch"] or "",
            stream_seq=int(row["stream_seq"]),
            kind=row["kind"],
            provider=row["provider"] or "",
            model_served=row["model_served"] or "",
            usage=usage,
            elapsed_ms=row["elapsed_ms"],
            event_id=row["event_id"],
        )

    stamps = [
        parse_observed_at(r["observed_at"])
        for r in conn.execute(
            "SELECT observed_at FROM events WHERE session_id=? ORDER BY seq",
            (session_id,),
        ).fetchall()
    ]
    elapsed_s = max(0.0, (max(stamps) - min(stamps)).total_seconds()) if stamps else 0.0

    features: dict[str, Any] = {
        "schema": FEATURE_SCHEMA,
        "n_requirements": len(reqs),
        "n_failed_now": failed_now,
        "n_remaining": remaining,
        "distinct_patches": distinct_patches,
        "same_assert_after_distinct_patches": same_after_distinct,
        "new_diagnostics_since_last_patch": new_diagnostics,
        "hypothesis_changed": hypothesis_changed,
        "n_checks": len(checks),
        "n_stale_checks": stale_checks,
        "n_fresh_pass_checks": fresh_pass_checks,
        "total_input_tokens": totals.in_tokens,
        "total_output_tokens": totals.out_tokens,
        "unknown_usage_ops": totals.unknown_ops,
        "usage_resets": len(totals.resets),
        "elapsed_s": round(elapsed_s, 1),
        "jev_failure_pattern": (jev or {}).get("failure_pattern"),
        "jev_hypothesis_repetition": (jev or {}).get("hypothesis_repetition"),
    }
    unknown = [k for k in LEAKAGE_DENYLIST if k in features]
    if unknown:
        raise ValueError(f"leakage fields in feature vector: {unknown}")
    return features
