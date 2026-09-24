"""Small offline supervised machinery: outcome/cost predictor + shadow use.

This is supervised learning, not RL: it fits numeric parameters mapping
decision-time features to observed terminal outcomes and costs. Log replay
cannot reveal counterfactual outcomes, so predictions are shadow-only and
abstain without adequate action coverage. No third-party ML dependency.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .features import LEAKAGE_DENYLIST
from .policy import RECIPES

ARTIFACT_VERSION = 1
LEARN_FEATURE_SCHEMA = "lfeat-1"
MIN_ACTION_EXAMPLES = 5

FEATURE_ORDER = [
    "n_requirements",
    "n_failed_now",
    "n_remaining",
    "distinct_patches",
    "same_assert_after_distinct_patches",
    "new_diagnostics_since_last_patch",
    "hypothesis_changed",
    "n_checks",
    "log_in_tokens",
    "log_out_tokens",
    "unknown_usage_ops",
    "usage_resets",
    "elapsed_s",
]

LABEL_SUCCESS = "verified_success"
LABEL_FAILURE = "failed_evaluation"
CENSORED_OUTCOMES = frozenset(
    {
        "unresolved_budget",
        "blocked",
        "cancelled",
        "evaluation_unavailable",
        "incomplete",
    }
)


class LearningError(ValueError):
    pass


@dataclass
class DatasetRow:
    group_id: str
    session_id: str
    recipe: str
    features: dict[str, float]
    label: int  # 1 success, 0 failure
    cost_tokens: int


@dataclass
class Dataset:
    rows: list[DatasetRow] = field(default_factory=list)
    censored: int = 0
    rejected: list[str] = field(default_factory=list)


def vectorize(features: dict[str, Any]) -> dict[str, float]:
    bad = [k for k in features if k in LEAKAGE_DENYLIST]
    if bad:
        raise LearningError(f"leakage feature(s) refused: {bad}")
    num = dict(features)
    num["hypothesis_changed"] = 1.0 if features.get("hypothesis_changed") else 0.0
    num["log_in_tokens"] = math.log1p(float(features.get("total_input_tokens", 0) or 0))
    num["log_out_tokens"] = math.log1p(float(features.get("total_output_tokens", 0) or 0))
    vector: dict[str, float] = {}
    for key in FEATURE_ORDER:
        value = num.get(key, 0)
        if isinstance(value, bool):
            value = 1.0 if value else 0.0
        if not isinstance(value, int | float) or not math.isfinite(float(value)):
            raise LearningError(f"non-numeric feature: {key}")
        vector[key] = float(value)
    return vector


def load_dataset(paths: list[Path]) -> Dataset:
    """Load training JSONL: {"record":"decision"|"outcome", ...} lines."""
    dataset = Dataset()
    decisions: dict[str, dict[str, Any]] = {}
    outcomes: dict[str, dict[str, Any]] = {}
    for path in paths:
        with path.open("r", encoding="utf-8") as handle:
            for lineno, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except ValueError:
                    dataset.rejected.append(f"{path}:{lineno}:invalid-json")
                    continue
                if not isinstance(record, dict):
                    dataset.rejected.append(f"{path}:{lineno}:not-an-object")
                    continue
                kind = record.get("record")
                if kind == "decision":
                    key = f"{record.get('session_id')}:{record.get('decision_id')}"
                    decisions[key] = record
                elif kind == "outcome":
                    outcomes[str(record.get("session_id"))] = record
                elif kind == "manifest":
                    continue
                else:
                    dataset.rejected.append(f"{path}:{lineno}:unknown-record:{kind}")
    for key, decision in decisions.items():
        session_id = str(decision.get("session_id", ""))
        outcome = outcomes.get(session_id)
        if outcome is None:
            dataset.censored += 1
            continue
        terminal = str(outcome.get("terminal_outcome", ""))
        if terminal in CENSORED_OUTCOMES:
            dataset.censored += 1
            continue
        if terminal == LABEL_SUCCESS:
            label = 1
        elif terminal == LABEL_FAILURE:
            label = 0
        else:
            dataset.rejected.append(f"{key}:unknown-outcome:{terminal}")
            continue
        recipe = decision.get("selected")
        if recipe not in RECIPES:
            dataset.censored += 1
            continue
        try:
            vector = vectorize(decision.get("features", {}))
        except LearningError as exc:
            dataset.rejected.append(f"{key}:{exc}")
            continue
        dataset.rows.append(
            DatasetRow(
                group_id=str(decision.get("group_id", session_id)),
                session_id=session_id,
                recipe=str(recipe),
                features=vector,
                label=label,
                cost_tokens=int(outcome.get("total_tokens", 0) or 0),
            )
        )
    return dataset


def grouped_split(rows: list[DatasetRow]) -> dict[str, list[DatasetRow]]:
    """Deterministic group split: sessions never straddle train/test."""
    groups = sorted({r.group_id for r in rows})
    split: dict[str, list[DatasetRow]] = {"train": [], "valid": [], "test": []}
    group_of: dict[str, str] = {}
    for group in groups:
        digest = hashlib.sha256(group.encode("utf-8")).hexdigest()
        bucket = int(digest[:8], 16) % 100
        if bucket < 70:
            group_of[group] = "train"
        elif bucket < 85:
            group_of[group] = "valid"
        else:
            group_of[group] = "test"
    for row in rows:
        split[group_of[row.group_id]].append(row)
    return split


def _sigmoid(z: float) -> float:
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    clipped = max(z, -60.0)
    exp_z = math.exp(clipped)
    return exp_z / (1.0 + exp_z)


def _scaler(rows: list[DatasetRow]) -> tuple[dict[str, float], dict[str, float]]:
    means: dict[str, float] = {}
    stds: dict[str, float] = {}
    for key in FEATURE_ORDER:
        values = [r.features[key] for r in rows]
        mean = sum(values) / len(values) if values else 0.0
        var = sum((v - mean) ** 2 for v in values) / len(values) if values else 0.0
        means[key] = mean
        stds[key] = math.sqrt(var) if var > 1e-12 else 1.0
    return means, stds


def _standardize(
    vector: dict[str, float], means: dict[str, float], stds: dict[str, float]
) -> list[float]:
    return [(vector[k] - means[k]) / stds[k] for k in FEATURE_ORDER]


def train_predictor(
    rows: list[DatasetRow],
    *,
    l2: float = 1.0,
    steps: int = 500,
    lr: float = 0.1,
) -> dict[str, Any]:
    """Fit L2 logistic (outcome) + ridge (log-cost) heads. Deterministic."""
    if len(rows) < 2:
        raise LearningError("need at least 2 eligible rows to fit")
    means, stds = _scaler(rows)
    dim = len(FEATURE_ORDER)
    w_out = [0.0] * dim
    b_out = 0.0
    w_cost = [0.0] * dim
    b_cost = 0.0
    targets = [math.log1p(max(0, r.cost_tokens)) for r in rows]
    mean_cost = sum(targets) / len(targets)
    b_cost = mean_cost
    n = len(rows)
    X = [_standardize(r.features, means, stds) for r in rows]
    for _ in range(steps):
        g_w = [0.0] * dim
        g_b = 0.0
        for x, row in zip(X, rows, strict=True):
            pred = _sigmoid(sum(wi * xi for wi, xi in zip(w_out, x, strict=True)) + b_out)
            err = pred - row.label
            for j in range(dim):
                g_w[j] += err * x[j] / n + (l2 / n) * w_out[j]
            g_b += err / n
        for j in range(dim):
            w_out[j] -= lr * g_w[j]
        b_out -= lr * g_b
    for _ in range(steps):
        g_w = [0.0] * dim
        g_c = 0.0
        for x, target in zip(X, targets, strict=True):
            pred = sum(wi * xi for wi, xi in zip(w_cost, x, strict=True)) + b_cost
            err = pred - target
            for j in range(dim):
                g_w[j] += 2 * err * x[j] / n + 2 * (l2 / n) * w_cost[j]
            g_c += 2 * err / n
        for j in range(dim):
            w_cost[j] -= lr * 0.1 * g_w[j]
        b_cost -= lr * 0.1 * g_c
    support: dict[str, int] = {}
    for row in rows:
        support[row.recipe] = support.get(row.recipe, 0) + 1
    return {
        "artifact_version": ARTIFACT_VERSION,
        "feature_schema": LEARN_FEATURE_SCHEMA,
        "algorithm": "l2-logistic-outcome + ridge-logcost (supervised, stdlib)",
        "weights_outcome": w_out,
        "bias_outcome": b_out,
        "weights_cost": w_cost,
        "bias_cost": b_cost,
        "means": means,
        "stds": stds,
        "support": support,
        "min_action_examples": MIN_ACTION_EXAMPLES,
        "n_rows": len(rows),
    }


def check_artifact(artifact: dict[str, Any]) -> None:
    if artifact.get("artifact_version") != ARTIFACT_VERSION:
        raise LearningError(f"incompatible artifact_version: {artifact.get('artifact_version')}")
    if artifact.get("feature_schema") != LEARN_FEATURE_SCHEMA:
        raise LearningError(f"incompatible feature_schema: {artifact.get('feature_schema')}")
    for key in ("weights_outcome", "weights_cost", "means", "stds"):
        if key not in artifact:
            raise LearningError(f"artifact missing {key}")


def predict(artifact: dict[str, Any], features: dict[str, Any]) -> tuple[float, float, bool, str]:
    """Return (p_success, expected_log_cost, abstain, reason)."""
    check_artifact(artifact)
    vector = vectorize(features)
    means = artifact["means"]
    stds = artifact["stds"]
    x = [(vector[k] - means[k]) / stds[k] for k in FEATURE_ORDER]
    p_ok = _sigmoid(
        sum(w * xi for w, xi in zip(artifact["weights_outcome"], x, strict=True))
        + float(artifact["bias_outcome"])
    )
    log_cost = sum(w * xi for w, xi in zip(artifact["weights_cost"], x, strict=True)) + float(
        artifact["bias_cost"]
    )
    return p_ok, log_cost, False, "ok"


def evaluate_split(artifact: dict[str, Any], rows: list[DatasetRow]) -> dict[str, Any]:
    if not rows:
        return {"n": 0, "note": "empty split"}
    check_artifact(artifact)
    correct = 0
    brier = 0.0
    abs_err = 0.0
    for row in rows:
        p_ok, log_cost, _, _ = predict(artifact, row.features)
        correct += int((p_ok >= 0.5) == bool(row.label))
        brier += (p_ok - row.label) ** 2
        abs_err += abs(log_cost - math.log1p(max(0, row.cost_tokens)))
    n = len(rows)
    return {
        "n": n,
        "accuracy": round(correct / n, 4),
        "brier": round(brier / n, 4),
        "mae_log_cost": round(abs_err / n, 4),
    }


def shadow_recommendation(
    artifact: dict[str, Any],
    features: dict[str, Any],
    *,
    baseline_selected: str | None,
    permitted: list[str],
) -> dict[str, Any]:
    """Shadow-only ranking: never promoted automatically, abstains on gaps."""
    check_artifact(artifact)
    support = artifact.get("support", {})
    eligible = [r for r in permitted if support.get(r, 0) >= MIN_ACTION_EXAMPLES]
    if not eligible:
        return {
            "shadow_selected": None,
            "abstained": True,
            "reason": "inadequate-action-coverage",
            "support": support,
        }
    p_ok, _, _, _ = predict(artifact, features)
    # Conservative: agree with baseline when covered, else best-covered action.
    if baseline_selected in eligible:
        return {
            "shadow_selected": baseline_selected,
            "abstained": False,
            "reason": "baseline-covered",
            "p_success": round(p_ok, 4),
            "eligible": eligible,
        }
    return {
        "shadow_selected": eligible[0],
        "abstained": False,
        "reason": "baseline-uncovered-fallback",
        "p_success": round(p_ok, 4),
        "eligible": eligible,
    }
