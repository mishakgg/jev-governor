# Product brief

Status: proposed contract for the first implementation; no implementation is claimed by this file.

## Problem and promise

Developers can see an agent spending tokens and time without knowing whether the next attempt is likely to help. The useful intervention is often not another model: it is a focused diagnostic, an explicit verification step, or an honest pause with a preserved patch.

The first product should help a developer answer: What is done? What is actually verified? What is unresolved? Where did usage go? What should happen next, and why?

Position it as a session companion, not an autonomous project manager. Do not promise universal savings, flawless task completion, or a new coding model.

## Initial user and task scope

Target individual developers or small teams repeatedly running local Codex on bounded bug fixes, failing CI checks, and small refactors in repositories with runnable checks. The user selects the repository and session explicitly. Do not scan all local sessions or accounts automatically.

Begin with a terminal report and advisory recommendations. Native Windows, WSL, Linux, and macOS support must be described according to actual tests; WSL support is not native Windows support. No platform claim based only on a mocked adapter.

## First-run experience

The offline demo is one command after documented installation. It uses clearly synthetic fixtures and explains both a stalled task and a healthy expensive investigation. No key, account, background service, upload, or coding-model call is required.

For a selected real session, doctor explains which runtime, version, auth mode, events, usage fields, and intervention controls are available. The user sees scope and privacy information before enabling observation. If only an imported trace is available, the report says imported/unverified rather than pretending to observe live execution.

## Evidence-centered session report

Show requirements as unknown, candidate, partially verified, verified, failed, or blocked, with provenance and check freshness. Preserve a shared investigation/overhead category instead of falsely assigning all usage to individual requirements. Estimated attribution must be labeled and must reconcile with session totals.

Show raw measured token usage, governor overhead, elapsed time, available pricing estimates and their versions, and unknown portions. Show human overrides and rescue attempts separately from independent success.

A recommendation should include one action, a short reason, supporting event/check references, uncertainty or abstention, and whether it is only advisory or actually applied. Suppress repeated unchanged advice; the tool should not become another noisy agent.

Illustrative output, not an algorithmic rule:

```text
Possible repeated-failure loop
The same assertion failed after two distinct patches.
No new diagnostic result has been recorded since the last attempt.
Suggested next step: run the approved isolated diagnostic.
Mode: advisory; no command executed; no model setting changed.
```

A repeated assertion alone is insufficient: account for changed inputs, meaningful hypotheses, flaky behavior, and environmental failures.

## Intervention recipes

| Recipe | Meaning | Limits |
| --- | --- | --- |
| CONTINUE | Keep the current configuration for the next bounded segment | Still subject to user budget and permission gates |
| ECONOMICAL_CONTINUE | Recommend an approved cheaper configuration | Never assumes availability or equivalent quality |
| ESCALATE_DIAGNOSIS | Recommend stronger focused investigation | No arbitrary subagent or permission expansion |
| VERIFY_NOW | Recommend a registered diagnostic or acceptance check | Does not invent shell commands or remove required checks |
| PAUSE_REPLAN | Preserve state and explain the blocker | Does not mark unresolved work successful |

Advisory mode is the alpha default. An action's execution recipe is separate from the policy selecting its ID. FINISH is an evidence-derived terminal outcome, not a policy shortcut around verification.

## Quality and learning

The research target is lower total cost at an acceptable verified-success rate, not cheap abandonment. Report success, cost, latency, regressions, and human intervention jointly. Budget profiles may eventually condition a policy, but no profile can waive mandatory correctness or permission checks.

The initial learned artifact should be a small offline outcome/cost model used in shadow mode, with support checks and fallback. RL remains a later candidate for long-horizon decisions, not a marketing label applied to rules or supervised learning.

## Out of scope for the first alpha

No coding-model fine-tuning, Jev weight training, full context rewriting, silent model changes, automatic permission grants, arbitrary shell execution, autonomous subagent creation, production-repository exploration, multi-tenant hosting, billing, public package release, or editor extension. No need to support every coding harness at once.

## Product validation

Ask pilot users to run a bounded task and note whether advice was useful, ignored, or harmful, along with effort spent supervising the governor. Keep feedback and independently checked outcomes separate. Installation friction and repeated nuisance recommendations matter even when a benchmark score improves.
