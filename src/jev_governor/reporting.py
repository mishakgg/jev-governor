"""Session views: ledger, usage summary, terminal outcome, text/JSON rendering."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from . import accounting, evidence


def session_budget(conn: sqlite3.Connection, session_id: str) -> dict[str, Any]:
    row = conn.execute(
        "SELECT budget_json FROM sessions WHERE session_id=?", (session_id,)
    ).fetchone()
    if row is None:
        return {}
    try:
        value = json.loads(row["budget_json"] or "{}")
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def summarize_usage(
    conn: sqlite3.Connection, session_id: str
) -> tuple[accounting.AccountingTotals, dict[str, Any]]:
    totals = accounting.AccountingTotals()
    streams: dict[str, accounting.StreamState] = {}
    for row in conn.execute(
        "SELECT * FROM usage_ledger WHERE session_id=? ORDER BY row_id", (session_id,)
    ).fetchall():
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
    return totals, accounting.estimate_cost(totals)


def _load_checks(conn: sqlite3.Connection, session_id: str) -> list[evidence.CheckRecord]:
    out: list[evidence.CheckRecord] = []
    for row in conn.execute(
        "SELECT * FROM checks WHERE session_id=? ORDER BY event_seq", (session_id,)
    ).fetchall():
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


def _load_patches(conn: sqlite3.Connection, session_id: str) -> list[evidence.PatchRecord]:
    out: list[evidence.PatchRecord] = []
    for row in conn.execute(
        "SELECT * FROM events WHERE session_id=? AND event_type='patch.observed' ORDER BY seq",
        (session_id,),
    ).fetchall():
        payload = evidence.payload_json(row)
        paths = payload.get("paths")
        out.append(
            evidence.PatchRecord(
                patch_id=str(payload.get("patch_id", row["event_id"])),
                paths=[str(p) for p in paths] if isinstance(paths, list) else None,
                seq=int(row["seq"]),
            )
        )
    return out


def ledger_view(conn: sqlite3.Connection, session_id: str) -> dict[str, Any]:
    session = conn.execute("SELECT * FROM sessions WHERE session_id=?", (session_id,)).fetchone()
    if session is None:
        raise KeyError(f"unknown session: {session_id}")
    checks = _load_checks(conn, session_id)
    patches = _load_patches(conn, session_id)
    req_rows = conn.execute(
        """
        SELECT r.* FROM requirements r
        JOIN (SELECT req_id, MAX(version) AS v FROM requirements
              WHERE session_id=? GROUP BY req_id) cur
          ON r.req_id = cur.req_id AND r.version = cur.v
        WHERE r.session_id=?
        ORDER BY r.req_id
        """,
        (session_id, session_id),
    ).fetchall()
    requirements: list[dict[str, Any]] = []
    states: dict[str, str] = {}
    for row in req_rows:
        try:
            acceptance = json.loads(row["acceptance_json"] or "{}")
        except ValueError:
            acceptance = {}
        req = evidence.RequirementVersion(
            req_id=row["req_id"],
            version=int(row["version"]),
            origin=row["origin"],
            text_ref=row["text_ref"],
            acceptance=acceptance if isinstance(acceptance, dict) else {},
            updated_seq=int(row["updated_seq"]),
            blocked=(row["state"] == "blocked"),
        )
        state, refs, notes = evidence.requirement_state(req, checks, patches)
        states[req.req_id] = state
        requirements.append(
            {
                "req_id": req.req_id,
                "version": req.version,
                "origin": req.origin,
                "text_ref": req.text_ref,
                "acceptance": req.acceptance,
                "state": state,
                "evidence_refs": refs,
                "notes": notes,
            }
        )
    check_views = []
    for check in checks:
        status, reason = evidence.check_freshness(check, patches)
        check_views.append(
            {
                "check_id": check.check_id,
                "recipe_id": check.recipe_id,
                "req_ids": check.req_ids,
                "exit_status": check.exit_status,
                "disposition": check.disposition,
                "verdict": check.passed,
                "provenance": check.provenance,
                "authoritative": check.authoritative,
                "freshness": status,
                "freshness_reason": reason,
                "seq": check.seq,
            }
        )
    totals, cost = summarize_usage(conn, session_id)
    budget = session_budget(conn, session_id)
    used = totals.in_tokens + totals.out_tokens
    max_total = budget.get("max_total_tokens")
    budget_exhausted = isinstance(max_total, int | float) and max_total > 0 and used >= max_total
    ended = conn.execute(
        "SELECT payload_json FROM events WHERE session_id=? AND event_type='session.ended'"
        " ORDER BY seq DESC LIMIT 1",
        (session_id,),
    ).fetchone()
    session_ended = ended is not None
    cancelled = False
    if ended is not None:
        try:
            cancelled = json.loads(ended["payload_json"] or "{}").get("reason") == "cancelled"
        except ValueError:
            cancelled = False
    eval_row = conn.execute(
        "SELECT * FROM evaluations WHERE session_id=? ORDER BY created_at DESC LIMIT 1",
        (session_id,),
    ).fetchone()
    evaluation = None
    if eval_row is not None:
        evaluation = {"outcome": eval_row["outcome"], "eval_id": eval_row["eval_id"]}
    outcome, outcome_reason = evidence.derive_terminal_outcome(
        req_states=states,
        evaluation=evaluation,
        session_ended=session_ended,
        budget_exhausted=bool(budget_exhausted),
        cancelled=cancelled,
    )
    event_count = conn.execute(
        "SELECT COUNT(*) AS c FROM events WHERE session_id=?", (session_id,)
    ).fetchone()["c"]
    return {
        "session_id": session_id,
        "workspace": session["workspace"],
        "base_rev": session["base_rev"],
        "adapter": session["adapter"],
        "label": session["label"],
        "fixture": bool(session["fixture"]),
        "event_count": event_count,
        "requirements": requirements,
        "checks": check_views,
        "patches": [{"patch_id": p.patch_id, "paths": p.paths, "seq": p.seq} for p in patches],
        "usage": {
            "input_tokens": totals.in_tokens,
            "cached_input_tokens_subset": totals.cached_in_tokens,
            "output_tokens": totals.out_tokens,
            "reasoning_output_tokens_subset": totals.reasoning_out_tokens,
            "total_tokens": totals.total_tokens,
            "unknown_ops": totals.unknown_ops,
            "jev": {
                "calls": totals.jev_calls,
                "input_tokens": totals.jev_in_tokens,
                "output_tokens": totals.jev_out_tokens,
            },
            "governor": {
                "ops": totals.governor_ops,
                "elapsed_ms": totals.governor_elapsed_ms,
            },
            "resets": totals.resets,
            "by_model": totals.by_model,
        },
        "cost": cost,
        "budget": budget,
        "budget_exhausted": bool(budget_exhausted),
        "evaluation": evaluation,
        "terminal_outcome": outcome,
        "terminal_reason": outcome_reason,
        "session_ended": session_ended,
    }


def render_inspect(view: dict[str, Any]) -> str:
    lines = [
        f"session: {view['session_id']}  events: {view['event_count']}"
        + ("  [synthetic fixture]" if view["fixture"] else ""),
        f"workspace: {view['workspace'] or '(none)'}  base: {view['base_rev'] or '(none)'}",
        f"adapter: {view['adapter'] or '(none)'}",
        "",
        "requirements:",
    ]
    if not view["requirements"]:
        lines.append("  (none recorded)")
    for req in view["requirements"]:
        lines.append(
            f"  {req['req_id']} [{req['origin']}] state={req['state']} "
            f"acceptance={json.dumps(req['acceptance'])}"
        )
        for ref in req["evidence_refs"]:
            lines.append(f"    evidence: {ref}")
        for note in req["notes"]:
            lines.append(f"    note: {note}")
    lines.append("")
    lines.append("checks:")
    if not view["checks"]:
        lines.append("  (none recorded)")
    for check in view["checks"]:
        lines.append(
            f"  {check['check_id']} recipe={check['recipe_id']} verdict={check['verdict']} "
            f"prov={check['provenance']} freshness={check['freshness']}"
        )
    lines.append("")
    usage = view["usage"]
    lines.append(
        f"usage: in={usage['input_tokens']} "
        f"(cached-subset={usage['cached_input_tokens_subset']}) "
        f"out={usage['output_tokens']} "
        f"(reasoning-subset={usage['reasoning_output_tokens_subset']}) "
        f"total={usage['total_tokens']} unknown_ops={usage['unknown_ops']}"
    )
    lines.append(
        f"  jev: calls={usage['jev']['calls']} in={usage['jev']['input_tokens']} "
        f"out={usage['jev']['output_tokens']} "
        f"| governor: ops={usage['governor']['ops']} "
        f"elapsed_ms={usage['governor']['elapsed_ms']}"
    )
    if usage["resets"]:
        lines.append(f"  stream resets: {len(usage['resets'])} (see JSON for detail)")
    est = view["cost"]["estimates"]
    if est:
        for entry in est:
            lines.append(
                f"  estimate: {entry['amount']} {entry['currency']} "
                f"({entry['provider']}/{entry['model']}, price {view['cost']['price_version']})"
            )
    else:
        lines.append("  estimate: none priced (measured tokens only)")
    cov = view["cost"]["coverage"]
    lines.append(
        f"  unpriced: in={cov['unpriced_input_tokens']} out={cov['unpriced_output_tokens']}"
    )
    lines.append("")
    lines.append(f"terminal: {view['terminal_outcome']} ({view['terminal_reason']})")
    return "\n".join(lines) + "\n"


def render_report(
    view: dict[str, Any],
    decisions: list[dict[str, Any]],
    feedback_rows: list[dict[str, Any]],
) -> str:
    lines = [
        f"# Governor report: {view['session_id']}",
        "",
        render_inspect(view).rstrip(),
        "",
        "## recommendations",
    ]
    if not decisions:
        lines.append("(none issued)")
    for decision in decisions:
        selected = decision.get("selected") or "ABSTAIN"
        flags = []
        if decision.get("advisory"):
            flags.append("advisory")
        if decision.get("suppressed"):
            flags.append("suppressed-duplicate")
        if decision.get("shadow"):
            flags.append("shadow-only")
        lines.append(
            f"- {selected} [{' '.join(decision.get('rationale_codes', []))}] "
            f"uncertainty={decision.get('uncertainty')} [{','.join(flags)}]"
        )
        if decision.get("reason"):
            lines.append(f"  reason: {decision['reason']}")
    lines.append("")
    lines.append("## feedback")
    if not feedback_rows:
        lines.append("(none recorded)")
    for item in feedback_rows:
        lines.append(f"- {item['kind']}: {item['text'][:200]}")
    lines.append("")
    if view["terminal_outcome"] != "verified_success":
        lines.append(
            "Outcome is NOT verified success. Do not present this session as "
            "successful; see terminal reason above."
        )
    else:
        lines.append("Outcome verified against the recorded evaluation.")
    return "\n".join(lines) + "\n"
