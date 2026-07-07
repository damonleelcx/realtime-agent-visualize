"""Committed fixture dataset + helpers for the P5 end-to-end tests.

A small OHLCV series with one clean BREAKOUT_UP plus one news item dated just
before it, and a stub LLM whose curated event + alignment cite that news. Lets
the full pipeline run offline, deterministically, with a frozen clock.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from agent.models import Bar, InflectionKind, NewsItem, PriceSeries, Provenance
from agent.tools import detect_inflections
from agent.tools.errors import DataSourceError
from tests.mocks.llm_stub import StubLLM

FROZEN = "2025-01-01T00:00:00Z"
START = "2023-05-01"
END = "2023-05-25"
NEWS_URL = "https://nvidianews.example.com/q1-fy24"


def _closes() -> list[float]:
    # 15 flat days, then a +20% gap up, then flat — one unambiguous BREAKOUT_UP.
    return [30.0] * 15 + [36.0] * 10


def load_series(ticker: str = "NVDA") -> PriceSeries:
    prov = Provenance("yahoo", f"https://finance.yahoo.com/quote/{ticker}/history", FROZEN, ticker)
    d0 = date.fromisoformat(START)
    bars = [
        Bar((d0 + timedelta(days=i)).isoformat(), c, c * 1.01, c * 0.99, c, 1_000_000, prov)
        for i, c in enumerate(_closes())
    ]
    return PriceSeries(ticker, bars, prov)


def load_news() -> list[NewsItem]:
    prov = Provenance("hackernews", NEWS_URL, FROZEN, "NVDA")
    return [
        NewsItem(
            "NVIDIA reports blowout Q1 FY24 data-center revenue",
            NEWS_URL, "2023-05-15",
            "Record forward guidance on AI data-center demand.", prov,
        )
    ]


def fixture_market_data(ticker: str, start: str, end: str, **_kw: Any) -> PriceSeries:
    return load_series(ticker)


def fixture_news(query: str, start: str, end: str, **_kw: Any) -> list[NewsItem]:
    return load_news()


def empty_news(query: str, start: str, end: str, **_kw: Any) -> list[NewsItem]:
    return []


def flaky_market_data() -> Any:
    """Fails once with a transient error, then succeeds (for the retry test)."""
    state = {"n": 0}

    def fn(ticker: str, start: str, end: str, **_kw: Any) -> PriceSeries:
        state["n"] += 1
        if state["n"] == 1:
            raise DataSourceError("transient outage")
        return load_series(ticker)

    return fn


def always_fails_market_data(ticker: str, start: str, end: str, **_kw: Any) -> PriceSeries:
    raise DataSourceError("wedged source")


def breakout_date() -> str:
    infl = detect_inflections(load_series())
    return next(i.date for i in infl if i.kind is InflectionKind.BREAKOUT_UP)


def stub_llm(inflection_date: str | None = None) -> StubLLM:
    d = inflection_date or breakout_date()
    return StubLLM({
        "events": [{
            "title": "NVIDIA reports blowout Q1 FY24 data-center revenue",
            "date": "2023-05-15", "category": "earnings", "impact": "high",
            "rationale": "Record data-center revenue guidance drove the breakout.",
            "news_refs": [NEWS_URL],
        }],
        "alignments": [{
            "inflection_date": d, "event_indices": [0], "confidence": 0.9,
            "explanation": f"The breakout aligns with the earnings beat. See {NEWS_URL}",
        }],
    })
