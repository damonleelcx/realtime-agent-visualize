"""Multi-asset comparison + strategy backtest — deterministic tool (docs/phases/P7).

Pure, numpy-only maths over already-fetched `PriceSeries` (no network, no LLM):
the same inputs always reproduce the same metrics, exactly like
`detect_inflections`. Every function operates on the **intersection** of the
assets' trading dates, so a 7-day-a-week asset (BTC) and a weekday-only asset
(gold futures) are compared on the days both actually traded.

Annualization uses 252 trading days; the risk-free rate is 0 (documented so the
Sharpe figure is reproducible, not a black box).
"""

from __future__ import annotations

from datetime import date

import numpy as np

from ..models import (
    AssetMetrics,
    BacktestConfig,
    BacktestResult,
    PairCorrelation,
    PriceSeries,
)

TRADING_DAYS = 252


# --------------------------------------------------------------------------- #
# Date alignment
# --------------------------------------------------------------------------- #
def align_closes(series: list[PriceSeries]) -> tuple[list[str], dict[str, list[float]]]:
    """Intersect trading dates across all series; return (dates, {ticker: closes}).

    Dates are ascending; only days on which EVERY asset has a bar are kept, so the
    returned close vectors are all the same length and index-aligned.
    """
    if not series:
        return [], {}
    common: set[str] | None = None
    per_ticker: dict[str, dict[str, float]] = {}
    for s in series:
        by_date = {b.date: b.close for b in s.bars}
        per_ticker[s.ticker] = by_date
        common = set(by_date) if common is None else (common & set(by_date))
    dates = sorted(common or set())
    closes = {t: [per_ticker[t][d] for d in dates] for t in per_ticker}
    return dates, closes


# --------------------------------------------------------------------------- #
# Per-asset metrics
# --------------------------------------------------------------------------- #
def _years(dates: list[str]) -> float:
    d0, d1 = date.fromisoformat(dates[0]), date.fromisoformat(dates[-1])
    return max((d1 - d0).days / 365.25, 1e-9)


def daily_returns(closes: list[float]) -> np.ndarray:
    p = np.asarray(closes, dtype=float)
    return np.diff(p) / p[:-1]


def _drawdown(closes: list[float], dates: list[str]) -> tuple[float, tuple[str, str]]:
    """Most negative peak-to-trough return, with (peak_date, trough_date)."""
    p = np.asarray(closes, dtype=float)
    max_peak = 0
    worst = 0.0
    worst_window = (dates[0], dates[0])
    for i in range(len(p)):
        if p[i] > p[max_peak]:
            max_peak = i
        dd = p[i] / p[max_peak] - 1.0
        if dd < worst:
            worst = dd
            worst_window = (dates[max_peak], dates[i])
    return float(worst), worst_window


def asset_metrics(ticker: str, closes: list[float], dates: list[str]) -> AssetMetrics:
    """Buy-&-hold stats for one aligned close vector (len >= 2)."""
    p = np.asarray(closes, dtype=float)
    total_return = float(p[-1] / p[0] - 1.0)
    cagr = float((p[-1] / p[0]) ** (1.0 / _years(dates)) - 1.0)
    r = daily_returns(closes)
    sd = float(np.std(r, ddof=1)) if len(r) > 1 else 0.0
    annual_vol = sd * np.sqrt(TRADING_DAYS)
    sharpe = (float(np.mean(r)) / sd * np.sqrt(TRADING_DAYS)) if sd > 0 else 0.0
    max_dd, window = _drawdown(closes, dates)
    return AssetMetrics(
        ticker=ticker, start_price=float(p[0]), end_price=float(p[-1]),
        total_return=total_return, cagr=cagr, annual_vol=float(annual_vol),
        sharpe=float(sharpe), max_drawdown=max_dd, drawdown_window=window,
    )


# --------------------------------------------------------------------------- #
# Correlation
# --------------------------------------------------------------------------- #
def correlate(
    ticker_a: str, closes_a: list[float],
    ticker_b: str, closes_b: list[float],
    dates: list[str], rolling_window: int = 60,
) -> PairCorrelation:
    """Pearson correlation of the two return streams + a trailing-window series."""
    ra, rb = daily_returns(closes_a), daily_returns(closes_b)
    pearson = float(np.corrcoef(ra, rb)[0, 1]) if len(ra) > 1 else 0.0
    rolling: list[tuple[str, float]] = []
    w = rolling_window
    # returns[i] spans dates[i]->dates[i+1]; label a window by its last date.
    if len(ra) >= w > 1:
        for i in range(w - 1, len(ra)):
            wa, wb = ra[i - w + 1 : i + 1], rb[i - w + 1 : i + 1]
            c = np.corrcoef(wa, wb)[0, 1]
            rolling.append((dates[i + 1], float(c) if np.isfinite(c) else 0.0))
    return PairCorrelation(
        ticker_a=ticker_a, ticker_b=ticker_b, pearson=pearson,
        rolling_window=w, rolling=rolling,
    )


# --------------------------------------------------------------------------- #
# Strategy backtest
# --------------------------------------------------------------------------- #
def _is_rebalance_day(prev: str, cur: str, schedule: str) -> bool:
    if schedule == "monthly":
        return prev[:7] != cur[:7]                # YYYY-MM changed
    if schedule == "quarterly":
        qp = (int(prev[5:7]) - 1) // 3
        qc = (int(cur[5:7]) - 1) // 3
        return prev[:4] != cur[:4] or qp != qc
    return False                                  # "none"


def run_backtest(
    config: BacktestConfig,
    dates: list[str],
    closes: dict[str, list[float]],
) -> BacktestResult:
    """Simulate a (optionally rebalanced) weighted portfolio on aligned closes.

    On each rebalance day the book is reset to target weights; the traded notional
    (turnover) is charged `cost_bps` and deducted from the portfolio value, so
    rebalancing's frictional drag is modelled rather than assumed free.
    """
    tickers = [t for t in config.weights if t in closes]
    w = np.array([config.weights[t] for t in tickers], dtype=float)
    px = {t: np.asarray(closes[t], dtype=float) for t in tickers}
    n = len(dates)

    capital = config.initial_capital
    units = np.array([capital * w[i] / px[t][0] for i, t in enumerate(tickers)])
    equity: list[tuple[str, float]] = [(dates[0], capital)]
    n_rebalances = 0
    total_cost = 0.0

    for k in range(1, n):
        prices_k = np.array([px[t][k] for t in tickers])
        value = float(np.dot(units, prices_k))
        if _is_rebalance_day(dates[k - 1], dates[k], config.rebalance):
            current_dollars = units * prices_k
            target_dollars = value * w
            turnover = float(np.sum(np.abs(target_dollars - current_dollars)))
            cost = turnover * config.cost_bps / 10_000.0
            total_cost += cost
            value -= cost
            units = value * w / prices_k
            n_rebalances += 1
        equity.append((dates[k], value))

    values = [v for _, v in equity]
    stats = asset_metrics(config.name, values, dates)  # reuse the return maths
    return BacktestResult(
        config=config, equity_curve=equity,
        total_return=stats.total_return, cagr=stats.cagr,
        annual_vol=stats.annual_vol, sharpe=stats.sharpe,
        max_drawdown=stats.max_drawdown, n_rebalances=n_rebalances,
        total_cost=float(total_cost), cost_drag=float(total_cost / config.initial_capital),
    )
