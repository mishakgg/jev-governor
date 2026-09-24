# Testing-ready alpha: acceptance checklist

Base: `bootstrap/project-brief` at `5e025beffe9bb5923fa5ffc7a39ef4bbb7d076ce`.
Branch: `spark/testing-ready-alpha`. Status labels (per docs/EVALUATION.md) are
decided independently at the bottom; no label is claimed from a weaker one.

## Offline acceptance matrix (docs/EVALUATION.md items 1-10)

| # | Requirement | Implementation | Evidence | Status |
| --- | --- | --- | --- | --- |
| 1 | One-command synthetic offline demo: requirements, fresh/stale checks, known/unknown usage, recommendations, completion report, no credentials | `src/jev_governor/demo.py`, fixtures `demo-*.jsonl`, `jev-gov demo` | `tests/test_flows.py::test_demo_matches_expected`; manual `demo` run | pass |
| 2 | Repeated-failure fixture recommends diagnosis/pause; productive expensive investigation not penalized | `policy.py` rules 2/5, `features.py` loop/productive signals | `test_policy.py` (loop, productive), demo-loop/demo-productive | pass |
| 3 | Fully checked patch verifies under declared evaluator; budget/interruption/missing evidence do not | `demo.py::run_verify_flow` (trusted run + labeled demo evaluation); `evidence.derive_terminal_outcome` | `demo-verify` → verified_success; `test_evidence.py::test_terminal_outcomes_never_invent_success`; demo-budget → unresolved_budget | pass |
| 4 | Patch change stales prior checks; forged success/trust cannot upgrade authority | `evidence.check_freshness`, import provenance stripping in `ingest.py` | demo-stale → VERIFY_NOW; `test_evidence.py` stale tests; `test_ingest.py::test_forged_trust_stripped_and_never_verified` | pass |
| 5 | Reimport/reconnect idempotent; cumulative + subset reconciliation; unknown visible | event_id dedup, `accounting.apply_to_totals` stream/epoch handling | `test_ingest.py` idempotency; `test_accounting.py` cumulative/reset/subset/unknown tests | pass |
| 6 | Jev disabled/no-key/invalid/timeout/cancel/401/422/429/529/server all bounded; no gate bypass on fallback | `jev.py` single retry budget, fail-fast, `FakeTransport` tests; recommend falls back to baseline | `test_jev.py` (12 cases); `test_flows.py::test_jev_smoke_defaults_to_not_run` | pass |
| 7 | CLI: bounded input, readable errors, JSON output, safe paths, retention/deletion, install smoke, no secrets/raw by default | `cli.py` (+shared --json/--data-dir), `export.py` redaction, `checks.py` path confinement | `test_flows.py` full workflow; `test_persistence.py`; clean-install smoke 2026-09-24 | pass |
| 8 | Narrow real Codex adapter: versioned contract tests + doctor; missing runtime/login diagnosed, offline intact | `codex_adapter.py` probe + rollout import, `codex-qualify` dry-run/live | `test_codex_adapter.py`; `doctor` on codex-cli 0.146.0; probe-missing test | pass |
| 9 | Small offline train/evaluate: real fitted parameters, versioned artifact, grouped held-out eval; labeled supervised | `learning.py` stdlib L2-logistic + ridge, JSON artifact, `train`/`evaluate`/`shadow` | `test_learning.py`; `test_flows.py::test_train_evaluate_shadow_roundtrip` | pass |
| 10 | Inadequate coverage/missing labels/incompatible schemas abstain or refuse; no fabricated estimates | support thresholds, censored outcomes, `check_artifact` | `test_learning.py` abstention/coverage/leakage tests; policy unsupported-fallback test | pass |

## Mandatory invariants (docs/DATA_CONTRACTS.md)

Duplicate ingestion, repeated cumulative snapshots, missing final usage,
cached/reasoning subsets, stream resets, malformed/oversized events,
unsupported schema versions, cross-session rejection, stale checks, forged
trust, train/test leakage (grouped split + denylist), override separation
(feedback vs evaluation), idempotent restart: each has at least one test in
`tests/test_{ingest,accounting,evidence,learning,persistence,flows}.py`.
Suite: 76 tests, all passing on Python 3.12 (venv) and 3.14 (clean install).

## Readiness labels

| Label | Verdict | Basis |
| --- | --- | --- |
| offline-test-ready | READY (this branch) | 76 tests + lint + demo + clean-install smoke pass; CI added (runs on push) |
| live-Codex-qualified | NOT RUN | `codex-qualify --run` implemented with dry-run default; no live run performed (would spend inference; needs explicit approval) |
| live-Jev-qualified | NOT RUN | `jev-smoke --live` implemented; no key/authorization, no live call made |
| research-efficacy-demonstrated | NOT CLAIMED | synthetic fits prove pipeline only; no controlled coding experiment run |

## Remaining limitations

- Live Codex observation (`exec --json` event shapes) and turn-level control are documented/untested; rollout import covers only the surveyed vocabulary.
- No per-generation routing, no auto-apply, no context rewriting, no subagent spawning (by design).
- Pricing table covers only `typesafe/jev-1.13.0` (dated 2026-09-24); Codex/subscription spend is measured-tokens-only.
- Windows tested; Linux/macOS rely on CI matrix (unobserved locally).
