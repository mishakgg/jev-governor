"""Thin CLI: doctor/demo/import/inspect/recommend/report/feedback/export/delete + research."""

from __future__ import annotations

import argparse
import json
import platform
import sqlite3
import subprocess
import sys
import tempfile
import uuid
from datetime import UTC
from pathlib import Path
from typing import Any

from . import (
    advisor,
    checks,
    codex_adapter,
    config,
    experiments,
    ingest,
    jev,
    learning,
    reporting,
    storage,
)
from . import (
    demo as demo_mod,
)
from . import (
    export as export_mod,
)
from .schemas import SCHEMA_VERSION, utcnow_iso

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2


def _settings(args: argparse.Namespace) -> config.Settings:
    return config.load_settings(getattr(args, "data_dir", None))


def _conn(settings: config.Settings) -> sqlite3.Connection:
    return storage.connect(settings)


def _print(payload: Any, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    elif isinstance(payload, str):
        print(payload, end="" if payload.endswith("\n") else "\n")
    else:
        print(json.dumps(payload, indent=2, sort_keys=True))


def _fail(message: str, as_json: bool = False) -> int:
    if as_json:
        print(json.dumps({"ok": False, "error": message}))
    else:
        print(f"error: {message}", file=sys.stderr)
    return EXIT_ERROR


# ------------------------------------------------------------------ commands


def cmd_version(args: argparse.Namespace) -> int:
    from . import __schema_version__, __version__

    payload = {
        "package": "jev-governor",
        "version": __version__,
        "schema_version": __schema_version__,
        "python": platform.python_version(),
        "platform": f"{platform.system()}-{platform.machine()}",
    }
    _print(payload, True)
    return EXIT_OK


def cmd_doctor(args: argparse.Namespace) -> int:
    from . import __version__

    settings = _settings(args)
    probe = codex_adapter.probe()
    payload = {
        "package_version": __version__,
        "schema_version": SCHEMA_VERSION,
        "python": platform.python_version(),
        "platform": f"{platform.system()}-{platform.machine()}",
        "data_dir": str(settings.data_dir),
        "mode": settings.mode,
        "jev": {
            "enabled": settings.jev_enabled,
            "model_configured": settings.jev_model,
            "api_key_present": settings.api_key_present,
            "live_max_attempts": settings.live_max_attempts,
            "timeout_s": settings.jev_timeout_seconds,
            "note": "key presence is not authorization; live calls need "
            "--live plus explicit enablement",
        },
        "codex": probe,
        "check_recipes": sorted(checks.RECIPES),
        "network_policy": "offline default; no provider traffic except explicit "
        "live commands (jev-smoke --live, recommend --with-jev --live, "
        "codex-qualify --run)",
    }
    if args.json:
        _print(payload, True)
        return EXIT_OK
    lines = [
        f"jev-governor {__version__}  schema={SCHEMA_VERSION}  "
        f"python={platform.python_version()}  platform={payload['platform']}",
        f"data dir: {settings.data_dir}  mode: {settings.mode}",
        f"jev: enabled={settings.jev_enabled} model={settings.jev_model} "
        f"key_present={settings.api_key_present} "
        f"max_attempts={settings.live_max_attempts}",
        f"codex: present={probe['present']} version={probe['version'] or '(none)'} "
        f"doctor={probe['doctor_status']} auth={probe['auth']}",
    ]
    for cap in probe["capabilities"]:
        lines.append(f"  [{cap['status']}] {cap['name']}: {cap['detail']}")
    lines.append(f"check recipes: {', '.join(sorted(checks.RECIPES))}")
    lines.append(payload["network_policy"])
    print("\n".join(lines))
    return EXIT_OK


def cmd_demo(args: argparse.Namespace) -> int:
    settings = _settings(args)
    conn = _conn(settings)
    if args.json:
        captured: list[str] = []
        result = demo_mod.run_demo(
            conn, out=captured.append, include_verify_flow=not args.no_verify_flow
        )
        result["log"] = captured
        _print(result, True)
    else:
        demo_mod.run_demo(conn, include_verify_flow=not args.no_verify_flow)
    conn.close()
    return EXIT_OK


def cmd_import(args: argparse.Namespace) -> int:
    settings = _settings(args)
    conn = _conn(settings)
    try:
        if args.adapter == "codex-rollout":
            conv = codex_adapter.convert_rollout(Path(args.file), args.session)
            summary = ingest.import_envelopes(
                conn,
                args.session,
                conv.envelopes,
                source_path=f"codex-rollout:{args.file}",
            )
            summary.diagnostics.extend(conv.diagnostics)
            summary.rejected += conv.rejected
        else:
            summary = ingest.import_jsonl(conn, args.session, Path(args.file))
    except OSError as exc:
        conn.close()
        return _fail(str(exc), args.json)
    payload = {
        "ok": True,
        "session": summary.session_id,
        "accepted": summary.accepted,
        "duplicates": summary.duplicates,
        "rejected": summary.rejected,
        "diagnostics": summary.diagnostics[:20],
    }
    _print(payload, args.json)
    conn.close()
    return EXIT_OK


def cmd_inspect(args: argparse.Namespace) -> int:
    settings = _settings(args)
    conn = _conn(settings)
    try:
        view = reporting.ledger_view(conn, args.session)
    except KeyError:
        conn.close()
        return _fail(f"unknown session: {args.session}", args.json)
    _print(view if args.json else reporting.render_inspect(view), args.json)
    conn.close()
    return EXIT_OK


def _maybe_jev_features(
    args: argparse.Namespace,
    settings: config.Settings,
    conn: sqlite3.Connection,
    feature_preview: dict[str, Any],
) -> tuple[dict[str, Any] | None, list[str]]:
    """Gated Jev call for recommend. Returns (features|None, notices)."""
    notices: list[str] = []
    if not getattr(args, "with_jev", False):
        return None, notices
    if not settings.jev_enabled:
        return None, ["jev-disabled: set JEV_GOVERNOR_JEV_ENABLED=true to authorize"]
    key = config.read_api_key()
    if not key:
        return None, ["jev-missing-key: TYPESAFE_API_KEY not present; using baseline"]
    if not getattr(args, "live", False) or int(getattr(args, "max_attempts", 0) or 0) < 1:
        return None, ["jev-not-authorized: --live --max-attempts N required; using baseline"]
    state = jev.build_state({**feature_preview, "fixture": False})
    result = jev.evaluate(
        state=state,
        model=settings.jev_model,
        api_key=key,
        transport=jev.UrllibTransport(),
        max_attempts=min(
            int(args.max_attempts), settings.live_max_attempts or int(args.max_attempts)
        ),
        deadline_s=60.0,
        per_attempt_timeout_s=settings.jev_timeout_seconds,
    )
    # Record Jev spend + governor overhead even on failure (attempts known).
    usage_payload = {
        "kind": "delta" if result.usage else "unknown",
        "provider": "typesafe",
        "model_requested": settings.jev_model,
        "model_served": result.model_served,
        "usage": {
            "input_tokens": result.usage.get("input_tokens", 0),
            "output_tokens": result.usage.get("output_tokens", 0),
        },
        "attempts": result.attempts,
        "latency_ms": result.latency_ms,
        "ok": result.ok,
        "error_kind": result.error_kind,
    }
    event_id = f"evt-jev-{uuid.uuid4().hex[:12]}"
    seq = storage.insert_event(
        conn,
        event_id=event_id,
        session_id=args.session,
        event_type="usage.reported",
        provenance="observed",
        source="jev-client",
        source_version="1",
        observed_at=utcnow_iso(),
        payload=usage_payload,
    )
    if seq is not None:
        row = conn.execute("SELECT * FROM events WHERE event_id=?", (event_id,)).fetchone()
        if row is not None:
            ingest.apply_projection(conn, args.session, row)
            conn.commit()
    if not result.ok:
        notices.append(f"jev-fallback:{result.error_kind}:{result.error[:120]}")
        return None, notices
    notices.append(
        f"jev-ok:model={result.model_served} attempts={result.attempts} "
        f"latency_ms={result.latency_ms}"
    )
    return result.features, notices


def cmd_recommend(args: argparse.Namespace) -> int:
    settings = _settings(args)
    conn = _conn(settings)
    try:
        reporting.ledger_view(conn, args.session)
    except KeyError:
        conn.close()
        return _fail(f"unknown session: {args.session}", args.json)
    from . import features as feat

    feature_preview = feat.build_features(conn, args.session)
    jev_features, notices = _maybe_jev_features(args, settings, conn, feature_preview)
    permitted = args.permitted.split(",") if getattr(args, "permitted", None) else None
    decision = advisor.issue_recommendation(
        conn,
        args.session,
        permitted=permitted,
        jev_features=jev_features,
        economical_target=getattr(args, "economical_target", None),
    )
    decision["notices"] = notices
    decision["mode"] = "advisory; no command executed; no model setting changed"
    conn.close()
    if args.json:
        _print(decision, True)
        return EXIT_OK
    selected = decision["selected"] or "ABSTAIN"
    lines = [
        f"recommendation for {args.session}: {selected}",
        f"reason: {decision['reason']}",
        f"codes: {' '.join(decision['rationale_codes'])}",
        f"uncertainty: {decision['uncertainty']}  advisory: {decision['advisory']}  "
        f"suppressed_duplicate: {decision['suppressed']}",
    ]
    for note in notices:
        lines.append(f"note: {note}")
    lines.append(decision["mode"])
    print("\n".join(lines))
    return EXIT_OK


def cmd_report(args: argparse.Namespace) -> int:
    settings = _settings(args)
    conn = _conn(settings)
    try:
        view = reporting.ledger_view(conn, args.session)
    except KeyError:
        conn.close()
        return _fail(f"unknown session: {args.session}", args.json)
    decisions = [
        {
            "selected": r["selected"],
            "rationale_codes": json.loads(r["rationale_json"] or "{}").get("codes", []),
            "reason": json.loads(r["rationale_json"] or "{}").get("reason", ""),
            "uncertainty": r["uncertainty"],
            "advisory": bool(r["advisory"]),
            "suppressed": bool(r["suppressed"]),
            "shadow": bool(r["shadow"]),
        }
        for r in conn.execute(
            "SELECT * FROM decisions WHERE session_id=? ORDER BY cutoff_seq", (args.session,)
        ).fetchall()
    ]
    feedback_rows = [
        {"kind": r["kind"], "text": r["text"]}
        for r in conn.execute(
            "SELECT kind, text FROM feedback WHERE session_id=?", (args.session,)
        ).fetchall()
    ]
    conn.close()
    if args.json:
        _print({"session": view, "decisions": decisions, "feedback": feedback_rows}, True)
    else:
        _print(reporting.render_report(view, decisions, feedback_rows), False)
    return EXIT_OK


def cmd_feedback(args: argparse.Namespace) -> int:
    settings = _settings(args)
    conn = _conn(settings)
    if storage.get_session(conn, args.session) is None:
        conn.close()
        return _fail(f"unknown session: {args.session}", args.json)
    feedback_id = f"fb-{uuid.uuid4().hex[:12]}"
    event_id = f"evt-{feedback_id}"
    seq = storage.insert_event(
        conn,
        event_id=event_id,
        session_id=args.session,
        event_type="feedback.recorded",
        provenance="human",
        source="cli-feedback",
        source_version="1",
        observed_at=utcnow_iso(),
        payload={"feedback_id": feedback_id, "kind": args.kind, "text": args.text[:2000]},
    )
    assert seq is not None
    row = conn.execute("SELECT * FROM events WHERE event_id=?", (event_id,)).fetchone()
    assert row is not None
    ingest.apply_projection(conn, args.session, row)
    conn.commit()
    conn.close()
    _print({"ok": True, "feedback_id": feedback_id}, args.json)
    return EXIT_OK


def cmd_export(args: argparse.Namespace) -> int:
    settings = _settings(args)
    conn = _conn(settings)
    try:
        result = export_mod.export_session(
            conn,
            args.session,
            Path(args.out),
            include_raw=bool(args.include_raw),
            group_id=args.group_id,
        )
    except KeyError:
        conn.close()
        return _fail(f"unknown session: {args.session}", args.json)
    conn.close()
    _print(result, args.json)
    return EXIT_OK


def cmd_delete(args: argparse.Namespace) -> int:
    settings = _settings(args)
    if not args.yes:
        return _fail("refusing without --yes (destructive operation)", args.json)
    conn = _conn(settings)
    if args.all:
        sessions = [r["session_id"] for r in storage.list_sessions(conn)]
        for session_id in sessions:
            storage.delete_session(conn, session_id)
        conn.commit()
        conn.close()
        _print({"ok": True, "deleted": sessions}, args.json)
        return EXIT_OK
    if not args.session:
        conn.close()
        return _fail("need --session or --all", args.json)
    storage.delete_session(conn, args.session)
    conn.commit()
    conn.close()
    _print({"ok": True, "deleted": [args.session]}, args.json)
    return EXIT_OK


def cmd_prune(args: argparse.Namespace) -> int:
    settings = _settings(args)
    if not args.yes:
        return _fail("refusing without --yes (destructive operation)", args.json)
    from datetime import datetime, timedelta

    cutoff = (datetime.now(UTC) - timedelta(days=args.older_than_days)).isoformat()
    conn = _conn(settings)
    removed = storage.prune_sessions_older_than(conn, cutoff)
    conn.commit()
    conn.close()
    _print({"ok": True, "pruned": removed}, args.json)
    return EXIT_OK


def cmd_sessions(args: argparse.Namespace) -> int:
    settings = _settings(args)
    conn = _conn(settings)
    rows = [
        {
            "session_id": r["session_id"],
            "label": r["label"],
            "fixture": bool(r["fixture"]),
            "adapter": r["adapter"],
            "created_at": r["created_at"],
        }
        for r in storage.list_sessions(conn)
    ]
    conn.close()
    _print(rows, args.json)
    return EXIT_OK


def cmd_run_check(args: argparse.Namespace) -> int:
    settings = _settings(args)
    conn = _conn(settings)
    try:
        result = checks.run_check(
            conn,
            args.session,
            recipe_id=args.recipe,
            workspace=Path(args.workspace),
            req_ids=args.req,
            paths=args.path,
            k_expr=args.k or "",
            timeout_s=args.timeout,
        )
    except (ValueError, OSError) as exc:
        conn.close()
        return _fail(str(exc), args.json)
    conn.close()
    _print(result, args.json)
    return EXIT_OK


def cmd_record_evaluation(args: argparse.Namespace) -> int:
    settings = _settings(args)
    conn = _conn(settings)
    if storage.get_session(conn, args.session) is None:
        conn.close()
        return _fail(f"unknown session: {args.session}", args.json)
    eval_id = f"eval-{uuid.uuid4().hex[:12]}"
    event_id = f"evt-{eval_id}"
    seq = storage.insert_event(
        conn,
        event_id=event_id,
        session_id=args.session,
        event_type="evaluation.completed",
        provenance="evaluator",
        source="cli-evaluation",
        source_version="1",
        observed_at=utcnow_iso(),
        payload={
            "eval_id": eval_id,
            "outcome": args.outcome,
            "evaluator": args.evaluator,
            "evaluator_version": "1",
            "independent": bool(args.independent),
            "coverage": {},
            "note": "independence-claim-requires-agent-inaccessible-runner",
        },
    )
    assert seq is not None
    row = conn.execute("SELECT * FROM events WHERE event_id=?", (event_id,)).fetchone()
    assert row is not None
    ingest.apply_projection(conn, args.session, row)
    conn.commit()
    conn.close()
    _print(
        {
            "ok": True,
            "eval_id": eval_id,
            "outcome": args.outcome,
            "independent": bool(args.independent),
        },
        args.json,
    )
    return EXIT_OK


def cmd_jev_smoke(args: argparse.Namespace) -> int:
    settings = _settings(args)
    if not args.live:
        payload = {
            "ok": False,
            "status": "not-run",
            "reason": "live flag not given; no provider traffic attempted",
        }
        _print(payload, args.json)
        return EXIT_OK
    if not settings.jev_enabled:
        payload = {
            "ok": False,
            "status": "not-run",
            "reason": "JEV_GOVERNOR_JEV_ENABLED is not true",
        }
        _print(payload, args.json)
        return EXIT_OK
    key = config.read_api_key()
    if not key:
        payload = {"ok": False, "status": "not-run", "reason": "missing-credential"}
        _print(payload, args.json)
        return EXIT_OK
    attempts = min(int(args.max_attempts), settings.live_max_attempts or int(args.max_attempts))
    if attempts < 1:
        payload = {
            "ok": False,
            "status": "not-run",
            "reason": "attempt budget is zero; no authorization",
        }
        _print(payload, args.json)
        return EXIT_OK
    state = {
        "fixture": True,
        "same_assertion_after_distinct_patches": 2,
        "new_diagnostics_since_last_patch": 0,
        "hypothesis_changed": False,
        "n_failed_now": 1,
        "n_remaining": 1,
    }
    result = jev.evaluate(
        state=state,
        model=settings.jev_model,
        api_key=key,
        transport=jev.UrllibTransport(),
        max_attempts=attempts,
        deadline_s=60.0,
        per_attempt_timeout_s=settings.jev_timeout_seconds,
    )
    payload = {
        "ok": result.ok,
        "status": "ok" if result.ok else "failed",
        "model_requested": result.model_requested,
        "model_served": result.model_served,
        "features": result.features,
        "usage": result.usage,
        "latency_ms": result.latency_ms,
        "attempts": result.attempts,
        "error_kind": result.error_kind,
        "error": result.error[:300] if result.error else "",
    }
    _print(payload, args.json)
    return EXIT_OK if result.ok else EXIT_ERROR


def cmd_train(args: argparse.Namespace) -> int:
    try:
        dataset = learning.load_dataset([Path(p) for p in args.dataset])
    except OSError as exc:
        return _fail(str(exc), args.json)
    split = learning.grouped_split(dataset.rows)
    if not split["train"]:
        return _fail("no eligible training rows (all censored or rejected)", args.json)
    try:
        artifact = learning.train_predictor(split["train"], l2=args.l2)
    except learning.LearningError as exc:
        return _fail(str(exc), args.json)
    metrics = {name: learning.evaluate_split(artifact, rows) for name, rows in split.items()}
    artifact.update(
        {
            "label_def": {
                "1": "verified_success",
                "0": "failed_evaluation",
                "excluded": sorted(learning.CENSORED_OUTCOMES),
            },
            "split_sizes": {k: len(v) for k, v in split.items()},
            "metrics": metrics,
            "censored": dataset.censored,
            "rejected": dataset.rejected[:20],
            "usage": "shadow-only; never auto-promoted",
            "limitations": "supervised fit on observed decisions; no counterfactual "
            "claims; synthetic rows prove pipeline only",
        }
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")
    _print(
        {
            "ok": True,
            "path": str(out),
            "metrics": metrics,
            "support": artifact["support"],
            "censored": dataset.censored,
        },
        args.json,
    )
    return EXIT_OK


def cmd_evaluate(args: argparse.Namespace) -> int:
    try:
        artifact = json.loads(Path(args.model).read_text(encoding="utf-8"))
        learning.check_artifact(artifact)
    except (OSError, ValueError) as exc:
        return _fail(f"artifact rejected: {exc}", args.json)
    except learning.LearningError as exc:
        return _fail(f"artifact rejected: {exc}", args.json)
    try:
        dataset = learning.load_dataset([Path(p) for p in args.dataset])
    except OSError as exc:
        return _fail(str(exc), args.json)
    split = learning.grouped_split(dataset.rows)
    metrics = {name: learning.evaluate_split(artifact, rows) for name, rows in split.items()}
    coverage = {
        recipe: artifact.get("support", {}).get(recipe, 0)
        for recipe in (
            "CONTINUE",
            "ECONOMICAL_CONTINUE",
            "ESCALATE_DIAGNOSIS",
            "VERIFY_NOW",
            "PAUSE_REPLAN",
        )
    }
    unsupported = [r for r, n in coverage.items() if n < learning.MIN_ACTION_EXAMPLES]
    _print(
        {
            "ok": True,
            "metrics": metrics,
            "coverage": coverage,
            "unsupported_actions": unsupported,
            "note": "held-out grouped evaluation; no live decisions changed",
        },
        args.json,
    )
    return EXIT_OK


def cmd_shadow(args: argparse.Namespace) -> int:
    try:
        artifact = json.loads(Path(args.model).read_text(encoding="utf-8"))
        learning.check_artifact(artifact)
    except (OSError, ValueError, learning.LearningError) as exc:
        return _fail(f"artifact rejected: {exc}", args.json)
    settings = _settings(args)
    conn = _conn(settings)
    try:
        from . import features as feat

        feature_vector = feat.build_features(conn, args.session)
    except KeyError:
        conn.close()
        return _fail(f"unknown session: {args.session}", args.json)
    baseline = advisor.issue_recommendation(conn, args.session)
    result = learning.shadow_recommendation(
        artifact,
        feature_vector,
        baseline_selected=baseline["selected"],
        permitted=list(advisor.policy.RECIPES),
    )
    result["baseline"] = baseline["selected"]
    result["shadow_only"] = True
    conn.close()
    _print(result, args.json)
    return EXIT_OK


def cmd_replay(args: argparse.Namespace) -> int:
    with tempfile.TemporaryDirectory(prefix="jev-replay-") as tmp:
        settings = config.load_settings(Path(tmp))
        conn = storage.connect(settings)
        try:
            path = demo_mod.fixture_path(args.fixture)
        except FileNotFoundError:
            conn.close()
            return _fail(f"unknown fixture: {args.fixture}", args.json)
        fixture_file = Path(str(path))
        session_id = ""
        try:
            with fixture_file.open("r", encoding="utf-8") as handle:
                for line in handle:
                    if not line.strip():
                        continue
                    try:
                        record = json.loads(line)
                    except ValueError:
                        continue
                    if isinstance(record, dict) and record.get("session_id"):
                        session_id = str(record["session_id"])
                        break
        except OSError:
            session_id = ""
        if not session_id:
            conn.close()
            return _fail(f"fixture has no session_id: {args.fixture}", args.json)
        summary = ingest.import_jsonl(conn, session_id, fixture_file, fixture=True)
        decision = advisor.issue_recommendation(conn, session_id)
        conn.close()
    payload = {
        "fixture": args.fixture,
        "imported": summary.accepted,
        "selected": decision["selected"],
        "expected": args.expect,
        "match": decision["selected"] == args.expect,
        "note": experiments.replay_note(),
    }
    _print(payload, args.json)
    return EXIT_OK if payload["match"] else EXIT_ERROR


def cmd_experiment_validate(args: argparse.Namespace) -> int:
    try:
        manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return _fail(f"manifest unreadable: {exc}", args.json)
    errors = experiments.validate_manifest(manifest)
    payload = {
        "ok": not errors,
        "errors": errors,
        "note": "validation only; no continuation executed",
    }
    _print(payload, args.json)
    return EXIT_OK if not errors else EXIT_ERROR


def cmd_codex_qualify(args: argparse.Namespace) -> int:
    probe = codex_adapter.probe()
    if not args.run:
        payload = {
            "mode": "dry-run",
            "probe": probe,
            "plan": "codex-qualify --run --yes --session S --prompt '...' "
            "would run: codex exec --json --sandbox read-only -C <cwd> "
            "with a bounded timeout, then import events as observed. "
            "No inference is spent in dry-run.",
            "auth_required": "normal local codex login; governor never touches credentials",
        }
        _print(payload, args.json)
        return EXIT_OK
    if not args.yes:
        return _fail("live codex run requires --yes", args.json)
    if not probe["present"]:
        return _fail("codex runtime unavailable", args.json)
    if not args.prompt or len(args.prompt) > 2000:
        return _fail("need --prompt (<=2000 chars)", args.json)
    settings = _settings(args)
    conn = _conn(settings)
    prior = conn.execute(
        "SELECT COUNT(*) AS c FROM events WHERE session_id=? AND source='codex-exec-live'",
        (args.session,),
    ).fetchone()["c"]
    if prior and not args.force:
        conn.close()
        return _fail(
            "session already has a live qualify run; refusing duplicate "
            "admission (use --force to override)",
            args.json,
        )
    argv = ["codex", "exec", "--json", "--sandbox", args.sandbox, args.prompt]
    try:
        proc = subprocess.run(
            codex_adapter._effective_argv(argv),
            capture_output=True,
            text=True,
            timeout=args.timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        storage.insert_event(
            conn,
            event_id=f"evt-qual-{uuid.uuid4().hex[:8]}",
            session_id=args.session,
            event_type="intervention.unknown",
            provenance="observed",
            source="codex-exec-live",
            source_version=probe["version"] or "unknown",
            observed_at=utcnow_iso(),
            payload={
                "note": "timeout; remote work may still be running; "
                "outcome unknown, no retry attempted"
            },
        )
        conn.commit()
        conn.close()
        return _fail("codex exec timed out; outcome recorded as unknown", args.json)
    envelopes: list[dict[str, Any]] = []
    lines = (proc.stdout or "").splitlines()
    for lineno, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if not isinstance(record, dict):
            continue
        payload: dict[str, Any] = {"codex_type": str(record.get("type", "?"))[:128]}
        etype = "checkpoint.observed"
        usage = record.get("usage") if isinstance(record.get("usage"), dict) else None
        if usage:
            etype = "usage.reported"
            payload = {
                "kind": "unknown",
                "provider": "openai-codex",
                "model_served": "",
                "usage": usage,
            }
        envelopes.append(
            {
                "schema_version": 1,
                "event_id": f"qual-{args.session}-{lineno}",
                "session_id": args.session,
                "event_type": etype,
                "source": "codex-exec-live",
                "source_version": probe["version"] or "unknown",
                "observed_at": utcnow_iso(),
                "provenance": "observed",
                "payload": payload,
            }
        )
    summary = ingest.import_envelopes(conn, args.session, envelopes, source_path="codex-exec-live")
    conn.close()
    _print(
        {
            "ok": True,
            "exit_code": proc.returncode,
            "lines_seen": len(lines),
            "accepted": summary.accepted,
            "rejected": summary.rejected,
            "note": "granularity is turn-level at best; served model unknown "
            "unless the event stream reports it",
        },
        args.json,
    )
    return EXIT_OK


# ------------------------------------------------------------------ parser


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jev-gov", description="Jev Governor: local-first coding-session companion"
    )
    parser.add_argument("--data-dir", default=None, help="state directory override")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    common = argparse.ArgumentParser(add_help=False)
    # SUPPRESS so subcommand defaults never override globally parsed values.
    common.add_argument("--data-dir", default=argparse.SUPPRESS, help="state directory override")
    common.add_argument(
        "--json", action="store_true", default=argparse.SUPPRESS, help="machine-readable output"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("version", parents=[common], help="show versions")
    p.set_defaults(func=cmd_version)

    p = sub.add_parser(
        "doctor", parents=[common], help="environment + capability report (no secrets)"
    )
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("demo", parents=[common], help="one-command synthetic offline demo")
    p.add_argument("--no-verify-flow", action="store_true")
    p.set_defaults(func=cmd_demo)

    p = sub.add_parser("import", parents=[common], help="import JSONL events into a session")
    p.add_argument("--session", required=True)
    p.add_argument("--file", required=True)
    p.add_argument("--adapter", choices=["envelope", "codex-rollout"], default="envelope")
    p.set_defaults(func=cmd_import)

    p = sub.add_parser("inspect", parents=[common], help="show ledger, usage, and terminal state")
    p.add_argument("session")
    p.set_defaults(func=cmd_inspect)

    p = sub.add_parser("recommend", parents=[common], help="issue one advisory recommendation")
    p.add_argument("session")
    p.add_argument("--permitted", default=None, help="comma-separated recipe allowlist")
    p.add_argument("--economical-target", default=None)
    p.add_argument("--with-jev", action="store_true")
    p.add_argument("--live", action="store_true")
    p.add_argument("--max-attempts", type=int, default=0)
    p.set_defaults(func=cmd_recommend)

    p = sub.add_parser("report", parents=[common], help="full completion report")
    p.add_argument("session")
    p.set_defaults(func=cmd_report)

    p = sub.add_parser(
        "feedback", parents=[common], help="record human feedback (separate from eval)"
    )
    p.add_argument("session")
    p.add_argument("--kind", required=True, choices=["useful", "ignored", "harmful", "note"])
    p.add_argument("--text", required=True)
    p.set_defaults(func=cmd_feedback)

    p = sub.add_parser("export", parents=[common], help="privacy-safe JSONL export")
    p.add_argument("session")
    p.add_argument("--out", required=True)
    p.add_argument("--include-raw", action="store_true")
    p.add_argument("--group-id", default=None)
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("delete", parents=[common], help="delete local session data (needs --yes)")
    p.add_argument("--session", default=None)
    p.add_argument("--all", action="store_true")
    p.add_argument("--yes", action="store_true")
    p.set_defaults(func=cmd_delete)

    p = sub.add_parser(
        "prune", parents=[common], help="delete sessions older than N days (needs --yes)"
    )
    p.add_argument("--older-than-days", type=int, required=True)
    p.add_argument("--yes", action="store_true")
    p.set_defaults(func=cmd_prune)

    p = sub.add_parser("sessions", parents=[common], help="list sessions")
    p.set_defaults(func=cmd_sessions)

    p = sub.add_parser(
        "run-check", parents=[common], help="execute a registered check (trusted ingress)"
    )
    p.add_argument("session")
    p.add_argument("--recipe", required=True, choices=sorted(checks.RECIPES))
    p.add_argument("--workspace", required=True)
    p.add_argument("--req", action="append", default=[])
    p.add_argument("--path", action="append", default=[])
    p.add_argument("--k", default="")
    p.add_argument("--timeout", type=int, default=600)
    p.set_defaults(func=cmd_run_check)

    p = sub.add_parser("record-evaluation", parents=[common], help="record an evaluation outcome")
    p.add_argument("session")
    p.add_argument(
        "--outcome",
        required=True,
        choices=[
            "verified_success",
            "failed_evaluation",
            "unresolved_budget",
            "blocked",
            "cancelled",
            "evaluation_unavailable",
        ],
    )
    p.add_argument("--evaluator", required=True)
    p.add_argument("--independent", action="store_true")
    p.set_defaults(func=cmd_record_evaluation)

    p = sub.add_parser(
        "jev-smoke", parents=[common], help="bounded synthetic Jev request (explicit live)"
    )
    p.add_argument("--live", action="store_true")
    p.add_argument("--max-attempts", type=int, default=1)
    p.set_defaults(func=cmd_jev_smoke)

    p = sub.add_parser(
        "train", parents=[common], help="fit supervised outcome/cost predictor (offline)"
    )
    p.add_argument("--dataset", action="append", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--l2", type=float, default=1.0)
    p.set_defaults(func=cmd_train)

    p = sub.add_parser(
        "evaluate", parents=[common], help="held-out grouped evaluation of an artifact"
    )
    p.add_argument("--dataset", action="append", required=True)
    p.add_argument("--model", required=True)
    p.set_defaults(func=cmd_evaluate)

    p = sub.add_parser("shadow", parents=[common], help="shadow-only learned recommendation")
    p.add_argument("session")
    p.add_argument("--model", required=True)
    p.set_defaults(func=cmd_shadow)

    p = sub.add_parser(
        "replay", parents=[common], help="replay a fixture through the policy (no agents)"
    )
    p.add_argument("--fixture", required=True)
    p.add_argument("--expect", required=True)
    p.set_defaults(func=cmd_replay)

    p = sub.add_parser(
        "experiment-validate", parents=[common], help="validate a continuation manifest"
    )
    p.add_argument("--manifest", required=True)
    p.set_defaults(func=cmd_experiment_validate)

    p = sub.add_parser(
        "codex-qualify", parents=[common], help="bounded live codex check (dry-run default)"
    )
    p.add_argument("--run", action="store_true")
    p.add_argument("--yes", action="store_true")
    p.add_argument("--force", action="store_true")
    p.add_argument("--session", default="codex-qualify")
    p.add_argument("--prompt", default="")
    p.add_argument("--sandbox", default="read-only", choices=["read-only", "workspace-write"])
    p.add_argument("--timeout", type=int, default=180)
    p.set_defaults(func=cmd_codex_qualify)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "data_dir"):
        args.data_dir = None
    if not hasattr(args, "json"):
        args.json = False
    try:
        return int(args.func(args))
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return EXIT_ERROR
