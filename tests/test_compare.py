"""Deterministic maths of the comparison tool (agent/tools/compare.py)."""

from __future__ import annotations

import math

from agent.models import BacktestConfig, Bar, PriceSeries, Provenance
from agent.tools.compare import (
    align_closes,
    asset_metrics,
    correlate,
    daily_returns,
    run_backtest,
)

_P = Provenance("yahoo", "https://example.com/x", "2025-01-01T00:00:00Z", "X")


def _series(ticker: str, dated_closes: list[tuple[str, float]]) -> PriceSeries:
    bars = [Bar(d, c, c, c, c, 1, _P) for d, c in dated_closes]
    return PriceSeries(ticker, bars, _P)


def test_align_closes_intersects_dates() -> None:
    a = _series("A", [("2023-01-02", 1), ("2023-01-03", 2), ("2023-01-04", 3)])
    b = _series("B", [("2023-01-03", 9), ("2023-01-04", 8), ("2023-01-05", 7)])
    dates, closes = align_closes([a, b])
    assert dates == ["2023-01-03", "2023-01-04"]
    assert closes["A"] == [2, 3]
    assert closes["B"] == [9, 8]


def test_align_closes_disjoint_is_empty() -> None:
    a = _series("A", [("2023-01-02", 1)])
    b = _series("B", [("2023-02-02", 1)])
    dates, _ = align_closes([a, b])
    assert dates == []


def test_asset_metrics_known_values() -> None:
    dates = ["2023-01-02", "2023-01-03", "2023-01-04", "2023-01-05"]
    closes = [100.0, 120.0, 90.0, 150.0]
    m = asset_metrics("X", closes, dates)
    assert math.isclose(m.total_return, 0.5)                 # 150/100 - 1
    # worst drawdown is 90/120 - 1 = -0.25, peak@120 (idx1) -> trough@90 (idx2)
    assert math.isclose(m.max_drawdown, -0.25)
    assert m.drawdown_window == ("2023-01-03", "2023-01-04")
    assert m.start_price == 100.0 and m.end_price == 150.0


def test_daily_returns() -> None:
    r = daily_returns([100.0, 110.0, 99.0])
    assert [round(x, 4) for x in r] == [0.1, -0.1]


def test_correlation_perfect_and_inverse() -> None:
    dates = ["d0", "d1", "d2", "d3"]
    a = [100.0, 110.0, 99.0, 108.9]                          # returns +.1,-.1,+.1
    same = correlate("A", a, "B", a, dates, rolling_window=99)
    assert math.isclose(same.pearson, 1.0, abs_tol=1e-9)
    inv = [100.0, 90.0, 99.0, 89.1]                          # returns -.1,+.1,-.1
    anti = correlate("A", a, "C", inv, dates, rolling_window=99)
    assert math.isclose(anti.pearson, -1.0, abs_tol=1e-9)
    assert same.rolling == []                                # window > N -> no series


def test_rolling_correlation_labels_by_last_date() -> None:
    dates = ["d0", "d1", "d2", "d3", "d4"]                   # 4 returns
    a = [100.0, 110.0, 99.0, 108.9, 98.0]
    c = correlate("A", a, "B", a, dates, rolling_window=2)
    # windows of 2 returns -> labelled by the last date of each window
    assert [d for d, _ in c.rolling] == ["d2", "d3", "d4"]
    assert all(math.isclose(v, 1.0, abs_tol=1e-9) for _, v in c.rolling)


def test_backtest_single_asset_tracks_price() -> None:
    dates = ["2023-01-02", "2023-01-03", "2023-01-04"]
    cfg = BacktestConfig("all-in A", {"A": 1.0}, "none", 0.0, 1000.0)
    bt = run_backtest(cfg, dates, {"A": [100.0, 110.0, 121.0]})
    assert [round(v, 2) for _, v in bt.equity_curve] == [1000.0, 1100.0, 1210.0]
    assert math.isclose(bt.total_return, 0.21)
    assert bt.n_rebalances == 0 and bt.total_cost == 0.0


def test_backtest_buy_and_hold_two_assets() -> None:
    dates = ["2023-01-02", "2023-01-03", "2023-01-04"]
    cfg = BacktestConfig("50/50", {"A": 0.5, "B": 0.5}, "none", 0.0, 1000.0)
    bt = run_backtest(cfg, dates, {"A": [100.0, 100.0, 100.0], "B": [100.0, 200.0, 400.0]})
    # 5 units each: day1 500+1000=1500, day2 500+2000=2500
    assert [round(v, 2) for _, v in bt.equity_curve] == [1000.0, 1500.0, 2500.0]
    assert bt.n_rebalances == 0


def test_rebalance_counts_month_boundaries_and_charges_cost() -> None:
    dates = ["2023-01-30", "2023-01-31", "2023-02-01", "2023-02-28", "2023-03-01"]
    closes = {"A": [100.0] * 5, "B": [100.0, 100.0, 200.0, 200.0, 400.0]}
    weights = {"A": 0.5, "B": 0.5}
    free = run_backtest(BacktestConfig("m", weights, "monthly", 0.0, 1000.0), dates, closes)
    costed = run_backtest(BacktestConfig("m", weights, "monthly", 100.0, 1000.0), dates, closes)
    assert free.n_rebalances == 2                            # Feb + Mar
    assert costed.n_rebalances == 2
    assert costed.total_cost > 0.0                           # turnover was charged
    assert costed.cost_drag > 0.0
    # costs reduce the ending value vs the frictionless run
    assert costed.equity_curve[-1][1] < free.equity_curve[-1][1]
