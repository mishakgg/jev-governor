"""Usage accounting: normalization, stream reconciliation, totals, estimates.

Semantics (v1):
- ``delta`` events carry per-operation increments; ``cumulative`` events carry
  running totals that must be differenced, never summed.
- Cached input and reasoning output are subsets: they are reported for
  transparency and never added on top of input/output totals.
- Unknown usage stays unknown (``None``), never zero.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

ACCOUNTING_SEMANTICS_VERSION = 1


@dataclass
class NormalizedUsage:
    in_tokens: int | None = None
    cached_in_tokens: int | None = None
    out_tokens: int | None = None
    reasoning_out_tokens: int | None = None
    total_tokens: int | None = None
    complete: bool = True
    note: str = ""


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float) and value >= 0 and value == int(value):
        return int(value)
    return None


def normalize_usage(raw: Any, provider: str = "") -> NormalizedUsage:
    """Normalize one raw provider usage payload without double counting."""
    if not isinstance(raw, dict):
        return NormalizedUsage(complete=False, note="missing-or-malformed-usage")
    in_tok = _as_int(raw.get("input_tokens"))
    cached = _as_int(raw.get("cached_input_tokens"))
    out_tok = _as_int(raw.get("output_tokens"))
    reasoning = _as_int(raw.get("reasoning_output_tokens"))
    total = _as_int(raw.get("total_tokens"))
    notes: list[str] = []
    if cached is not None and in_tok is not None and cached > in_tok:
        notes.append("cached-exceeds-input")
        cached = in_tok
    if reasoning is not None and out_tok is not None and reasoning > out_tok:
        notes.append("reasoning-exceeds-output")
        reasoning = out_tok
    # total_tokens is informational; effective total is input + output so that
    # subset fields can never be double counted.
    effective_total: int | None = None
    if in_tok is not None and out_tok is not None:
        effective_total = in_tok + out_tok
    elif total is not None:
        effective_total = total
        notes.append("total-without-input-output-split")
    complete = in_tok is not None or out_tok is not None or total is not None
    if provider == "typesafe" and in_tok is None and total is None:
        complete = False
    return NormalizedUsage(
        in_tokens=in_tok,
        cached_in_tokens=cached,
        out_tokens=out_tok,
        reasoning_out_tokens=reasoning,
        total_tokens=effective_total,
        complete=complete,
        note=";".join(notes),
    )


@dataclass
class StreamState:
    epoch: str = ""
    base_in: int = 0
    base_out: int = 0
    base_cached: int = 0
    base_reasoning: int = 0
    last_seq: int = -1
    resets: int = 0


@dataclass
class AccountingTotals:
    in_tokens: int = 0
    cached_in_tokens: int = 0
    out_tokens: int = 0
    reasoning_out_tokens: int = 0
    unknown_ops: int = 0
    jev_in_tokens: int = 0
    jev_out_tokens: int = 0
    jev_calls: int = 0
    governor_elapsed_ms: int = 0
    governor_ops: int = 0
    resets: list[str] = field(default_factory=list)
    by_model: dict[str, dict[str, int]] = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return self.in_tokens + self.out_tokens


def _bump_model(totals: AccountingTotals, model: str, key: str, value: int) -> None:
    if not model:
        model = "unknown"
    bucket = totals.by_model.setdefault(model, {"in": 0, "out": 0})
    bucket[key] += value


def apply_to_totals(
    totals: AccountingTotals,
    streams: dict[str, StreamState],
    *,
    stream_id: str,
    epoch: str,
    stream_seq: int,
    kind: str,
    provider: str,
    model_served: str,
    usage: NormalizedUsage,
    elapsed_ms: int | None = None,
    event_id: str = "",
) -> list[str]:
    """Fold one usage record into totals. Returns diagnostics (resets etc.)."""
    diagnostics: list[str] = []
    if kind == "governor":
        totals.governor_ops += 1
        if elapsed_ms:
            totals.governor_elapsed_ms += elapsed_ms
        return diagnostics
    if not usage.complete and usage.total_tokens is None:
        totals.unknown_ops += 1
        return diagnostics
    in_v = usage.in_tokens or 0
    out_v = usage.out_tokens or 0
    cached_delta = 0
    reasoning_delta = 0
    if kind == "cumulative":
        state = streams.setdefault(stream_id or "_default", StreamState())
        if stream_id and state.epoch and epoch != state.epoch:
            diagnostics.append(f"epoch-reset:{stream_id}:{state.epoch}->{epoch}")
            state.epoch = epoch
            state.base_in, state.base_out = in_v, out_v
            state.base_cached = usage.cached_in_tokens or 0
            state.base_reasoning = usage.reasoning_out_tokens or 0
            state.last_seq = stream_seq
            state.resets += 1
            totals.resets.append(f"{event_id}:epoch-reset")
            return diagnostics
        if not state.epoch:
            state.epoch = epoch
        if stream_seq <= state.last_seq and state.last_seq >= 0:
            diagnostics.append(f"repeated-cumulative-snapshot:{event_id}")
            return diagnostics
        if in_v < state.base_in or out_v < state.base_out:
            diagnostics.append(f"counter-reset:{stream_id or '_default'}")
            totals.resets.append(f"{event_id}:counter-reset")
            state.base_in, state.base_out = in_v, out_v
            state.base_cached = usage.cached_in_tokens or 0
            state.base_reasoning = usage.reasoning_out_tokens or 0
            state.last_seq = stream_seq
            state.resets += 1
            return diagnostics
        delta_in, delta_out = in_v - state.base_in, out_v - state.base_out
        # Subset fields in cumulative snapshots are cumulative too: difference
        # them against their own baselines, never add them raw.
        cached_delta = max(0, (usage.cached_in_tokens or 0) - state.base_cached)
        reasoning_delta = max(0, (usage.reasoning_out_tokens or 0) - state.base_reasoning)
        state.base_in, state.base_out = in_v, out_v
        state.base_cached = usage.cached_in_tokens or 0
        state.base_reasoning = usage.reasoning_out_tokens or 0
        state.last_seq = stream_seq
    elif kind == "delta":
        state = streams.setdefault(stream_id or "_delta", StreamState())
        if stream_id and stream_seq <= state.last_seq and state.last_seq >= 0:
            diagnostics.append(f"repeated-delta:{event_id}")
            return diagnostics
        if stream_id:
            state.last_seq = stream_seq
        delta_in, delta_out = in_v, out_v
        cached_delta = min(usage.cached_in_tokens or 0, delta_in)
        reasoning_delta = min(usage.reasoning_out_tokens or 0, delta_out)
    else:  # kind == "unknown" with partial numbers: count what is known.
        totals.unknown_ops += 1
        delta_in, delta_out = in_v, out_v
        cached_delta = min(usage.cached_in_tokens or 0, delta_in) if delta_in else 0
        reasoning_delta = min(usage.reasoning_out_tokens or 0, delta_out) if delta_out else 0
    totals.in_tokens += delta_in
    totals.out_tokens += delta_out
    # Subsets are reported for transparency, never added to totals again.
    totals.cached_in_tokens += cached_delta
    totals.reasoning_out_tokens += reasoning_delta
    if provider == "typesafe":
        totals.jev_calls += 1
        totals.jev_in_tokens += delta_in
        totals.jev_out_tokens += delta_out
    _bump_model(totals, model_served, "in", delta_in)
    _bump_model(totals, model_served, "out", delta_out)
    return diagnostics


# Dated, sourced price entries. Only listed (provider, model) pairs can be
# estimated; everything else is reported as unpriced, never converted by guess.
PRICE_TABLE = {
    "version": "2026-09-24",
    "source": "https://docs.typesafe.ai/models (checked 2026-09-24)",
    "entries": {
        ("typesafe", "jev-1.13.0"): {
            "currency": "USD",
            "per_mtok_input": 0.042,
            "per_mtok_output": 0.0,
            "note": "input-token billing, free output",
        },
    },
}


def estimate_cost(totals: AccountingTotals) -> dict[str, Any]:
    """Estimate cost only for priced usage; disclose coverage explicitly."""
    amounts: list[dict[str, Any]] = []
    for (provider, model), entry in PRICE_TABLE["entries"].items():
        bucket = totals.by_model.get(model)
        if provider == "typesafe" and model == "jev-1.13.0":
            used_in = totals.jev_in_tokens
            used_out = totals.jev_out_tokens
        elif bucket is not None:
            used_in = bucket["in"]
            used_out = bucket["out"]
        else:
            continue
        if used_in == 0 and used_out == 0:
            continue
        amounts.append(
            {
                "provider": provider,
                "model": model,
                "currency": entry["currency"],
                "amount": round(
                    used_in / 1_000_000 * entry["per_mtok_input"]
                    + used_out / 1_000_000 * entry["per_mtok_output"],
                    6,
                ),
                "priced_input_tokens": used_in,
                "priced_output_tokens": used_out,
            }
        )
    priced_in = sum(a["priced_input_tokens"] for a in amounts)
    priced_out = sum(a["priced_output_tokens"] for a in amounts)
    return {
        "price_version": PRICE_TABLE["version"],
        "price_source": PRICE_TABLE["source"],
        "estimates": amounts,
        "coverage": {
            "priced_input_tokens": priced_in,
            "priced_output_tokens": priced_out,
            "unpriced_input_tokens": totals.in_tokens - priced_in,
            "unpriced_output_tokens": totals.out_tokens - priced_out,
            "declares": "codex/subscription usage has no documented token price; "
            "reported as measured tokens only",
        },
        "actual_billing": None,
        "observed_credits": None,
        "note": "estimates are API-equivalent only where a dated rate exists; "
        "actual billing and credits are separate and usually unobserved",
    }
