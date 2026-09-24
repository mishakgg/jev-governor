# Primary references and verification notes

Checked 2026-09-24. These links are implementation starting points, not evidence that this repository has exercised an integration. Recheck live documentation and installed SDK/runtime versions before relying on any contract. No third-party implementation code was copied into this foundation.

## TypeSafe / Jev

- [Quick start](https://docs.typesafe.ai/introduction/quickstart): dashboard key setup and API entry point; environment variable TYPESAFE_API_KEY.
- [HTTP API](https://docs.typesafe.ai/api): model/state/questions request, typed answers, usage, and error contracts.
- [Models](https://docs.typesafe.ai/models): checked version/alias mapping, rate/context/billing details, and model-version reporting. As checked, jev-latest points to jev-1.13.0. Treat prices and limits as dated information.
- [Confidence](https://docs.typesafe.ai/confidence): distribution-derived certainty; downstream coding-success calibration remains a separate empirical task.
- [SDK index](https://docs.typesafe.ai/sdk): official client options; inspect their current timeout/retry defaults before wrapping them.
- [Documentation index](https://docs.typesafe.ai/llms.txt): discover current official pages rather than guessing endpoints.

## OpenAI / Codex

- [Codex SDK](https://developers.openai.com/codex/sdk/): current Python and TypeScript integration entry points. Use only the chosen SDK's actual current schemas.
- [App server](https://developers.openai.com/codex/app-server/): thread/turn events and controls; probe exact granularity and platform behavior.
- [Authentication](https://developers.openai.com/codex/auth/): supported local sign-in methods and separation of subscription and API-key billing.
- [Reasoning guide](https://developers.openai.com/api/docs/guides/reasoning): verify usage-detail semantics; reasoning tokens must not be counted twice when already included in output usage.

## Project interpretation

Official APIs establish available primitives, not that an inference-governor policy improves code quality or saves tokens. A semantic confidence distribution is not a trained outcome predictor. A selected model setting is not necessarily the actual served configuration. A successful request is not a validated intervention.

The implementation should compare actual task continuations, preserve total experiment costs, and report unverified items explicitly. Do not claim novelty from the absence of one exact product name or infer savings from rerating old traces at cheaper prices.
