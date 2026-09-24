# Jev Governor

**Spend coding-agent inference where it helps. Verify what actually improved.**

Jev Governor is a proposed local-first companion for coding sessions. It observes evidence and usage, detects repeated unproductive work, and recommends whether to continue, diagnose, escalate, verify, or pause. The longer-term research goal is to learn these interventions from coding-session outcomes and total cost, without training the coding model itself.

## Status

**Documentation foundation only, prepared 2026-09-24.** There is no executable package, live-qualified integration, trained policy, or demonstrated saving in this commit. Commands described below and in the specifications are implementation targets, not commands that already work. Do not present this repository as a released product.

The first implementation assignment is [the Muse Spark testing-ready prompt](docs/prompts/muse-spark-testing-ready.md). Read [AGENTS.md](AGENTS.md) before changing the repository.

## The first useful product

A developer should be able to run a synthetic offline demonstration, inspect an explicitly selected local coding session, see a revision-bound requirements/evidence ledger, understand usage and unknown costs, and receive one concrete next-step recommendation with a short explanation. Advisory mode does not change the active coding agent.

A separately enabled Jev evaluator may add semantic features. Its absence must not prevent useful deterministic operation. Live Codex observation and any intervention require a version-specific capability check; a recommendation is not proof that a setting was applied.

The initial users are developers doing bounded repository bug fixes, CI repairs, and small refactors. Start with local Codex and a terminal interface, not a replacement IDE, hosted service, or general agent platform.

## Design commitments

- Evidence, model estimates, imported claims, and independent evaluations are distinct. A generated claim that tests passed is not a test result.
- Verification requirements and execution permissions stay outside the learned policy. Budget exhaustion is an unresolved outcome, never success.
- Account for all attempts and governor overhead. Preserve raw usage, estimated API-equivalent cost, actual billing/credits when observable, latency, and human intervention separately.
- Learning starts offline and in shadow mode. Synthetic learning demonstrations test the machinery; they do not establish coding efficacy.
- Normal development and CI are offline and require no credentials. Local session contents stay local unless the user explicitly enables a defined outbound data scope.

## Planned implementation surface

Prefer a small typed Python package, Python 3.12 or a supported compatible version selected and pinned during implementation, SQLite for local state, JSONL for interchange, and a thin CLI. Use the official Codex SDK or another documented interface only after probing the installed version. Avoid a second runtime unless an actual integration constraint justifies it.

Target CLI capabilities: `doctor`, `demo`, `import`, `inspect`, `recommend`, `report`, `feedback`, `export`, and a separately gated `jev-smoke`. Exact syntax belongs in the tested implementation README. Experimental training/evaluation commands must be clearly separate from ordinary session operation.

## API keys and live testing

Offline tests and the demo need **no API key**. Live Jev calls need a TypeSafe key from the [dashboard](https://console.typesafe.ai), supplied through `TYPESAFE_API_KEY`. See [integration instructions](docs/INTEGRATIONS.md) and the placeholder [.env.example](.env.example). Having a key is not permission to spend or upload code. Live calls also require explicit enablement, a bounded test plan, and an approved data scope.

Codex authentication is separate. Reuse the user's normal supported local login; do not collect credentials or silently switch from subscription authentication to API billing. Missing access is reported as unavailable, not a reason to block offline work.

## Reading order

| Document | Purpose |
| --- | --- |
| [AGENTS.md](AGENTS.md) | Engineering, safety, Git, and reporting rules |
| [Product](docs/PRODUCT.md) | First user experience and product boundaries |
| [Architecture](docs/ARCHITECTURE.md) | Components and integration control boundaries |
| [Data contracts](docs/DATA_CONTRACTS.md) | Evidence, usage, decisions, and trajectories |
| [Evaluation](docs/EVALUATION.md) | Acceptance tests and research methodology |
| [Roadmap](docs/ROADMAP.md) | Sequenced milestones and release gates |
| [Integrations](docs/INTEGRATIONS.md) | Jev and Codex setup and capability qualification |
| [Security](docs/SECURITY.md) | Threat boundaries, local data, and execution |
| [References](docs/REFERENCES.md) | Dated primary-source starting points |
| [Implementation prompt](docs/prompts/muse-spark-testing-ready.md) | Full Muse Spark session assignment |

## Research objective

Minimize total cost to reach independently verified acceptance, subject to a predeclared quality requirement relative to strong fixed and heuristic baselines. Measure verified success, total expenditure, time, regressions, and human intervention together. An apparent saving from repricing the same token counts under a different model is not an observed saving from executing that model.

The progression is deterministic baseline, learned outcome/cost prediction, supported controlled interventions, then conservative sequential policy learning if the evidence warrants it. Jev is an interchangeable feature provider, not the reward authority.

## Contributing

Inspect current branches and open PRs, work on an isolated branch, add behavior tests, and leave the PR open. Do not self-merge, publish packages, deploy services, change account billing, or run paid benchmark campaigns without explicit authorization. Preserve attribution and licenses when reusing external code. No third-party code is included in this documentation foundation.
