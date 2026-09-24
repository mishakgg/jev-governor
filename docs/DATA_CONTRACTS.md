# Data and evidence contracts

Status: design requirements. Implement concrete typed schemas and tests; this document is not a substitute for runtime validation.

## Event envelope

Every event should have schema_version, event_id, session_id, event_type, source, source_version, source_event_id where provided, observed_at, and provenance. Include source sequence and source timestamp when available; do not pretend wall-clock order from different processes establishes causality. Bound record size and string/collection lengths.

Session identity must include the explicitly selected workspace/repository identity, base revision, runtime and adapter versions, auth-mode label without secrets, and relevant policy/evaluator versions. Use local pseudonymous IDs in exports; do not assume hashing a path anonymizes its contents.

Distinguish synthetic fixture, imported claim, adapter-observed event, trusted check-runner record, human feedback, and independent evaluator result. An imported `trusted: true` field must not upgrade provenance. Only the trusted ingress path can establish its own origin.

Suggested event families: session started/ended, requirement proposed/accepted/updated, checkpoint observed, model request/usage, tool/check started/completed, patch observed, hypothesis/diagnostic recorded, recommendation issued, intervention requested/applied/failed/unknown, override/feedback, and evaluation completed/unavailable.

## Requirements and evidence

A requirement has a stable ID, text or a local reference, origin (user or inferred), scope/version, and an explicit acceptance mapping. Updates create a new version; model output cannot erase prior requirements.

A check record includes check ID, command recipe ID, executor identity, exit status, timeout/cancellation disposition, environment fingerprint, evaluated repository-state fingerprint, start/end times, and bounded artifact references. Protect runner configuration and acceptance definitions from the evaluated agent where independence is claimed.

Represent at least unknown, candidate, partially_verified, verified, failed, and blocked. Verification requires an applicable acceptance mapping and adequate fresh evidence. A successful process exit alone cannot prove every requirement.

A repository-state fingerprint covers the actual evaluated tree, including relevant uncommitted and untracked inputs under a declared policy. A commit SHA alone is insufficient for a dirty tree. If comprehensive fingerprinting is unavailable, downgrade freshness/completeness rather than claiming full coverage. Later relevant changes invalidate evidence until rerun or a sound explicit dependency rule establishes continued validity.

Evidence attachments are references with provenance and integrity metadata, not authority embedded in arbitrary text. Independent runner artifacts must not be read from agent-editable locations as though protected.

## Usage and accounting

For each billable or observed operation record provider, requested model, served model if exposed, effort if exposed, operation/attempt ID, usage scope, raw provider usage, normalized fields, timing, success/failure/cancellation, and pricing provenance.

The adapter must declare whether each usage event is a delta or cumulative snapshot and whether cached/reasoning fields are subsets or additional quantities. Compute deltas within a stable stream/epoch. Deduplicate exact events; do not add cumulative totals repeatedly. A counter reset, contradiction, or missing epoch is a diagnostic, not a negative refund.

Normalized fields may include input_tokens, cached_input_tokens, output_tokens, reasoning_output_tokens, total_tokens, completeness, source, and accounting_semantics_version. Unknown counts are null/unknown, not zero. In OpenAI Responses semantics, reasoning output is part of output usage; preserve provider-specific semantics for other adapters. See REFERENCES.md.

Track Jev usage and other governor costs separately and include them in totals. Failed attempts can still consume usage. Report known lower-bound totals and missing portions when completion is partial; do not silently exclude these sessions from comparisons.

Economic fields distinguish actual billed currency, observed credits, documented-rate estimates, and unknown. Pricing needs currency, rate version/effective date, model/service tier, caching rules, and source. Do not mix credit balances with dollar estimates or invent a subscription-token conversion. Do not pin public prices as timeless constants.

Per-requirement attribution is estimated unless a direct scoped operation supports it. Permit multi-requirement and shared overhead entries with a declared allocation rule that does not double-count the session total.

## Decision record

Record decision_id, session/checkpoint IDs, observation cutoff, feature schema and values, feature provenance, policy version, permitted recipes, capability snapshot, remaining observed budget and reservations, selected recipe, intended configuration, estimated cost and uncertainty when available, and rationale codes/evidence references.

Keep recommendation, requested action, acknowledged action, and observed application distinct. Record abstention, override, and actual executed action. A timeout after sending a control command may leave the outcome unknown. Do not treat a disconnected observer as proof that the underlying work stopped.

Log the behavior-policy selection probability only if actually known. For a deterministic policy its chosen action may have probability one, but that does not provide support for alternatives. Jev answer probabilities describe semantic choices, not the probability with which the experiment selected an intervention. User overrides require separate selection/execution provenance.

## Terminal outcome and feedback

Use explicit categories: verified_success, failed_evaluation, unresolved_budget, blocked, cancelled, evaluation_unavailable, and incomplete. Preserve evaluator identity/version, evaluated fingerprint, requirement coverage, and acceptance artifacts. Human acceptance/rejection and intervention count are separate fields; they do not rewrite independent results.

Store censoring or missing terminal observations. Unknown is not success, and missing independent evaluation should not be silently converted to failure labels for training. Report data availability and make exclusions explicit.

## Dataset and artifact manifests

Exports include schema versions, source/session counts, date range, privacy scope, provenance category, action coverage, usage completeness, split grouping keys, and checksums. Avoid raw private text by default. Dataset labels and future observations live outside the decision-time feature payload.

Training artifacts include algorithm identity (rules, supervised prediction, bandit, or RL), feature/action versions, seed, training-data manifest hash, split IDs, validation results, support/abstention policy, and limitations. Do not load pickle or other executable serialization from untrusted exports.

Paired-continuation manifests identify the common checkpoint, repository and environment snapshots, branch treatments, randomization and seed, model/runtime versions, evaluator contract, resource envelope, and all incurred costs. Replay-only artifacts must say that no alternative agent execution occurred.

## Mandatory invariants

Test duplicate ingestion, repeated cumulative snapshots, missing final usage, cached/reasoning subsets, stream resets, malformed/oversized events, unsupported schema versions, cross-session mixups, stale check results, forged trust labels, train/test leakage, override attribution, and idempotent restart. Reports must surface uncertainty instead of rounding it away.
