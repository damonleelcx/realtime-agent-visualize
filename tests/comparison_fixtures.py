"""Deterministic fixtures for the multi-asset comparison tests (docs/phases/P7).

Two small, provenance-carrying series whose closes are chosen so the metrics are
hand-checkable, plus an injectable market_data stub. Gold trades weekdays only and
Bitcoin every day, so the pipeline's date-intersection is exercised.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from agent.models import Bar, PriceSeries, Provenance

FROZEN = "2025-01-01T00:00:00Z"
GOLD_URL = "https://finance.yahoo.com/quote/GC=F/history"
BTC_URL = "https://finance.yahoo.com/quote/BTC-USD/history"


def _series(
    ticker: str, url: str, start: str, closes: list[float], *, weekdays_only: bool
) -> PriceSeries:
    prov = Provenance("yahoo", url, FROZEN, ticker)
    bars: list[Bar] = []
    d = date.fromisoformat(start)
    i = 0
    while i < len(closes):
        if not (weekdays_only and d.weekday() >= 5):
            c = closes[i]
            bars.append(Bar(d.isoformat(), c, c * 1.01, c * 0.99, c, 1_000_000, prov))
            i += 1
        d += timedelta(days=1)
    return PriceSeries(ticker, bars, prov)


def gold() -> PriceSeries:
    # weekday-only; steady low-vol drift
    closes = [1800.0 + 5.0 * i for i in range(60)]
    return _series("GC=F", GOLD_URL, "2023-01-02", closes, weekdays_only=True)


def btc() -> PriceSeries:
    # every day; higher vol, one clear drawdown then recovery
    closes = [20000.0 * (1.01 ** i) for i in range(40)]
    closes += [closes[-1] * 0.7]                      # -30% shock
    closes += [closes[-1] * (1.02 ** i) for i in range(1, 40)]
    return _series("BTC-USD", BTC_URL, "2023-01-02", closes, weekdays_only=False)


def market_data_stub() -> Any:
    data = {"GC=F": gold(), "BTC-USD": btc()}

    def fn(ticker: str, start: str, end: str, **_kw: Any) -> PriceSeries:
        return data[ticker]

    return fn
