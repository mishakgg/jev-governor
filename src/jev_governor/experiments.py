"""Experiment manifests: validation for paired continuations + replay-only runs.

Paid real-agent branching is NOT implemented here: this module validates
manifests and replays fixtures through the policy (labeled replay-only, no
agent execution). Launching continuations needs a separately approved budget
and an isolated environment the alpha does not provision.
"""

from __future__ import annotations

from typing import Any

MANIFEST_VERSION = 1


def validate_manifest(manifest: Any) -> list[str]:
    """Return a list of blocking errors; empty means valid-for-planning."""
    errors: list[str] = []
    if not isinstance(manifest, dict):
        return ["manifest-must-be-an-object"]
    if manifest.get("manifest_version") != MANIFEST_VERSION:
        errors.append(f"unsupported-manifest_version:{manifest.get('manifest_version')}")
    checkpoint = manifest.get("checkpoint", {})
    if not isinstance(checkpoint, dict):
        errors.append("checkpoint-must-be-an-object")
        checkpoint = {}
    for key in ("session_id", "cutoff_seq", "repo_fp", "env_fp"):
        if key not in checkpoint:
            errors.append(f"checkpoint-missing:{key}")
    repo_fp = checkpoint.get("repo_fp", {})
    if isinstance(repo_fp, dict) and not repo_fp.get("complete"):
        errors.append("checkpoint-repo_fp-incomplete")
    acceptance = manifest.get("acceptance", {})
    if not isinstance(acceptance, dict) or not acceptance.get("contract_id"):
        errors.append("acceptance-contract-missing")
    envelope = manifest.get("resource_envelope", {})
    if not isinstance(envelope, dict):
        errors.append("resource_envelope-must-be-an-object")
    else:
        if not isinstance(envelope.get("max_total_tokens"), int):
            errors.append("resource_envelope-max_total_tokens-missing")
        if not envelope.get("budget_approved_by"):
            errors.append("resource_envelope-budget-not-approved")
    treatments = manifest.get("treatments", {})
    if not isinstance(treatments, dict) or len(treatments) < 2:
        errors.append("need-at-least-two-treatments")
    evaluator = manifest.get("evaluator", {})
    if not isinstance(evaluator, dict) or not evaluator.get("contract_id"):
        errors.append("evaluator-contract-missing")
    if manifest.get("live_database") or manifest.get("shared_writable_state"):
        errors.append("unsafe-shared-state: isolate branches before running")
    return errors


def replay_note() -> str:
    return (
        "replay-only: decisions recomputed from stored fixture events; "
        "no alternative agent execution occurred and no counterfactual "
        "saving can be inferred"
    )
