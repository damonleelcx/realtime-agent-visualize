"""End-to-end comparison pipeline, fully offline (agent/comparison.py)."""

from __future__ import annotations

import pytest

from agent.comparison import run_comparison
from agent.models import ComparisonResult
from agent.orchestrator import ValidationError
from tests.comparison_fixtures import FROZEN, gold, market_data_stub


def _run(tmp_path, outputs=("html", "xlsx", "pptx", "docx")):
    return run_comparison(
        ["GC=F", "BTC-USD"], "2023-01-02", "2023-06-01", list(outputs),
        title="Gold vs Bitcoin", rebalance="monthly", cost_bps=10.0,
        market_data_fn=market_data_stub(), out_dir=str(tmp_path), clock=lambda: FROZEN,
    )


def test_pipeline_produces_payload_and_artifacts(tmp_path) -> None:
    rr = _run(tmp_path)
    r = rr.result
    assert isinstance(r, ComparisonResult)
    assert r.tickers == ["GC=F", "BTC-USD"]
    assert len(r.aligned_dates) >= 2
    assert len(r.metrics) == 2
    assert len(r.correlations) == 1                       # one pair
    assert len(r.backtests) == 2                          # strategy + buy&hold benchmark
    # deterministic detail: buy&hold benchmark pays no transaction cost
    bench = next(b for b in r.backtests if b.config.rebalance == "none")
    assert bench.total_cost == 0.0
    assert len(rr.artifacts) == 4
    for p in rr.artifacts:
        assert __import__("pathlib").Path(p).exists()


def test_pipeline_payload_round_trips(tmp_path) -> None:
    r = _run(tmp_path, outputs=("html",)).result
    r2 = ComparisonResult.from_json(r.to_json())
    assert r2.title == r.title
    assert r2.tickers == r.tickers
    assert r2.metrics[0].max_drawdown == r.metrics[0].max_drawdown
    assert r2.backtests[0].equity_curve == r.backtests[0].equity_curve


def test_pipeline_rejects_non_overlapping_assets(tmp_path) -> None:
    def disjoint(ticker, start, end, **_kw):
        s = gold()
        if ticker == "BTC-USD":
            # shift BTC a decade away so no trading date overlaps
            from agent.models import Bar, PriceSeries
            bars = [Bar("2033" + b.date[4:], b.open, b.high, b.low, b.close, b.volume, b.prov)
                    for b in s.bars]
            return PriceSeries("BTC-USD", bars, s.prov)
        return s

    with pytest.raises(ValidationError):
        run_comparison(
            ["GC=F", "BTC-USD"], "2023-01-02", "2023-06-01", ["html"],
            market_data_fn=disjoint, out_dir=str(tmp_path), clock=lambda: FROZEN,
        )


def test_needs_two_tickers(tmp_path) -> None:
    with pytest.raises(ValueError):
        run_comparison(["GC=F"], "2023-01-02", "2023-06-01", ["html"],
                       market_data_fn=market_data_stub(), out_dir=str(tmp_path))
