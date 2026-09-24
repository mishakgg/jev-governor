"""End-to-end CLI flows on isolated stores."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from jev_governor import demo as demo_mod

DATA = Path(__file__).parent / "data"
FIXTURES = Path(demo_mod.fixture_path("demo-loop.jsonl")).parent


def test_demo_matches_expected(cli_runner):
    code, out, err = cli_runner("demo", "--no-verify-flow", "--json")
    assert code == 0
    payload = json.loads(out)
    for session_id, expected in (
        ("demo-loop", "ESCALATE_DIAGNOSIS"),
        ("demo-productive", "CONTINUE"),
        ("demo-stale", "VERIFY_NOW"),
        ("demo-budget", "PAUSE_REPLAN"),
    ):
        assert payload["sessions"][session_id]["match"], session_id
        assert payload["sessions"][session_id]["outcome_ok"], session_id


def test_full_workflow_import_to_delete(cli_runner, data_dir):
    code, out, _ = cli_runner(
        "import", "--session", "demo-loop", "--file", str(FIXTURES / "demo-loop.jsonl")
    )
    assert code == 0
    code, out, _ = cli_runner("inspect", "demo-loop", "--json")
    assert code == 0
    assert json.loads(out)["terminal_outcome"] == "incomplete"
    code, out, _ = cli_runner("recommend", "demo-loop", "--json")
    assert code == 0
    assert json.loads(out)["selected"] == "ESCALATE_DIAGNOSIS"
    code, out, _ = cli_runner("report", "demo-loop")
    assert code == 0 and "ESCALATE_DIAGNOSIS" in out
    code, out, _ = cli_runner("feedback", "demo-loop", "--kind", "useful", "--text", "helpful")
    assert code == 0
    export_path = data_dir / "wf-1.jsonl"
    code, out, _ = cli_runner("export", "demo-loop", "--out", str(export_path), "--group-id", "g1")
    assert code == 0
    text = export_path.read_text(encoding="utf-8")
    assert '"record": "decision"' in text
    assert "TYPESAFE" not in text
    code, out, _ = cli_runner("delete", "--session", "demo-loop")
    assert code == 1  # refuses without --yes
    code, out, _ = cli_runner("delete", "--session", "demo-loop", "--yes")
    assert code == 0
    code, out, _ = cli_runner("inspect", "demo-loop")
    assert code == 1


def test_run_check_trusted_and_evaluation(cli_runner, data_dir, tmp_path):
    repo = tmp_path / "mini"
    repo.mkdir()
    (repo / "check_ok.py").write_text("print('ok')\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(repo)], capture_output=True, check=False)
    subprocess.run(["git", "-C", str(repo), "add", "."], capture_output=True, check=False)
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "x"],
        capture_output=True,
        check=False,
    )
    code, out, _ = cli_runner(
        "import", "--session", "demo-stale", "--file", str(FIXTURES / "demo-stale.jsonl")
    )
    assert code == 0
    code, out, _ = cli_runner(
        "run-check",
        "demo-stale",
        "--recipe",
        "python-file",
        "--workspace",
        str(repo),
        "--req",
        "R1",
        "--path",
        "check_ok.py",
        "--json",
    )
    assert code == 0, out
    assert json.loads(out)["exit_status"] == 0
    code, out, _ = cli_runner(
        "record-evaluation",
        "demo-stale",
        "--outcome",
        "verified_success",
        "--evaluator",
        "test-attestor",
    )
    assert code == 0
    code, out, _ = cli_runner("inspect", "demo-stale", "--json")
    assert code == 0
    # The imported synthetic check is stale/weak; the trusted check ran against
    # a different repo state (mini repo), so the requirement is NOT verified:
    # honesty check -- no false freshness across states.
    assert json.loads(out)["terminal_outcome"] in ("failed_evaluation", "incomplete")


def test_run_check_rejects_escape(cli_runner, tmp_path):
    code, out, err = cli_runner(
        "run-check",
        "s-esc",
        "--recipe",
        "python-file",
        "--workspace",
        str(tmp_path),
        "--path",
        "../evil.py",
    )
    assert code == 1


def test_import_codex_rollout(cli_runner):
    code, out, _ = cli_runner(
        "import",
        "--session",
        "wf-codex",
        "--file",
        str(DATA / "sample_rollout.jsonl"),
        "--adapter",
        "codex-rollout",
        "--json",
    )
    assert code == 0
    assert json.loads(out)["accepted"] > 0
    code, out, _ = cli_runner("inspect", "wf-codex", "--json")
    assert json.loads(out)["usage"]["input_tokens"] == 1500


def test_jev_smoke_defaults_to_not_run(cli_runner):
    code, out, _ = cli_runner("jev-smoke", "--json")
    payload = json.loads(out)
    assert code == 0
    assert payload["status"] == "not-run"


def test_codex_qualify_dry_run(cli_runner):
    code, out, _ = cli_runner("codex-qualify", "--json")
    payload = json.loads(out)
    assert code == 0
    assert payload["mode"] == "dry-run"


def test_replay_and_experiment_validate(cli_runner, tmp_path):
    code, out, _ = cli_runner(
        "replay", "--fixture", "demo-loop.jsonl", "--expect", "ESCALATE_DIAGNOSIS", "--json"
    )
    assert code == 0, out
    assert json.loads(out)["match"]
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "manifest_version": 1,
                "checkpoint": {
                    "session_id": "s",
                    "cutoff_seq": 3,
                    "repo_fp": {"complete": True},
                    "env_fp": "e",
                },
                "acceptance": {"contract_id": "c1"},
                "resource_envelope": {"max_total_tokens": 1000, "budget_approved_by": "owner"},
                "treatments": {"A": {}, "B": {}},
                "evaluator": {"contract_id": "c1"},
            }
        ),
        encoding="utf-8",
    )
    code, out, _ = cli_runner("experiment-validate", "--manifest", str(manifest))
    assert code == 0, out
    manifest.write_text("{}", encoding="utf-8")
    code, out, _ = cli_runner("experiment-validate", "--manifest", str(manifest))
    assert code == 1


def test_train_evaluate_shadow_roundtrip(cli_runner, data_dir):
    from tests.test_learning import _write_dataset  # reuse synthetic builder

    dataset = data_dir / "ds.jsonl"
    _write_dataset(dataset, n_groups=20)
    model = data_dir / "model.json"
    code, out, _ = cli_runner("train", "--dataset", str(dataset), "--out", str(model), "--json")
    assert code == 0, out
    code, out, _ = cli_runner(
        "evaluate", "--dataset", str(dataset), "--model", str(model), "--json"
    )
    assert code == 0, out
    assert "accuracy" in out or '"test"' in out
    code, out, _ = cli_runner(
        "import", "--session", "demo-loop", "--file", str(FIXTURES / "demo-loop.jsonl")
    )
    assert code == 0
    code, out, _ = cli_runner("shadow", "demo-loop", "--model", str(model), "--json")
    assert code == 0, out
    assert json.loads(out)["shadow_only"]


def test_reports_never_label_unresolved_successful(cli_runner):
    for fixture, session in (
        ("demo-loop.jsonl", "demo-loop"),
        ("demo-stale.jsonl", "demo-stale"),
        ("demo-budget.jsonl", "demo-budget"),
    ):
        code, _, _ = cli_runner("import", "--session", session, "--file", str(FIXTURES / fixture))
        assert code == 0
        code, out, _ = cli_runner("report", session, "--json")
        assert code == 0
        assert json.loads(out)["session"]["terminal_outcome"] != "verified_success"
