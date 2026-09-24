"""Usage normalization, stream reconciliation, estimates."""

from __future__ import annotations

from jev_governor import accounting


def _apply(totals, streams, **overrides):
    base = {
        "stream_id": "",
        "epoch": "",
        "stream_seq": 0,
        "kind": "delta",
        "provider": "openai-codex",
        "model_served": "m",
        "usage": accounting.NormalizedUsage(),
        "event_id": "e",
    }
    base.update(overrides)
    return accounting.apply_to_totals(totals, streams, **base)


def test_delta_sums_and_subsets_not_double_counted():
    totals = accounting.AccountingTotals()
    streams: dict = {}
    usage = accounting.normalize_usage(
        {
            "input_tokens": 1000,
            "cached_input_tokens": 800,
            "output_tokens": 100,
            "reasoning_output_tokens": 60,
            "total_tokens": 1100,
        }
    )
    _apply(totals, streams, usage=usage, event_id="e1")
    assert totals.in_tokens == 1000
    assert totals.out_tokens == 100
    assert totals.total_tokens == 1100
    assert totals.cached_in_tokens == 800
    assert totals.reasoning_out_tokens == 60


def test_cumulative_differenced_not_summed():
    totals = accounting.AccountingTotals()
    streams: dict = {}
    snapshots = [(1, 1000, 100), (2, 1500, 160), (3, 1500, 160), (2, 1500, 160)]
    diags: list[str] = []
    for seq, i, o in snapshots:
        usage = accounting.normalize_usage({"input_tokens": i, "output_tokens": o})
        diags = _apply(
            totals,
            streams,
            kind="cumulative",
            stream_id="t1",
            epoch="s1",
            stream_seq=seq,
            usage=usage,
            event_id=f"e{seq}",
        )
    assert totals.in_tokens == 1500
    assert totals.out_tokens == 160
    assert any("repeated-cumulative" in d for d in diags)


def test_counter_reset_is_diagnostic_not_refund():
    totals = accounting.AccountingTotals()
    streams: dict = {}
    _apply(
        totals,
        streams,
        kind="cumulative",
        stream_id="t1",
        epoch="s1",
        stream_seq=1,
        usage=accounting.normalize_usage({"input_tokens": 1500, "output_tokens": 160}),
        event_id="e1",
    )
    diags = _apply(
        totals,
        streams,
        kind="cumulative",
        stream_id="t1",
        epoch="s1",
        stream_seq=2,
        usage=accounting.normalize_usage({"input_tokens": 100, "output_tokens": 10}),
        event_id="e2",
    )
    assert totals.in_tokens == 1500  # no negative delta
    assert any("counter-reset" in d for d in diags)
    assert totals.resets


def test_epoch_change_starts_new_baseline():
    totals = accounting.AccountingTotals()
    streams: dict = {}
    _apply(
        totals,
        streams,
        kind="cumulative",
        stream_id="t1",
        epoch="s1",
        stream_seq=1,
        usage=accounting.normalize_usage({"input_tokens": 1500, "output_tokens": 160}),
        event_id="e1",
    )
    diags = _apply(
        totals,
        streams,
        kind="cumulative",
        stream_id="t1",
        epoch="s2",
        stream_seq=1,
        usage=accounting.normalize_usage({"input_tokens": 200, "output_tokens": 20}),
        event_id="e2",
    )
    assert totals.in_tokens == 1500
    assert any("epoch-reset" in d for d in diags)


def test_missing_usage_stays_unknown():
    totals = accounting.AccountingTotals()
    streams: dict = {}
    usage = accounting.normalize_usage(None)
    assert not usage.complete
    _apply(totals, streams, kind="unknown", usage=usage, event_id="e1")
    assert totals.unknown_ops == 1
    assert totals.total_tokens == 0


def test_jev_and_governor_tracked_separately():
    totals = accounting.AccountingTotals()
    streams: dict = {}
    _apply(
        totals,
        streams,
        provider="typesafe",
        usage=accounting.normalize_usage({"input_tokens": 300, "output_tokens": 30}),
        event_id="j1",
    )
    _apply(
        totals,
        streams,
        kind="governor",
        usage=accounting.NormalizedUsage(),
        elapsed_ms=120,
        event_id="g1",
    )
    assert totals.jev_calls == 1
    assert totals.jev_in_tokens == 300
    assert totals.governor_ops == 1
    assert totals.governor_elapsed_ms == 120


def test_estimate_only_prices_listed_models():
    totals = accounting.AccountingTotals()
    streams: dict = {}
    _apply(
        totals,
        streams,
        provider="typesafe",
        model_served="jev-1.13.0",
        usage=accounting.normalize_usage({"input_tokens": 1_000_000, "output_tokens": 0}),
        event_id="j1",
    )
    _apply(
        totals,
        streams,
        provider="openai-codex",
        model_served="gpt-x",
        usage=accounting.normalize_usage({"input_tokens": 500, "output_tokens": 50}),
        event_id="c1",
    )
    cost = accounting.estimate_cost(totals)
    assert cost["price_version"] == "2026-09-24"
    assert len(cost["estimates"]) == 1
    assert cost["estimates"][0]["amount"] == 0.042
    assert cost["coverage"]["unpriced_input_tokens"] == 500
    assert cost["actual_billing"] is None
