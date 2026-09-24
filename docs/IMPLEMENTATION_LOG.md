# Implementation log (material decisions only)

## 2026-09-24 — testing-ready alpha (`spark/testing-ready-alpha`)

1. **Stdlib-only runtime, zero dependencies.** Install friction dominates alpha
   adoption; `urllib` (Jev), `sqlite3`, `argparse`, and a hand-rolled
   regularized logistic/ridge fit remove the supply chain. Dev extra is
   `pytest` + `ruff` only. `requires-python >=3.12`, verified on 3.12 and 3.14.
2. **Codex integration = CLI adapter, not Python SDK.** No `codex-sdk`/`openai`
   package is installed here; the documented stable surface is the installed
   `codex` CLI (0.146.0): `doctor --json` (redacted probe) and rollout JSONL
   import of an explicitly selected file. Live `exec --json` stays
   untested/dry-run-default; app-server is experimental and out of scope.
3. **Observed usage semantics beat docs.** Surveyed 11985 local rollout files'
   vocabulary (keys only) and asserted over 227 usage records: `cached ⊆
   input`, `reasoning ⊆ output`, `thread_token_usage` monotonic cumulative.
   Import threads cumulative totals only to avoid double counting.
4. **Jev via direct HTTPS, not an SDK.** One retry budget owned by `jev.py`
   (no SDK/wrapper layering), stdlib `urllib`, strict typed validation,
   401/422 fail-fast, bounded 429/529/5xx retries honoring `retry-after`.
   Verified against live docs: `POST /v1/systemone`, `jev-1.13.0`,
   input-token billing $0.042/MTok (2026-09-24).
5. **Authority is ingress-based.** File import can only assign `imported`
   (claimed trusted/evaluator/observed/human stripped with diagnostics);
   `trusted` comes only from the local check runner, `evaluator` only from
   the evaluation ingress. Synthetic fixtures can never self-verify; the
   demo's verified case runs a real local check plus a labeled demo
   evaluation.
6. **No fictional model catalogue.** `ECONOMICAL_CONTINUE` fires only with a
   configured target; Codex controls are turn-level only; served model is
   `unknown` unless an event reports it; no hard spend cap is claimed.
7. **Learning is supervised + shadow-only.** JSON artifacts (no pickle),
   grouped splits, leakage denylist, per-action support thresholds with
   abstention. Counterfactual savings are never inferred from replay.
8. **argparse `--json`/`--data-dir` accepted before or after the subcommand**
   (SUPPRESS defaults prevent subcommand defaults clobbering globals).
9. **Check identity is session-scoped** (`PRIMARY KEY (session_id, check_id)`):
   fixture `c1` colliding across sessions was caught by the demo and fixed.
10. **Cumulative subset fields are differenced** (`base_cached`/`base_reasoning`
    baselines): raw per-snapshot cached/reasoning values would double count.
