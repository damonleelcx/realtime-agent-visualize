"""Atomic, deterministic tools (no LLM inside).

P1: market_data, news_fetch. P2 adds detect_inflections; P4 adds artifact_io;
P7 adds compare (multi-asset metrics + strategy backtest).
"""

from __future__ import annotations

from .compare import align_closes, asset_metrics, correlate, run_backtest
from .detect_inflections import detect_inflections
from .errors import DataSourceError, EmptyResultError
from .market_data import market_data
from .news_fetch import news_fetch

__all__ = [
    "market_data",
    "news_fetch",
    "detect_inflections",
    "align_closes",
    "asset_metrics",
    "correlate",
    "run_backtest",
    "DataSourceError",
    "EmptyResultError",
]
