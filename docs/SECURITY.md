# Security and privacy boundaries

This document specifies design requirements, not a security certification.

## Trust model

The coding agent's messages, target repository, tool output text, imported traces, semantic model answers, and model artifacts are potentially untrusted. The governor's trusted configuration defines permissions, budgets, eligible recipes, data-sharing scope, and evaluator contracts. External content cannot rewrite that configuration.

An event signed or stored by the local ingestion path can establish origin/integrity within its stated boundary; it does not prove that its textual content is true. Do not accept caller-supplied trust labels as authority.

## Threats and required behavior

| Threat | Required response |
| --- | --- |
| Prompt injection tells governor to mark complete or run a command | Treat as content; fixed action and verification gates remain unchanged |
| Agent edits tests or reports fabricated successful output | Record evidence provenance; protected external evaluation required for independent acceptance |
| Transcript says a check was run against the current patch | Require trusted execution identity and state freshness; imported claim cannot self-upgrade |
| Path traversal, symlink tricks, or malicious command arguments | Validate paths and boundaries; use registered recipes and subprocess argument arrays |
| Reconnect repeats a usage or action event | Idempotent ingestion; no duplicate cost or side effects |
| Jev outage or malformed choice | Bounded failure and deterministic fallback without bypassing a pause/budget gate |
| Credential in source text or an error response | Minimize collection; redact diagnostics; do not persist or export secret-bearing payloads |
| Malicious training artifact | Schema-validated safe numeric/data format, no executable deserialization |
| Budget estimate is stale or unknown | Report uncertainty; do not claim an enforceable spend guarantee |

## Local data

Select sessions explicitly. No automatic global transcript discovery, home-directory scan, analytics upload, or shared training collection. Store local state outside target-agent writable paths when possible. Use appropriate local permissions and document platform limits. Same-user processes may still read each other's data; do not market this as hostile-process isolation.

Default exports contain structured minimal observations, not raw prompts, source files, terminal dumps, or auth details. Raw diagnostic retention requires opt-in, a bounded size and retention period, and a clear delete operation. Derived features can still be sensitive. Hashing is not anonymization, and regex redaction cannot guarantee safety of arbitrary text.

Deletion removes the selected local records and associated owned artifacts only. It does not promise deletion of provider-side data or already exported copies. Prevent traversal and accidental deletion of user work.

## Command execution and evaluation

A test command executes repository code. Approved command names or a disposable Git worktree do not make that code safe. Use a properly scoped existing sandbox/container for untrusted targets; do not implement an ad hoc shell jail. Never pass Jev keys or unrelated credentials to evaluated task subprocesses. Restrict their filesystem, network, and writable state as the environment allows.

Fixture acceptance tests demonstrate software behavior but are not hidden independent benchmarks merely because they live under tests/. Independent research evaluation needs an agent-inaccessible contract, runner, result channel, and suitable execution isolation. If that isolation is absent, downgrade the claim instead of renaming it independent.

## Failure and recovery

Advisory mode never changes runtime settings. For any later control, persist a decision/request identity before execution, distinguish acknowledgment from confirmed application, and reconcile unknown outcomes before retrying. Cancellation signals are not proof all remote work stopped. Preserve the user's patch and session state when pausing.

Jev feature extraction failure should not break ordinary inspection/reporting. Storage corruption and dropped observations must remain visible as incomplete evidence; they cannot silently produce a success verdict or trustworthy total.

## Secrets and live tests

TYPESAFE_API_KEY is supplied through a local secret mechanism and is never committed. Exclude auth caches, .env files, transcripts, local databases, and training exports from Git. Do not inspect existing secret values to prove they exist. Live smoke tests use synthetic content, explicit authorization, bounded attempts, and no raw credential-bearing logs.

A credential is not permission to spend. Do not buy credits, change billing, upload private repository content, or launch benchmark campaigns without specific owner authorization.
