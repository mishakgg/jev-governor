"""Narrow Codex CLI adapter (read-only by default).

Two supported paths:
1. ``probe`` -- version/auth/capability report from ``codex --version`` and the
   redacted ``codex doctor --json`` output. Never triggers inference and never
   prints secrets (only check id/category/status/summary are retained).
2. ``import_rollout`` -- versioned import of an explicitly selected local
   rollout JSONL file (``~/.codex/sessions/...``) into envelope events.
   Undocumented upstream format: parsed defensively, everything stays
   ``imported`` provenance, content minimized by default.

Live ``codex exec`` observation exists only behind the explicit bounded
``codex-qualify --run`` command (see cli.py). Control granularity observed in
turn_context/app-server docs is turn-level; per-generation routing is NOT
claimed.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ADAPTER_NAME = "codex-cli"
ADAPTER_VERSION = "codex-cli-import-1"
PROBE_TIMEOUT_S = 30


@dataclass
class Capability:
    name: str
    status: str  # supported|unsupported|unavailable|untested (+observed/documented note)
    detail: str
    evidence: str = ""


def _effective_argv(argv: list[str]) -> list[str]:
    """Resolve Windows console-script shims (.cmd/.bat need cmd.exe)."""
    import os

    if os.name != "nt" or not argv:
        return argv
    resolved = shutil.which(argv[0])
    if resolved and resolved.lower().endswith((".cmd", ".bat")):
        return ["cmd", "/d", "/s", "/c", resolved, *argv[1:]]
    return argv


def _run(argv: list[str], timeout: int) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            _effective_argv(argv),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        return 127, "", "not-found"
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"
    return proc.returncode, proc.stdout, proc.stderr


def probe(codex_bin: str = "codex") -> dict[str, Any]:
    """Probe the local Codex CLI without inference and without secrets."""
    caps: list[Capability] = []
    exe = shutil.which(codex_bin)
    present = exe is not None
    version = ""
    if present:
        caps.append(Capability("runtime.present", "supported", f"found at {exe}", evidence="which"))
        code, out, _ = _run([codex_bin, "--version"], PROBE_TIMEOUT_S)
        version = (out.strip() or "").splitlines()[0][:128] if out.strip() else ""
        if code == 0 and version:
            caps.append(
                Capability("runtime.version", "supported", version, evidence="codex --version")
            )
        else:
            caps.append(
                Capability(
                    "runtime.version",
                    "unavailable",
                    "version query failed",
                    evidence=f"exit={code}",
                )
            )
    else:
        caps.append(
            Capability("runtime.present", "unavailable", "codex not on PATH", evidence="which")
        )
    auth_label = "unknown"
    doctor_status = "not-run"
    if present:
        code, out, _ = _run([codex_bin, "doctor", "--json"], PROBE_TIMEOUT_S)
        if code == 0:
            try:
                doctor = json.loads(out)
            except ValueError:
                doctor = None
            if isinstance(doctor, dict):
                doctor_status = str(doctor.get("overallStatus", "unknown"))[:32]
                checks = doctor.get("checks", {})
                auth = checks.get("auth.credentials", {}) if isinstance(checks, dict) else {}
                auth_label = (
                    f"{auth.get('status', '?')}: {str(auth.get('summary', ''))[:80]}"
                    if auth
                    else "not-reported"
                )
                caps.append(
                    Capability(
                        "auth.status-nonsecret",
                        "supported",
                        auth_label,
                        evidence="codex doctor --json (summary only)",
                    )
                )
            else:
                caps.append(
                    Capability(
                        "auth.status-nonsecret",
                        "unavailable",
                        "doctor output unparseable",
                        evidence="codex doctor --json",
                    )
                )
        else:
            caps.append(
                Capability(
                    "auth.status-nonsecret",
                    "unavailable",
                    f"doctor failed (exit={code})",
                    evidence="codex doctor --json",
                )
            )
    else:
        caps.append(
            Capability(
                "auth.status-nonsecret", "unavailable", "no runtime to query", evidence="none"
            )
        )
    # Static capability declarations (documented vs observed vs untested).
    caps.extend(
        [
            Capability(
                "events.exec-json",
                "untested",
                "codex exec --json advertises JSONL events; no live run performed",
                evidence="documented: codex exec --help",
            ),
            Capability(
                "events.rollout-import",
                "supported",
                "versioned parser for explicitly selected local rollout JSONL; "
                "undocumented upstream format, defensive parse, imported-only",
                evidence="observed: local rollout vocabulary survey (0.146/0.155)",
            ),
            Capability(
                "usage.thread-cumulative",
                "supported",
                "thread_token_usage is monotonic cumulative; turn_token_usage is "
                "per-turn delta; cached/reasoning are subsets",
                evidence="observed: 227 usage records checked locally",
            ),
            Capability(
                "control.model-per-turn",
                "untested",
                "turn-level model/effort selection exists (exec -m/-c, turn_context); "
                "per-generation routing is NOT claimed",
                evidence="documented: exec --help, app-server docs",
            ),
            Capability(
                "control.apply",
                "unsupported",
                "alpha is advisory-only; no model/effort switching is executed",
                evidence="design: advisory default",
            ),
            Capability(
                "control.interrupt",
                "untested",
                "no cancellation path exercised; local disconnect would not prove "
                "remote cancellation",
                evidence="none",
            ),
        ]
    )
    return {
        "adapter": ADAPTER_NAME,
        "adapter_version": ADAPTER_VERSION,
        "present": present,
        "executable": exe or "",
        "version": version,
        "doctor_status": doctor_status,
        "auth": auth_label,
        "capabilities": [c.__dict__ for c in caps],
    }


def default_sessions_root() -> Path:
    return Path.home() / ".codex" / "sessions"


def list_rollout_files(limit: int = 20) -> list[str]:
    root = default_sessions_root()
    if not root.is_dir():
        return []
    files = sorted(root.rglob("rollout-*.jsonl"))
    return [str(p) for p in files[-limit:]]


@dataclass
class RolloutImport:
    envelopes: list[dict[str, Any]] = field(default_factory=list)
    diagnostics: list[str] = field(default_factory=list)
    cli_version: str = ""
    rejected: int = 0


_USAGE_KEYS = (
    "input_tokens",
    "cached_input_tokens",
    "cache_write_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
    "total_tokens",
)


def _usage_numbers(raw: Any) -> dict[str, int]:
    out: dict[str, int] = {}
    if not isinstance(raw, dict):
        return out
    for key in _USAGE_KEYS:
        value = raw.get(key)
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            out[key] = value
    return out


def convert_rollout(path: Path, session_id: str) -> RolloutImport:
    """Convert a rollout JSONL file to envelope events (defensive, minimal).

    Content policy: identifiers, status, timing, and numeric usage are kept;
    message text, tool input/output, and file contents are dropped. Raw
    retention is never enabled by this path.
    """
    result = RolloutImport()
    try:
        handle = path.open("r", encoding="utf-8", errors="replace")
    except FileNotFoundError:
        result.diagnostics.append(f"file-not-found:{path}")
        result.rejected = 1
        return result
    lineno = 0
    ordinal_base = 0
    with handle:
        for line in handle:
            lineno += 1
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except ValueError:
                result.rejected += 1
                if len(result.diagnostics) < 50:
                    result.diagnostics.append(f"line-{lineno}:invalid-json")
                continue
            if not isinstance(record, dict):
                result.rejected += 1
                continue
            rtype = record.get("type")
            payload = record.get("payload", {})
            ordinal = record.get("ordinal", lineno)
            if not isinstance(ordinal, int):
                ordinal = lineno
            ordinal_base = max(ordinal_base, ordinal if isinstance(ordinal, int) else 0)
            ts = str(record.get("timestamp", ""))[:64]
            if rtype == "session_meta" and isinstance(payload, dict):
                result.cli_version = str(payload.get("cli_version", ""))[:64]
                result.envelopes.append(
                    {
                        "schema_version": 1,
                        "event_id": f"codex-{session_id}-meta",
                        "session_id": session_id,
                        "event_type": "session.started",
                        "source": "codex-rollout",
                        "source_version": result.cli_version or "unknown",
                        "observed_at": ts or "1970-01-01T00:00:00Z",
                        "provenance": "imported",
                        "payload": {
                            "workspace": str(payload.get("cwd", ""))[:512],
                            "adapter": ADAPTER_NAME,
                            "adapter_version": result.cli_version,
                            "label": str(payload.get("id", ""))[:256],
                            "provider": str(payload.get("model_provider", ""))[:64],
                        },
                    }
                )
            elif rtype == "turn_context" and isinstance(payload, dict):
                result.envelopes.append(
                    {
                        "schema_version": 1,
                        "event_id": f"codex-{session_id}-turn-{ordinal}",
                        "session_id": session_id,
                        "event_type": "checkpoint.observed",
                        "source": "codex-rollout",
                        "source_version": result.cli_version or "unknown",
                        "observed_at": ts or "1970-01-01T00:00:00Z",
                        "provenance": "imported",
                        "payload": {
                            "turn_id": str(payload.get("turn_id", ""))[:128],
                            "model_requested": str(payload.get("model", ""))[:128],
                            "model_served": "",
                            "effort": str(payload.get("effort", ""))[:32],
                            "sandbox": str(payload.get("sandbox_policy", ""))[:64],
                            "note": "requested-config-only;served-model-unknown",
                        },
                    }
                )
            elif rtype == "token_usage_record" and isinstance(payload, dict):
                thread_usage = _usage_numbers(payload.get("thread_token_usage"))
                if not thread_usage:
                    continue
                # Import the cumulative thread totals only; turn/usage fields
                # describe the same spend at finer granularity.
                result.envelopes.append(
                    {
                        "schema_version": 1,
                        "event_id": f"codex-{session_id}-usage-{ordinal}",
                        "session_id": session_id,
                        "event_type": "usage.reported",
                        "source": "codex-rollout",
                        "source_version": result.cli_version or "unknown",
                        "observed_at": ts or "1970-01-01T00:00:00Z",
                        "provenance": "imported",
                        "payload": {
                            "kind": "cumulative",
                            "stream_id": str(payload.get("thread_id", "thread"))[:256],
                            "epoch": str(payload.get("session_id", ""))[:256],
                            "stream_seq": ordinal,
                            "provider": "openai-codex",
                            "model_requested": "",
                            "model_served": "",
                            "usage": thread_usage,
                        },
                    }
                )
            elif rtype == "event_msg" and isinstance(payload, dict):
                inner = str(payload.get("type", ""))[:64]
                if inner in ("task_complete", "turn_aborted", "task_started"):
                    result.envelopes.append(
                        {
                            "schema_version": 1,
                            "event_id": f"codex-{session_id}-ev-{ordinal}",
                            "session_id": session_id,
                            "event_type": "checkpoint.observed",
                            "source": "codex-rollout",
                            "source_version": result.cli_version or "unknown",
                            "observed_at": ts or "1970-01-01T00:00:00Z",
                            "provenance": "imported",
                            "payload": {
                                "codex_event": inner,
                                "turn_id": str(payload.get("turn_id", ""))[:128],
                                "duration_ms": payload.get("duration_ms"),
                                "reason": str(payload.get("reason", ""))[:256],
                            },
                        }
                    )
                elif inner == "item_completed":
                    item = payload.get("item", {})
                    name = ""
                    status = ""
                    if isinstance(item, dict):
                        name = str(item.get("name", item.get("type", "")))[:128]
                        status = str(item.get("status", ""))[:64]
                    result.envelopes.append(
                        {
                            "schema_version": 1,
                            "event_id": f"codex-{session_id}-tool-{ordinal}",
                            "session_id": session_id,
                            "event_type": "tool.completed",
                            "source": "codex-rollout",
                            "source_version": result.cli_version or "unknown",
                            "observed_at": ts or "1970-01-01T00:00:00Z",
                            "provenance": "imported",
                            "payload": {
                                "tool": name,
                                "status": status,
                                "turn_id": str(payload.get("turn_id", ""))[:128],
                            },
                        }
                    )
            # Other record types (response_item content, world_state, compacted,
            # token_count) are intentionally skipped: content-bearing or redundant.
    return result
