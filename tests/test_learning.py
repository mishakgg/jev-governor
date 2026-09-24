"""Supervised machinery: fit, grouped splits, leakage, coverage, abstention."""

from __future__ import annotations

import json

import pytest

from jev_governor import learning


def _features(kind="plain"):
    base = {
        "n_requirements": 1,
        "n_failed_now": 0,
        "n_remaining": 1,
        "distinct_patches": 1,
        "same_assert_after_distinct_patches": 0,
        "new_diagnostics_since_last_patch": 0,
        "hypothesis_changed": False,
        "n_checks": 1,
        "total_input_tokens": 1000,
        "total_output_tokens": 100,
        "unknown_usage_ops": 0,
        "usage_resets": 0,
        "elapsed_s": 60.0,
    }
    if kind == "bad":
        base.update(n_failed_now=2, same_assert_after_distinct_patches=2)
    return base


def _write_dataset(path, n_groups=12):
    lines = [json.dumps({"record": "manifest", "test": True})]
    recipes = ["CONTINUE", "VERIFY_NOW", "ESCALATE_DIAGNOSIS"]
    for group in range(n_groups):
        session = f"sess-{group}"
        kind = "bad" if group % 3 == 0 else "plain"
        for rep in range(3):
            lines.append(
                json.dumps(
                    {
                        "record": "decision",
                        "decision_id": f"d-{group}-{rep}",
                        "session_id": session,
                        "group_id": f"group-{group}",
                        "cutoff_seq": rep,
                        "features": _features(kind),
                        "feature_schema": "feat-1",
                        "policy_version": "det-1",
                        "selected": recipes[(group + rep) % 3],
                    }
                )
            )
        lines.append(
            json.dumps(
                {
                    "record": "outcome",
                    "session_id": session,
                    "group_id": f"group-{group}",
                    "terminal_outcome": "failed_evaluation"
                    if kind == "bad"
                    else "verified_success",
                    "total_tokens": 1100,
                }
            )
        )
    # One censored session: excluded from rows, counted as censored.
    lines.append(
        json.dumps(
            {
                "record": "decision",
                "decision_id": "d-c",
                "session_id": "sess-c",
                "group_id": "group-c",
                "cutoff_seq": 0,
                "features": _features(),
                "feature_schema": "feat-1",
                "policy_version": "det-1",
                "selected": "CONTINUE",
            }
        )
    )
    lines.append(
        json.dumps(
            {
                "record": "outcome",
                "session_id": "sess-c",
                "group_id": "group-c",
                "terminal_outcome": "incomplete",
                "total_tokens": 10,
            }
        )
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_load_excludes_censored(tmp_path):
    dataset_path = tmp_path / "ds.jsonl"
    _write_dataset(dataset_path)
    dataset = learning.load_dataset([dataset_path])
    assert dataset.censored == 1
    assert len(dataset.rows) == 36
    assert {r.label for r in dataset.rows} == {0, 1}


def test_grouped_split_never_straddles_groups(tmp_path):
    dataset_path = tmp_path / "ds.jsonl"
    _write_dataset(dataset_path)
    dataset = learning.load_dataset([dataset_path])
    split = learning.grouped_split(dataset.rows)
    seen = {}
    for name, rows in split.items():
        for row in rows:
            assert seen.get(row.group_id, name) == name
            seen[row.group_id] = name
    assert split["train"]


def test_train_fits_real_parameters_and_evaluates(tmp_path):
    dataset_path = tmp_path / "ds.jsonl"
    _write_dataset(dataset_path, n_groups=20)
    dataset = learning.load_dataset([dataset_path])
    split = learning.grouped_split(dataset.rows)
    artifact = learning.train_predictor(split["train"])
    assert artifact["artifact_version"] == 1
    assert any(abs(w) > 1e-9 for w in artifact["weights_outcome"])
    metrics = learning.evaluate_split(artifact, split["test"] or split["valid"])
    assert 0.0 <= metrics["accuracy"] <= 1.0
    assert 0.0 <= metrics["brier"] <= 1.0


def test_leakage_features_refused():
    with pytest.raises(learning.LearningError):
        learning.vectorize({**_features(), "terminal_outcome": "verified_success"})


def test_incompatible_artifact_refused():
    with pytest.raises(learning.LearningError):
        learning.check_artifact({"artifact_version": 999, "feature_schema": "lfeat-1"})
    with pytest.raises(learning.LearningError):
        learning.check_artifact({"artifact_version": 1, "feature_schema": "other"})


def test_shadow_abstains_without_coverage(tmp_path):
    dataset_path = tmp_path / "ds.jsonl"
    _write_dataset(dataset_path, n_groups=20)
    dataset = learning.load_dataset([dataset_path])
    artifact = learning.train_predictor(learning.grouped_split(dataset.rows)["train"])
    thin = dict(artifact, support={"CONTINUE": 1})
    result = learning.shadow_recommendation(
        thin, _features(), baseline_selected="CONTINUE", permitted=["CONTINUE"]
    )
    assert result["abstained"]
    assert result["reason"] == "inadequate-action-coverage"


def test_too_few_rows_refuses():
    with pytest.raises(learning.LearningError):
        learning.train_predictor([])
