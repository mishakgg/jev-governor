# Architecture

Status: implementation target, not an inventory of existing modules.

## Minimal pipeline

```text
selected local Codex session / explicit imported fixture
    -> versioned adapter
    -> validated events and usage normalization
    -> local evidence ledger + SQLite event store
    -> deterministic features
    -> optional bounded Jev features
    -> policy recommendation
    -> fixed permission / capability / budget gate
    -> advisory report (default)
       OR separately approved supported action
    -> subsequent events and independent evaluation
    -> export / offline training / comparison report
```

Use a small Python package with clear modules rather than separate services. A reasonable layout is adapters/, accounting/, evidence/, policies/, storage/, evaluation/, cli/, with research extras kept optional. Favor simple stable APIs over speculative plugin frameworks.

## Adapter contract

An adapter reports runtime name/version, connection identity, capability status and evidence, and supported event semantics. Capabilities are not booleans inferred from product branding: use supported, unsupported, unavailable, and untested, with documented versus locally observed evidence.

The initial Codex adapter must support explicit-session observation or a supported programmatic launch. Identify the actual checkpoint granularity: a user turn, an agent segment, or an internal generation. Never label turn-level control as per-generation routing without observing it.

For any control, separate requested configuration from accepted configuration and actually observed model/effort. If the served model is not exposed, record unknown. A prompt requesting a model change is not an adapter control.

Avoid unstable undocumented transcript scraping as the only real integration. A versioned import adapter is acceptable for compatibility, but imported records carry limited provenance. Capability probing must never print auth contents or trigger inference just to report a version.

## State and storage

Use append-only logical events with immutable IDs and a local transaction boundary for ingestion, usage updates, and derived state. SQLite is enough initially. Exports use versioned JSONL plus a manifest. Keep the store outside a target agent's writable workspace where practical; a same-user local process is not a strong hostile-process isolation boundary.

Store only the fields needed for the current feature. Raw content is opt-in and local. Deduplicate reconnects and repeated imports. Preserve corruption diagnostics and partial-session status; do not silently discard malformed records and then claim complete accounting.

Reports are deterministic projections. Rebuilding from accepted events must produce the same evidence state and totals. Establish bounded storage, retention/deletion, and safe export handling without building a general data platform.

## Evidence and semantic features

Deterministic features include fresh checks, repeated failure identities, changed-file/symbol counts when measurable, elapsed time, recent usage, missing events, and observed changes in the hypothesis/diagnostic record.

Jev may classify failure type, ambiguity, repeated-hypothesis likelihood, or whether a proposed next action is diagnostic. Send a bounded, explicitly approved state, not entire transcripts by default. Its output is tagged as an estimate with rubric and model versions. Missing Jev must leave a functional deterministic baseline.

Do not put terminal evaluation results or future observations into a decision-time feature vector. Do not ask Jev to certify acceptance or authorize commands.

## Policy and safety separation

Policies return one allowed recipe ID plus structured reasons and uncertainty; they never return executable shell or authorization mutations. The baseline is deterministic. An optional learned policy may rank supported alternatives in shadow mode, but a fixed gate determines eligibility.

Check the user-selected mode, approved action set, current capabilities, data-sharing scope, and budget before execution. Apply hard admission constraints only where the runtime actually enforces them. Keep observed usage, reservations, and estimated next-segment cost separate. Checkpoint-based budgeting may overshoot during an active generation; disclose that limit and stop admitting new work when required.

Jev timeout or invalid output falls back to baseline decision logic; it does not override an exhausted budget or an explicit pause. Automation, when added, needs synchronous admission guards, decision IDs, reconciliation after lost acknowledgment, and a rollback/disable switch. Do not replay an uncertain side effect blindly.

## Evaluation and research

Acceptance is computed by a separate evaluator contract against the exact evaluated repository state. Trusted check results are stronger than textual claims, but the evaluator still records whether tests were agent-editable or independent.

An experiment runner may create controlled continuations in isolated disposable environments. A Git worktree isolates files, not processes, network, credentials, or databases. Conversation forks do not snapshot the full environment. Initial experiments must restrict external state enough to make comparisons meaningful.

Keep data collection, model fitting, shadow recommendations, and policy promotion separate commands. A trained artifact includes feature/schema/action versions, training provenance, split identity, and support limits. Prefer safe data formats; do not deserialize arbitrary executable model objects from user imports.

## Operational simplicity

No cloud backend is needed for the alpha. Offline demo, import, inspection, export, and reports must work without Codex or Jev installed. A live adapter is loaded only when used. No hidden network calls in package import, telemetry, help, doctor, or offline training.
