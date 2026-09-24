"""Advisory issuance: features -> policy -> stored decision (advisory default)."""

from __future__ import annotations

import json
import sqlite3
import uuid
from typing import Any

from . import features as feat
from . import policy
from .schemas import utcnow_iso


def load_economical_target(conn: sqlite3.Connection, session_id: str) -> str | None:
    row = conn.execute(
        "SELECT budget_json FROM sessions WHERE session_id=?", (session_id,)
    ).fetchone()
    if row is None:
        return None
    try:
        budget = json.loads(row["budget_json"] or "{}")
    except ValueError:
        return None
    target = budget.get("economical_target") if isinstance(budget, dict) else None
    return str(target) if target else None


def issue_recommendation(
    conn: sqlite3.Connection,
    session_id: str,
    *,
    permitted: list[str] | None = None,
    jev_features: dict[str, Any] | None = None,
    economical_target: str | None = None,
    shadow: bool = False,
) -> dict[str, Any]:
    from . import reporting  # local import: layering

    view = reporting.ledger_view(conn, session_id)
    cutoff = int(view["event_count"])
    feature_vector = feat.build_features(conn, session_id, jev=jev_features)
    last = conn.execute(
        "SELECT selected, rationale_json FROM decisions WHERE session_id=? AND shadow=0"
        " ORDER BY cutoff_seq DESC LIMIT 1",
        (session_id,),
    ).fetchone()
    last_selected = last["selected"] if last else None
    last_codes: list[str] = []
    if last:
        try:
            last_codes = json.loads(last["rationale_json"] or "{}").get("codes", [])
        except ValueError:
            last_codes = []
    last_cutoff_row = conn.execute(
        "SELECT cutoff_seq FROM decisions WHERE session_id=? AND shadow=0"
        " ORDER BY cutoff_seq DESC LIMIT 1",
        (session_id,),
    ).fetchone()
    new_events = last_cutoff_row is None or int(last_cutoff_row["cutoff_seq"]) < cutoff
    target = economical_target or load_economical_target(conn, session_id)
    ctx = policy.PolicyContext(
        permitted=permitted or list(policy.RECIPES),
        budget=view["budget"],
        economical_available=target,
        last_selected=last_selected,
        last_codes=last_codes,
        new_events_since_last=new_events,
        advisory=True,
    )
    refs: list[str] = []
    for req in view["requirements"]:
        refs.extend(req["evidence_refs"][:4])
    decision = policy.decide(feature_vector, ctx, refs)
    decision_id = f"dec-{uuid.uuid4().hex[:12]}"
    conn.execute(
        """
        INSERT INTO decisions(decision_id, session_id, cutoff_seq, features_json,
                              feature_schema, policy_version, permitted_json, selected,
                              intended_config_json, rationale_json, uncertainty,
                              abstained, advisory, suppressed, shadow, created_at)
        VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            decision_id,
            session_id,
            cutoff,
            json.dumps(feature_vector),
            feat.FEATURE_SCHEMA,
            policy.POLICY_VERSION,
            json.dumps(ctx.permitted),
            decision.selected,
            json.dumps(decision.intended_config),
            json.dumps({"codes": decision.rationale_codes, "reason": decision.reason}),
            decision.uncertainty,
            1 if decision.abstained else 0,
            1 if decision.advisory else 0,
            1 if decision.suppressed else 0,
            1 if shadow else 0,
            utcnow_iso(),
        ),
    )
    conn.commit()
    return {
        "decision_id": decision_id,
        "session_id": session_id,
        "cutoff_seq": cutoff,
        "selected": decision.selected,
        "rationale_codes": decision.rationale_codes,
        "evidence_refs": decision.evidence_refs,
        "uncertainty": decision.uncertainty,
        "abstained": decision.abstained,
        "suppressed": decision.suppressed,
        "advisory": decision.advisory,
        "intended_config": decision.intended_config,
        "reason": decision.reason,
        "policy_version": policy.POLICY_VERSION,
    }
