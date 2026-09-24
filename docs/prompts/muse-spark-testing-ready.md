# Muse Spark 1.3 Max — Build Jev Governor to a testing-ready alpha

You are the lead implementation engineer and research engineer for https://github.com/mishakgg/jev-governor. Turn the project brief into a working, locally testable developer tool. This is an implementation assignment, not another brainstorming session, literature survey, or documentation-only PR.

## 1. Mission

Build a local-first coding-session companion that observes evidence and inference usage, detects unproductive loops, and recommends whether to continue, use a cheaper configuration, escalate diagnosis, verify, or pause/replan.

The research direction is to learn a small controller from coding-session results and total expenditure while keeping the coding models frozen. The first usable product must work before that learner is good. Jev is an optional semantic feature provider, not the policy's sole implementation and never the authority that declares success.

The intended first user runs bounded local Codex bug fixes, CI repairs, and small refactors. Deliver a CLI and reproducible offline demo, not an IDE replacement or hosted platform.

## 2. Establish the correct base

Inspect repository status, remote refs, current implementation, and open PRs. Record the full base SHA and preserve existing work.

The documentation foundation was prepared on bootstrap/project-brief. If its PR remains unmerged, branch from its current head and open a dependent implementation PR targeting that branch. If already merged, use current origin/main. Do not duplicate the foundation, self-merge it, force-push, or overwrite another agent's branch. Use an isolated branch such as spark/testing-ready-alpha.

Read AGENTS.md and all linked product, architecture, data, evaluation, roadmap, integration, and security documents. Treat described commands as targets until implemented. Recheck current official SDK/API documentation where needed; do not blindly trust an old model name or undocumented transcript shape.

Create a short acceptance checklist with implementation and evidence columns, then start building. Make reversible design decisions yourself and document material ones. Do not stop at a plan or ask the owner to choose routine libraries.

## 3. Deliver a coherent offline vertical slice first

Prefer one typed Python package with a thin CLI, SQLite persistence, versioned JSONL interchange, pytest and lightweight static checks. Choose and pin a supported runtime and dependencies. Keep research dependencies optional. Avoid unnecessary services, a web frontend, a vector database, a GPU stack, or a second language/runtime.

Implement a one-command clearly synthetic demo and a usable workflow covering installation/help, doctor, import, inspect, recommend, report, feedback, export, and local data deletion/retention. Exact syntax is yours to choose, but publish only commands you have actually tested.

The demo must show a repeated-failure loop, a productive expensive investigation, and a stale passing check after a patch change. It must work without Jev, Codex, credentials, or provider network access. This is a mechanics demonstration, not measured real-world savings.

## 4. Evidence ledger, not invented progress

Represent explicit and inferred requirements separately. Track unknown, candidate, partially verified, verified, failed, and blocked states with evidence references.

Bind check records to the actual evaluated repository state, including relevant dirty/untracked inputs, the environment, and the acceptance contract. A relevant subsequent patch makes old evidence stale. Missing or incomplete fingerprints must reduce assurance, not create false freshness.

Separate agent claims, imported trace claims, adapter observations, trusted command-runner results, independent evaluator results, and human feedback. An imported trusted=true field, a statement that tests passed, or a model's confidence cannot upgrade evidence. A process exit code alone does not prove every requirement.

Keep mandatory verification outside the learned policy. Do not let the agent rewrite requirements, the acceptance mapping, or the verification floor to finish cheaply. Distinguish verified success, failed evaluation, unresolved budget, blocked work, cancellation, evaluation unavailable, and incomplete sessions.

## 5. Correct accounting and persistence

Record raw provider usage and normalize it with source-specific semantics. Distinguish per-operation deltas from cumulative snapshots; deduplicate reconnect/import events and handle stream epochs/resets. Preserve missing usage as unknown.

Do not add cached input or reasoning output twice when they are subsets. Keep actual billing, observed credits, API-equivalent estimates, measured tokens, elapsed time, tool compute, and human intervention separate. Include failed attempts, retries, Jev usage, and governor overhead. Report price versions and incomplete coverage.

Per-requirement usage attribution is an estimate unless directly scoped. Include shared investigation/overhead and avoid double counting. Rebuild reports deterministically from stored events. Test restart, malformed/oversized input, partial traces, cross-session confusion, and idempotent reimport.

Do not claim a hard spend cap where an adapter only checks between turns and observes usage afterward. Reservations, predictions, and actual usage are different quantities.

## 6. Small policy, useful recommendations

Start with deterministic recipes: CONTINUE, ECONOMICAL_CONTINUE, ESCALATE_DIAGNOSIS, VERIFY_NOW, and PAUSE_REPLAN. Keep model/effort mappings configurable and validated against observed capabilities. Do not hard-code a fictional fixed model catalogue.

Recommendations need a concise reason, evidence references, uncertainty/abstention, and advisory/applied status. Use repeated failures, changed hypotheses, new diagnostics, remaining checks, usage, and observation quality. A costly investigation with no immediate passing test must not automatically be labeled waste.

Default to advisory mode. Selecting a recipe is not execution permission. Registered checks use approved argument arrays, not shell generated from Jev or transcript text. A test executes repository code; a worktree is not a sandbox. Never widen approvals, filesystem access, network access, or user budgets.

