# Evaluation and research plan

Status: planned protocol. No experiment or performance result is claimed here.

## Separate four readiness labels

| Label | Required evidence |
| --- | --- |
| Offline-test-ready | Fresh install, deterministic demo, ledger/accounting/CLI tests, local report/export workflow pass with provider network blocked |
| Live-Codex-qualified | Named runtime/adapter/platform actually observed a selected session with documented usage and control limits |
| Live-Jev-qualified | Explicitly authorized bounded API smoke succeeds with synthetic state; request/response schema and usage validated |
| Research-efficacy-demonstrated | Held-out controlled executions meet a predeclared success-quality criterion and show measured benefit over strong baselines |

Mocks establish contract behavior, not live qualification. Live API success establishes connectivity, not better decisions. None of the first three labels establishes cost savings.

## First-session acceptance tests

1. One-command offline demo uses clearly synthetic traces and produces requirements, fresh/stale checks, known/unknown usage, recommendations, and a completion report without credentials.
2. A repeated-failure fixture recommends diagnosis or pause when appropriate; a productive expensive investigation is not penalized merely because it has no immediate passing test.
3. A fully checked patch reaches verified completion under the fixture's declared evaluator; budget exhaustion, interrupted evaluation, and missing evidence do not.
4. A patch change makes prior relevant checks stale. Forged success/trust labels in repository text or imported logs cannot upgrade authority.
5. Reimport and reconnect do not duplicate events, usage, or applied actions. Cumulative snapshots and cache/reasoning subsets reconcile correctly. Unknown usage remains visible.
6. Jev disabled, absent key, invalid response, timeout, cancellation, 401, 422, 429, 529, and server failure all have deterministic bounded behavior. No permission or budget widening occurs on fallback.
7. CLI supports bounded input, readable errors, JSON output for scripts, safe paths, retention/deletion, and a clean install/package smoke. Reports contain no secret or raw transcript by default.
8. A narrow real Codex adapter has versioned contract tests and a doctor report. Missing runtime/login yields a useful diagnostic while offline features still work.
9. A small offline train/evaluate workflow fits a real numeric predictor from eligible synthetic or consented examples, emits a versioned artifact, and evaluates on held-out grouped data. This is explicitly supervised machinery, not demonstrated RL or real-world savings.
10. Inadequate action coverage, missing labels, or incompatible schemas lead to abstention/refusal to promote, not fabricated estimates for unsupported actions.

The developer may implement a simple regularized outcome/cost predictor, with an established lightweight library as an optional research extra. Avoid writing a sprawling ML framework. Policy selection remains shadow-only until its evidence gate is met.

## Metrics

Always report verified success, regressions/requirement violations, total usage/cost including failures and governor overhead, elapsed time, and human intervention together. Include distributions/tail behavior and denominators, not only means.

Cost per verified success = total cost of all included attempts / count of verified successes. With zero successes it is undefined, not zero. When monetary accounting is incomplete, disclose coverage and report measured token/time components separately. Do not silently drop costly failures or sessions with missing measurements.

Track observation overhead, Jev overhead, recommendation frequency, repeated nuisance alerts, accepted/overridden recommendations, and installation friction. Distinguish an intervention accepted by a developer from an intervention that causally improved the result.

## Baselines and task set

Compare a strong fixed configuration, an economical fixed configuration, a simple deterministic escalation/verification rule, and the candidate policy. Use the same original task, repository state, acceptance contract, tools, and declared resource envelope.

Begin with small redistributable or owned tasks: localized bug, repeated failed patch, wrong hypothesis, flaky/environmental failure, productive high-cost investigation, and apparent completion that fails independent regression checks. Synthetic traces validate mechanics; real coding execution is a separate dataset category. Respect repository/data licenses and opt-in data use.

Split by repository/task family and session, with time-aware holdouts when appropriate. Never randomly divide near-duplicate turns from one episode between training and testing. Keep duplicate detection, feature selection, calibration, and hyperparameter selection within training/validation boundaries. Do not repeatedly tune against the final holdout.

## Research objective

Minimize expected full-session cost subject to a predeclared verified-success requirement relative to baseline and separate regression/intervention limits. Choose the non-inferiority margin and analysis protocol before observing the final results. This is an aggregate empirical target, not a per-task guarantee.

Use paired analyses and uncertainty intervals appropriate for repeated runs and clustered tasks. A small pilot with no statistically significant quality difference does not prove equal quality. Publish task counts, variation, missing data, exclusions, and compute used. Avoid arbitrary impressive savings targets.

## Counterfactuals and controlled continuations

At selected checkpoints, execute baseline and treatment continuations from equivalent states. Preserve conversation state where supported and separately snapshot the filesystem, relevant untracked files, dependencies, fixtures, environment, databases, and processes, or restrict the benchmark to eliminate those external dependencies.

A Git branch or conversation fork is not a full snapshot. Separate credentials and writable state; do not run competing branches against one live database. Randomize order where feasible, record caches and external-service effects, and count both branches' inference and compute costs. These are new executions, not free replay.

The initial experiment runner can validate manifests, replay fixtures, and refuse unsafe/incomplete continuation setups. Implement paid real-agent branching only after a bounded owner-approved experiment exists.

## Learning stages

Stage A: deterministic policy and instrumentation. Stage B: supervised outcome/cost prediction with calibration and support checks. Stage C: limited controlled exploration among safe eligible actions on disposable tasks, with true behavior propensities recorded. Stage D: conservative sequential RL when meaningful sequential feedback and supported alternatives exist.

Do not infer the value of an untried action from an ordinary log as though observed. Hard tasks may have been preferentially routed to expensive configurations. Shadow recommendations alone do not measure their causal benefit. Off-policy estimates require assumptions, overlap, and uncertainty reporting; a library does not remove those requirements.

Use outcome-minus-cost or constrained formulations only with explicit scale and quality gates. Intermediate progress-per-token is a diagnostic, not the sole reward. Early costly diagnosis may help later, and cheap abandonment must not win. A simulator-only RL baseline may be added later as labeled research, not shipped as a validated controller.

## Jev ablation and promotion

Compare deterministic features alone with deterministic plus Jev features. Include Jev latency, usage, and missing-response behavior. Freeze feature rubrics/model versions within a comparison. Only keep an added feature provider if its measured benefit justifies its overhead and privacy cost.

Promote a policy only after held-out evidence, adequate action coverage, a compatibility check, an explicit approval, and a rollback path. Never explore on important live work by default. Failing to beat the heuristic is a valid result; preserve the useful non-learning product.
