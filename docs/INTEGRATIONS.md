# Integration setup and qualification

Checked against the primary references listed in REFERENCES.md on 2026-09-24. These are setup requirements, not live-test results. Recheck official docs and installed versions during implementation; do not assume old API or runtime details remain current.

## Offline mode

Offline demo, fixture replay, reports, storage, and deterministic policy require no key and no coding runtime. Provider traffic must be blocked in normal tests, including when a developer happens to have credentials set. An explicit live mode is a separate command/flag and never an import-time side effect.

## Jev / TypeSafe

Obtain a TypeSafe API key from https://console.typesafe.ai and supply it locally as `TYPESAFE_API_KEY`. Never paste it into a prompt, GitHub issue, committed file, or visible test log. Use the agent environment's secret facility or a locally ignored environment file. The example file contains no credential and is only a proposed configuration contract until implemented.

The official API currently accepts POST https://api.typesafe.ai/v1/systemone with Bearer authentication and a body containing model, state, and named typed questions. The response contains the served model, typed answers, and usage. Follow the official TypeSafe SDK or HTTP contract; do not use an invented chat-completions endpoint.

As checked on the date above, `jev-latest` resolves to `jev-1.13.0`. Pin a version for experiments and record both requested and returned IDs. Aliases and prices can change. The current model page describes input-token billing with free output; keep a dated pricing entry and do not assume that rule for other providers or future versions.

A minimal synthetic request shape is:

```json
{
  "model": "jev-1.13.0",
  "state": {
    "fixture": true,
    "same_assertion_after_distinct_patches": 2,
    "new_diagnostics_since_last_patch": 0,
    "hypothesis_changed": false
  },
  "questions": {
    "failure_pattern": {
      "type": "choice",
      "instructions": "Classify only the observed pattern. Do not authorize actions or certify task success. Use insufficient_evidence when these fields do not support a classification.",
      "criteria": {
        "possible_repeated_attempt": "Repeated failure with no recorded diagnostic or hypothesis change",
        "meaningful_investigation": "New diagnostic evidence or a changed hypothesis is recorded",
        "insufficient_evidence": "The supplied observation is insufficient or contradictory"
      }
    }
  }
}
```

This is a contract example, not a calibrated rubric or a request run in this foundation. Do not assert a particular answer in a live test. Validate shape, finite values, option membership, distribution bounds, expected questions, served model, and usage. Reject malformed or oversized responses safely.

Jev confidence is derived from the distribution over the supplied choices; do not display it as a calibrated probability of eventual coding success or as an experiment's action-selection propensity.

Set an absolute request deadline and one retry budget across SDK and wrapper. Do not layer unbounded retries. Authentication/validation errors fail immediately; transient overload/rate-limit/network conditions receive only bounded retries where appropriate and within the authorized attempt cap. Count every attempt, including retries, conservatively. A timed-out request may still have consumed provider resources; preserve unknown usage.

Live smoke requirements: explicit enablement, a present key, one small synthetic request, an attempt cap, no private source text, and secret-safe reporting. Key absence should produce not-run/missing-credential, not pass. Ordinary tests use a fake transport. A key by itself does not authorize any live call.

Jev is a feature provider, not the learned policy and not the evaluator. Train downstream local parameters; do not assume access to train Jev's weights.

## Codex

Use a supported local authentication flow. Current official documentation describes ChatGPT sign-in and API-key authentication with different billing. The governor must not read/copy credential values, change active accounts, invoke login/logout without user action, or silently switch billing modes.

The official SDK documentation currently includes Python and TypeScript options. Prefer one narrow Python integration for the alpha if the actual supported SDK meets the needed contract. Record the exact SDK and runtime versions and inspect current official schemas. The app-server exposes turn-level control; capability probing must establish the actual boundary used by this adapter.

Doctor should report executable/SDK presence, non-secret authentication status if supported, platform, version, supported event types, session selection, usage semantics, and which controls are documented versus observed. Do not launch a model call just to detect installation. Provide an explicit separately authorized live observation test.

Qualification covers thread/turn identity, new and resumed observations, reconnect/deduplication, usage counters, event ordering, tool/check signals, requested versus applied model/effort, and interruption limits. Any unavailable item stays unavailable/untested. Do not assume a local observer disconnect confirms server-side cancellation.

Start with observation/advice. A future apply mode uses only explicit approved supported controls. It must preserve sandbox and approval settings, reconcile uncertain action outcomes, and refuse unsupported model/effort combinations. Never claim to route every internal generation merely because a new user turn can select a model.

## Egress and resource authorization

The project defaults are no Jev traffic, no automatic coding generation, and no experiment campaign. Require explicit user-scoped enablement for each. Summarize the outbound payload and count/budget envelope before an authorized live test. Prefer minimal structured features and synthetic state; sending a bounded excerpt still sends code/data to a third party.

Credential host destinations must be fixed to the verified provider or an explicitly approved test transport. Do not forward authorization to redirects or arbitrary URLs from session data. Redact before persistence/export; never log raw HTTP authorization or a complete environment dump.