Suppress repeated unchanged advice. On unavailable Jev, fall back to the baseline without bypassing a pause, exhausted budget, or permission gate. Do not implement arbitrary subagent spawning, automatic context truncation, or autonomous changes to important live repositories.

## 7. Implement a real, narrow Codex integration

Probe the currently available official/documented local interfaces and choose the smallest reliable path. Current reference docs include a Python SDK, but verify its actual installed contract and pin supported versions.

Implement a versioned adapter and doctor report for runtime presence, version, platform, non-secret auth status where supported, explicit session selection, event types, usage semantics, and control capabilities. Separate documented, observed, unavailable, unsupported, and untested.

Establish whether controls apply to user turns, segments, or internal model calls. Do not advertise per-generation routing from turn-level controls. Record requested, acknowledged, and actually observed configurations separately; unavailable served-model information is unknown.

Use normal supported local Codex authentication. Do not collect/copy auth files, switch billing methods, log credentials, or auto-approve tools. Missing runtime/login must not block offline features. Provide contract tests and a bounded opt-in live-qualification procedure; mocks alone do not establish live support.

For any implemented control, guard duplicate admission and reconcile an uncertain acknowledgment before retrying. Local disconnection is not confirmed cancellation of durable/remote work. A read-only advisory alpha is preferable to fake automation.

## 8. Optional Jev integration and key handling

Use TYPESAFE_API_KEY through a local secret mechanism. Live Jev calls also require explicit enablement, an approved outbound payload scope, and a bounded attempt/deadline plan. Credential presence alone is not authorization. Do not ask for a key in chat or put one in Git.

Follow the current official TypeSafe API/SDK. Configure/pin the model for experiments and record the actual returned model, rubric version, usage, latency, and attempts. Send small structured observations by default, not entire transcripts or source files. Jev features may estimate failure pattern or hypothesis repetition; they cannot certify task success.

Implement strict typed-response validation, missing/invalid option handling, timeout/cancellation, 401/422 fail-fast, bounded transient retries including rate limits/overload, and deterministic fallback. Use one total retry budget across SDK and wrapper; never hide retry spend.

Provide jev-smoke using one small synthetic request with an explicit live flag and attempt cap. With no key or authorization, leave it not run and complete the rest. Normal tests must block provider traffic even when credentials exist in the environment.

## 9. Make learning real but proportionate

Collect decision-time observations, eligible recipes, selected/requested/applied actions, policy and schema versions, user overrides, full costs, terminal evaluation, and censoring/missing labels. Store genuine behavior propensities only when known; Jev answer probabilities are not action-selection propensities.

After the core works, implement a small CPU-friendly offline train/evaluate path for an outcome/cost predictor and shadow recommendations. Fit actual numeric parameters from eligible examples, save a safe versioned artifact, and evaluate on grouped held-out data. Keep future observations and evaluation labels out of input features. Add tests for leakage, incompatible artifacts, inadequate action coverage, and abstention.

Synthetic training proves the pipeline, not real coding effectiveness. Call a supervised predictor supervised, not RL. Do not manufacture outcomes for actions never taken or claim that log replay proves counterfactual savings. Keep default execution deterministic and learned recommendations shadow-only.

Prepare manifests and a small replay/experiment interface for later paired checkpoint continuations. Validate the common state, environment, acceptance contract, resource envelope, and complete cost accounting. Do not launch paid continuation experiments without a separately approved budget. Full sequential RL, hierarchical control, and model training infrastructure are later work justified by collected evidence, not prerequisites for this alpha.

## 10. Validation and finish criteria

Run the offline acceptance matrix in docs/EVALUATION.md, unit and integration tests, static checks, clean-install/package smoke, and the complete CLI demo/import/report/export path with credentials unset and provider network blocked. Add offline CI without secret-dependent tests or automatic publishing.

Specifically test forged trust/success claims, stale checks, duplicate usage, cached/reasoning subsets, missing terminal usage, malformed inputs, budget exhaustion, Jev errors/cancellation, storage restart, safe export/deletion, train/test leakage, and unsupported-action fallback. Confirm that reports never label unresolved work successful.

Aim to finish M0 and the implementation/testing parts of M1, then the small M2 learning workflow once the core is sound. Do not trade a working narrow tool for a wide placeholder architecture. Missing external access blocks only the relevant live qualification, not useful offline work.

Keep the owner informed at material milestones. Do not repeatedly ask for confirmation for safe local implementation. Stop for actual missing authorization involving paid calls, private-data egress, destructive operations, deployment, or account/billing changes; continue independent offline work.

Leave an open PR and a precise final report: base/final SHAs, changed components, tested install/run commands, acceptance outcomes, actual platform/runtime versions, remaining limitations, and exact live-test steps. Report offline-test-ready, live-Codex-qualified, live-Jev-qualified, and research-efficacy-demonstrated separately. No unmeasured savings claim, simulated live result, or invented trained-policy success.

Do not merge, deploy, publish, force-push, disable checks, buy credits, or launch an unbounded experiment. The deliverable is a working testable alpha plus honest evidence and a clear next research experiment.
