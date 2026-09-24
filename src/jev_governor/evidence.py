"""Evidence ledger: requirements, check records, freshness, terminal outcomes.

Authority rules (no exceptions):
- Only ``trusted`` and ``evaluator`` provenance can support ``verified``.
- An imported ``trusted: true`` flag, a "tests passed" sentence, a model
  confidence score, or a bare exit code never upgrades authority.
- A relevant later patch makes earlier checks stale. Missing fingerprints
  reduce assurance (stale/degraded), never freshness.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from .schemas import AUTHORITATIVE_PROVENANCE

FRESH = "fresh"
STALE = "stale"
DEGRADED = "degraded"


@dataclass
class RepoFingerprint:
    commit: str = ""
    tree: str = ""
    relevant_paths: list[str] = field(default_factory=list)
    complete: bool = False

    @classmethod
    def from_payload(cls, raw: Any) -> RepoFingerprint:
        if not isinstance(raw, dict):
            return cls(complete=False)
        paths = raw.get("relevant_paths", [])
        if not isinstance(paths, list):
            paths = []
        return cls(
            commit=str(raw.get("commit", "")),
            tree=str(raw.get("tree", "")),
            relevant_paths=[str(p) for p in paths if isinstance(p, str)][:512],
            complete=bool(raw.get("complete", False)),
        )


@dataclass
class CheckRecord:
    check_id: str
    req_ids: list[str]
    recipe_id: str
    executor: str
    exit_status: int | None
    disposition: str
    env_fp: str
    repo_fp: RepoFingerprint
    started_at: str
    ended_at: str
    provenance: str
    seq: int

    @property
    def passed(self) -> bool | None:
        if self.disposition != "completed":
            return None
        if self.exit_status is None:
            return None
        return self.exit_status == 0

    @property
    def authoritative(self) -> bool:
        return self.provenance in AUTHORITATIVE_PROVENANCE


@dataclass
class PatchRecord:
    patch_id: str
    paths: list[str] | None  # None means unknown scope -> conservatively relevant
    seq: int


@dataclass
class RequirementVersion:
    req_id: str
    version: int
    origin: str
    text_ref: str
    acceptance: dict[str, Any]
    updated_seq: int
    blocked: bool = False


def acceptance_recipes(acceptance: dict[str, Any]) -> tuple[list[str], str]:
    recipes = acceptance.get("check_recipe_ids", [])
    if not isinstance(recipes, list):
        recipes = []
    mode = acceptance.get("required", "all")
    if mode not in ("all", "any"):
        mode = "all"
    return [str(r) for r in recipes if isinstance(r, str)], mode


def check_freshness(check: CheckRecord, later_patches: list[PatchRecord]) -> tuple[str, str]:
    """Return (fresh|stale, reason) for a check given later patches."""
    if not check.repo_fp.complete:
        return STALE, "missing-or-incomplete-fingerprint"
    if not check.repo_fp.relevant_paths:
        return DEGRADED, "no-relevant-paths-declared"
    covered = set(check.repo_fp.relevant_paths)
    for patch in later_patches:
        if patch.seq <= check.seq:
            continue
        if patch.paths is None:
            return STALE, f"patch-{patch.patch_id}-unknown-scope"
        if covered.intersection(patch.paths):
            return STALE, f"patch-{patch.patch_id}-overlaps"
    return FRESH, "no-relevant-later-patch"


def requirement_state(
    req: RequirementVersion,
    checks: list[CheckRecord],
    patches: list[PatchRecord],
) -> tuple[str, list[str], list[str]]:
    """Derive (state, evidence_refs, notes) for one requirement version."""
    if req.blocked:
        return "blocked", [], ["explicit-block-recorded"]
    recipes, mode = acceptance_recipes(req.acceptance)
    if not recipes:
        return "unknown", [], ["no-acceptance-mapping"]
    fresh_pass: set[str] = set()
    fresh_fail: set[str] = set()
    weak_support = False
    refs: list[str] = []
    notes: list[str] = []
    for check in checks:
        if req.req_id not in check.req_ids:
            continue
        if check.recipe_id not in recipes:
            continue
        verdict = check.passed
        if verdict is None:
            notes.append(f"{check.check_id}:no-verdict-{check.disposition}")
            continue
        status, reason = check_freshness(check, patches)
        refs.append(f"{check.check_id}:{status}:{check.provenance}")
        if status != FRESH:
            notes.append(f"{check.check_id}:stale-{reason}")
            continue
        if check.authoritative:
            if verdict:
                fresh_pass.add(check.recipe_id)
            else:
                fresh_fail.add(check.recipe_id)
        else:
            # Non-authoritative records are claims, not proof.
            notes.append(f"{check.check_id}:untrusted-provenance-{check.provenance}")
            if verdict:
                weak_support = True
            else:
                fresh_fail.add(check.recipe_id)
    if fresh_fail and (mode == "all" or not fresh_pass):
        if mode == "any" and fresh_pass:
            return "partially_verified", refs, notes + ["mixed-authoritative-results"]
        return "failed", refs, notes
    need = set(recipes)
    if mode == "any":
        if fresh_pass:
            return "verified", refs, notes
    elif need.issubset(fresh_pass):
        return "verified", refs, notes
    if fresh_pass or weak_support:
        return "partially_verified", refs, notes + ["incomplete-authoritative-coverage"]
    return "candidate", refs, notes + ["accepted-no-fresh-evidence"]


def derive_terminal_outcome(
    *,
    req_states: dict[str, str],
    evaluation: dict[str, Any] | None,
    session_ended: bool,
    budget_exhausted: bool,
    cancelled: bool,
) -> tuple[str, str]:
    """Map ledger state to a terminal outcome. Never invents success."""
    if evaluation is not None:
        outcome = str(evaluation.get("outcome", ""))
        if outcome == "verified_success":
            if all(s == "verified" for s in req_states.values()) and req_states:
                return "verified_success", "evaluation-confirms-all-verified"
            return "failed_evaluation", "evaluation-claims-success-without-full-coverage"
        if outcome in (
            "failed_evaluation",
            "unresolved_budget",
            "blocked",
            "cancelled",
            "evaluation_unavailable",
        ):
            return outcome, "evaluator-reported"
    if cancelled:
        return "cancelled", "cancellation-recorded"
    if budget_exhausted:
        return "unresolved_budget", "budget-exhausted-without-verification"
    if any(s == "blocked" for s in req_states.values()):
        return "blocked", "requirement-blocked"
    if req_states and all(s == "verified" for s in req_states.values()):
        # Ledger coverage without an independent evaluation is not success.
        return "incomplete", "ledger-covered-but-no-independent-evaluation"
    if session_ended:
        if any(s == "failed" for s in req_states.values()):
            return "failed_evaluation", " ended-with-failed-requirements".strip()
        return "incomplete", "session-ended-without-verification"
    return "incomplete", "session-open"


def payload_json(row: Any, key: str = "payload_json") -> dict[str, Any]:
    try:
        value = json.loads(row[key] or "{}")
    except (ValueError, KeyError, TypeError):
        return {}
    return value if isinstance(value, dict) else {}
