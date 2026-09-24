# Roadmap and acceptance gates

All milestones below are planned. Mark a gate complete only with commands, versions, artifacts, and outcomes from actual execution.

## M0 — Executable offline vertical slice

Build package/CLI, typed schemas, fixture adapter, SQLite/event persistence, evidence freshness, usage normalization, deterministic recommendations, and a readable completion report. Include one stalled synthetic session, one productive investigation, and one stale-verification case. No credentials or provider network.

Exit: fresh install and documented demo/import/inspect/recommend/report/export flow passes; malformed/duplicate/partial records and usage invariants are tested. No stubs masquerading as live integration. This is the first implementation priority.

## M1 — Test-ready local advisory alpha

Add a narrow official/documented Codex integration with a capability probe and separate live-qualification checklist. Add an optional Jev feature provider with bounded retries, deadlines, input scope, and a synthetic live-smoke command. Keep default mode advisory and Jev disabled.

Add feedback, explicit-session selection, privacy-safe exports, retention/deletion, packaging smoke, and offline CI. Document the actually tested operating system/runtime and limits on observation, model/effort control, interruption, and usage.

Exit: all offline alpha acceptance cases pass; a real adapter path exists with versioned contract tests; missing native access is accurately reported. Live qualification may remain blocked by unavailable credentials/authorization, but must never be falsely marked complete.

## M2 — Learning-ready and small shadow predictor

Finalize episode/dataset manifests and grouped train/validation/test splits. Implement a small CPU-friendly outcome/cost predictor and a safe versioned artifact format. Exercise train -> held-out evaluation -> shadow recommendation on labeled fixtures. Store observed outcomes without inventing counterfactuals. Add action-support checks and abstention.

Exit: numeric parameters actually fit data, held-out evaluation is reproducible, leakage/coverage failures are caught, and synthetic results are prominently labeled. The default governor remains deterministic. This milestone is a real supervised prototype, not an assertion that RL is solved.

## M3 — Controlled continuation pilot

Prepare a small owned/licensed bug-fix task set and protected acceptance runner. Execute paired baseline/treatment continuations only under an explicit resource and data authorization. Validate environment equivalence, count all experiment costs, and compare to strong fixed and heuristic baselines.

Exit: report denominators, uncertainty, quality/cost/intervention results, governor overhead, failures, and limitations. A negative result is publishable and useful. Do not set a mandatory saving percentage that invites gaming.

## M4 — Sequential policy learning

Only after useful alternative actions and delayed effects are represented in data, evaluate a conservative sequential learner. Keep coding models frozen. Compare to the existing predictor and rules, use support constraints, and retain a baseline fallback.

Exit: a justified held-out result and a reviewed promotion/rollback procedure. Hierarchical control, context strategies, and broader harness support are later experiments, not prerequisites for the first useful tool.

## Scope of the first Muse Spark session

Aim to complete M0 and the implementation/testing parts of M1, then the small M2 learning workflow if the core is sound. Do not claim live M1 qualification without running it. Do not launch M3 paid experiments or M4 production learning merely because an API key is present.

Prefer a working narrow slice over a wide skeleton. First finish ledger, accounting, recommendations, reports, and a narrow adapter before optional polish or sophisticated training. Continue useful offline work when external access is absent. Leave explicit acceptance evidence and remaining gates in the PR.

## Status artifact to maintain during implementation

Create a concise testing-ready checklist recording each requirement, implementation path, test command, outcome, and remaining limitation. Keep an implementation log only for material decisions or blockers; do not generate large diary files. Keep README status current, including exactly what a developer can run today.
