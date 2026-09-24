"""Trusted check runner: the only ingress that may create ``trusted`` records.

Registered recipes use fixed subprocess argument arrays -- never shell text
built from transcripts or model output. Paths are confined to the selected
workspace. A passing exit code is bound to the evaluated repository state;
it is the ledger (not the exit code) that decides requirement coverage.

WARNING: a check executes repository code. A worktree or directory check is
not a sandbox. Run untrusted targets only inside an appropriate existing
execution boundary.
"""

from __future__ import annotations

import hashlib
import sqlite3
import subprocess
import sys
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

MAX_HASH_BYTES = 8 * 1024 * 1024
RUN_TIMEOUT_S = 600


@dataclass(frozen=True)
class Recipe:
    recipe_id: str
    base_argv: tuple[str, ...]
    allow_k: bool = False


RECIPES: dict[str, Recipe] = {
    "pytest": Recipe("pytest", (sys.executable, "-m", "pytest"), allow_k=True),
    "python-file": Recipe("python-file", (sys.executable,)),
}


def fingerprint_repo(workspace: Path, relevant_paths: list[str]) -> dict[str, Any]:
    """Hash relevant files + git state. Incomplete when anything is missing."""
    commit = ""
    try:
        proc = subprocess.run(
            ["git", "-C", str(workspace), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        if proc.returncode == 0:
            commit = proc.stdout.strip()[:128]
    except (FileNotFoundError, subprocess.TimeoutExpired):
        commit = ""
    hashes: dict[str, str] = {}
    complete = True
    for rel in relevant_paths:
        target = (workspace / rel).resolve()
        try:
            target.relative_to(workspace.resolve())
        except ValueError:
            complete = False
            continue
        try:
            data = target.read_bytes()[:MAX_HASH_BYTES]
            hashes[rel] = hashlib.sha256(data).hexdigest()
        except OSError:
            complete = False
    if not relevant_paths:
        complete = False
    if not commit:
        complete = False
    return {
        "commit": commit,
        "relevant_paths": list(relevant_paths),
        "hashes": hashes,
        "complete": complete,
        "policy": "git-head-plus-sha256(relevant-paths)",
    }


def _confine(workspace: Path, rel: str) -> Path:
    target = (workspace / rel).resolve()
    target.relative_to(workspace.resolve())  # raises ValueError on escape
    return target


def run_check(
    conn: sqlite3.Connection,
    session_id: str,
    *,
    recipe_id: str,
    workspace: Path,
    req_ids: list[str],
    paths: list[str],
    k_expr: str = "",
    env_fp: str = "",
    timeout_s: int = RUN_TIMEOUT_S,
) -> dict[str, Any]:
    from .ingest import apply_projection
    from .storage import SessionRow, ensure_session, insert_event  # local import: layering

    recipe = RECIPES.get(recipe_id)
    if recipe is None:
        raise ValueError(f"unknown recipe: {recipe_id}")
    if recipe_id == "python-file" and len(paths) != 1:
        raise ValueError("python-file requires exactly one file path")
    confined: list[str] = []
    for rel in paths:
        if not rel or len(rel) > 512:
            raise ValueError(f"bad path: {rel!r}")
        confined.append(str(_confine(workspace, rel)))
    argv: list[str] = list(recipe.base_argv) + confined
    if k_expr:
        if not recipe.allow_k or len(k_expr) > 256:
            raise ValueError("k-expression not allowed for this recipe")
        argv += ["-k", k_expr]
    ensure_session(conn, SessionRow(session_id=session_id, workspace=str(workspace)))
    repo_fp = fingerprint_repo(workspace, paths)
    started = datetime.now(UTC).isoformat(timespec="seconds")
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
            cwd=str(workspace),
        )
        exit_status: int | None = proc.returncode
        disposition = "completed"
        tail = (proc.stdout + proc.stderr)[-2000:]
    except subprocess.TimeoutExpired:
        exit_status = None
        disposition = "timeout"
        tail = ""
    ended = datetime.now(UTC).isoformat(timespec="seconds")
    check_id = f"chk-{uuid.uuid4().hex[:12]}"
    payload = {
        "check_id": check_id,
        "req_ids": req_ids,
        "recipe_id": recipe_id,
        "executor": "local-runner",
        "exit_status": exit_status,
        "disposition": disposition,
        "env_fp": env_fp,
        "repo_fp": repo_fp,
        "started_at": started,
        "ended_at": ended,
        "argv_summary": [Path(a).name if a.startswith(str(workspace)) else a for a in argv],
        "output_tail": tail,
    }
    seq = insert_event(
        conn,
        event_id=f"evt-{check_id}",
        session_id=session_id,
        event_type="check.completed",
        provenance="trusted",
        source="local-runner",
        source_version="1",
        observed_at=ended,
        payload=payload,
    )
    assert seq is not None
    row = conn.execute("SELECT * FROM events WHERE event_id=?", (f"evt-{check_id}",)).fetchone()
    assert row is not None
    apply_projection(conn, session_id, row)
    conn.commit()
    return {
        "check_id": check_id,
        "exit_status": exit_status,
        "disposition": disposition,
        "freshness_basis": repo_fp,
    }
