"""Cache (de)serialization for the record types P1 caches.

Tools store `dataclasses.asdict(record)` and rebuild via these reconstructors,
keeping the cache schema-stable without exposing model internals elsewhere.
"""

from __future__ import annotations

from typing import Any

from ..models import Bar, NewsItem, PriceSeries, Provenance


def prov_from(d: dict[str, Any]) -> Provenance:
    return Provenance(**d)


def bar_from(d: dict[str, Any]) -> Bar:
    return Bar(
        date=d["date"], open=d["open"], high=d["high"], low=d["low"],
        close=d["close"], volume=d["volume"], prov=prov_from(d["prov"]),
    )


def series_from(d: dict[str, Any]) -> PriceSeries:
    return PriceSeries(
        ticker=d["ticker"],
        bars=[bar_from(b) for b in d["bars"]],
        prov=prov_from(d["prov"]),
    )


def newsitem_from(d: dict[str, Any]) -> NewsItem:
    return NewsItem(
        title=d["title"], url=d["url"], published_at=d["published_at"],
        summary=d["summary"], prov=prov_from(d["prov"]),
    )
