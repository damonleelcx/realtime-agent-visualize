"""`market_data` tool — OHLCV bars with provenance (docs/phases/P1).

Deterministic, no LLM inside. Fallback ladder: Yahoo daily chart (keyless,
what yfinance wraps) → Stooq CSV (keyless). Every Bar is stamped with a
clickable Provenance at fetch time. Transports are module-level functions so
tests can monkeypatch them; parse functions are pure and golden-tested.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import asdict

from ..cache import JsonCache, cache_key
from ..models import Bar, PriceSeries, Provenance
from ._serde import series_from
from ._util import in_range, now_iso, ts_to_date
from .errors import DataSourceError, EmptyResultError

Clock = Callable[[], str]

# Ordered fallback ladder. Dispatched by name (below) so a monkeypatched
# `_fetch_yahoo` / `_fetch_stooq` is resolved at call time, not import time.
_MARKET_SOURCES = ("yahoo", "stooq")

_YAHOO_CHART_API = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"


def _yahoo_url(ticker: str) -> str:
    """Human-clickable history page (used as the per-bar source_url)."""
    return f"https://finance.yahoo.com/quote/{ticker}/history"


def _stooq_url(ticker: str) -> str:
    return f"https://stooq.com/q/d/l/?s={ticker.lower()}.us&i=d"


# --------------------------------------------------------------------------- #
# Transports (network). Lazy-import requests so the module imports without the
# `full` extra; tests never hit these (they monkeypatch or use parse fns).
# --------------------------------------------------------------------------- #
def _fetch_yahoo(ticker: str, start: str, end: str) -> str:  # pragma: no cover
    import requests  # noqa: PLC0415

    params: dict[str, str | int] = {"interval": "1d", "range": "10y"}
    try:
        resp = requests.get(
            _YAHOO_CHART_API.format(ticker=ticker), params=params, timeout=15,
            headers={"User-Agent": "realtime-agent-visualize/0.1"},
        )
        resp.raise_for_status()
        return str(resp.text)
    except Exception as exc:  # noqa: BLE001
        raise DataSourceError(f"yahoo transport: {exc}") from exc


def _fetch_stooq(ticker: str, start: str, end: str) -> str:  # pragma: no cover
    import requests  # noqa: PLC0415

    try:
        resp = requests.get(_stooq_url(ticker), timeout=15)
        resp.raise_for_status()
        return str(resp.text)
    except Exception as exc:  # noqa: BLE001
        raise DataSourceError(f"stooq transport: {exc}") from exc


# --------------------------------------------------------------------------- #
# Parsers (pure — golden-tested)
# --------------------------------------------------------------------------- #
def parse_yahoo_chart(raw: str, ticker: str, start: str, end: str, fetched_at: str) -> list[Bar]:
    """Yahoo v8 chart JSON → ascending, range-filtered bars."""
    url = _yahoo_url(ticker)
    query = f"{ticker}|{start}|{end}"
    try:
        result = json.loads(raw)["chart"]["result"]
        if not result:
            raise EmptyResultError("yahoo: empty result set")
        node = result[0]
        stamps = node["timestamp"]
        quote = node["indicators"]["quote"][0]
        o, h, low, c, v = (
            quote["open"], quote["high"], quote["low"], quote["close"], quote["volume"],
        )
    except EmptyResultError:
        raise
    except (KeyError, ValueError, TypeError, IndexError) as exc:
        raise DataSourceError(f"yahoo parse: {exc}") from exc

    bars: list[Bar] = []
    for i, ts in enumerate(stamps):
        if None in (o[i], h[i], low[i], c[i], v[i]):
            continue
        date = ts_to_date(int(ts))
        if not in_range(date, start, end):
            continue
        bars.append(
            Bar(
                date=date, open=float(o[i]), high=float(h[i]), low=float(low[i]),
                close=float(c[i]), volume=int(v[i]),
                prov=Provenance("yahoo", url, fetched_at, query),
            )
        )
    bars.sort(key=lambda b: b.date)
    return bars


def parse_stooq_csv(raw: str, ticker: str, start: str, end: str, fetched_at: str) -> list[Bar]:
    """Stooq daily CSV (Date,Open,High,Low,Close,Volume) → ascending bars."""
    url = _stooq_url(ticker)
    query = f"{ticker}|{start}|{end}"
    lines = [ln for ln in raw.strip().splitlines() if ln.strip()]
    if not lines or not lines[0].lower().startswith("date"):
        raise DataSourceError("stooq parse: unexpected CSV header")
    bars: list[Bar] = []
    for ln in lines[1:]:
        cols = ln.split(",")
        if len(cols) < 6:
            continue
        try:
            date = cols[0]
            if not in_range(date, start, end):
                continue
            bars.append(
                Bar(
                    date=date, open=float(cols[1]), high=float(cols[2]),
                    low=float(cols[3]), close=float(cols[4]), volume=int(float(cols[5])),
                    prov=Provenance("stooq", url, fetched_at, query),
                )
            )
        except ValueError as exc:
            raise DataSourceError(f"stooq parse: {exc}") from exc
    bars.sort(key=lambda b: b.date)
    return bars


# --------------------------------------------------------------------------- #
# Dispatch (dynamic name lookup keeps monkeypatching working)
# --------------------------------------------------------------------------- #
def _fetch_market(source: str, ticker: str, start: str, end: str) -> str:
    if source == "yahoo":
        return _fetch_yahoo(ticker, start, end)
    if source == "stooq":
        return _fetch_stooq(ticker, start, end)
    raise DataSourceError(f"unknown market source: {source}")


def _parse_market(source: str, raw: str, ticker: str, start: str, end: str, at: str) -> list[Bar]:
    if source == "yahoo":
        return parse_yahoo_chart(raw, ticker, start, end, at)
    return parse_stooq_csv(raw, ticker, start, end, at)


def _source_url(source: str, ticker: str) -> str:
    return _yahoo_url(ticker) if source == "yahoo" else _stooq_url(ticker)


# --------------------------------------------------------------------------- #
# Public tool
# --------------------------------------------------------------------------- #
def market_data(
    ticker: str,
    start: str,
    end: str,
    *,
    cache: JsonCache | None = None,
    no_cache: bool = False,
    refresh: bool = False,
    clock: Clock | None = None,
) -> PriceSeries:
    """Fetch daily OHLCV for `ticker` in `[start, end]` as a provenance-carrying
    PriceSeries. Yahoo primary, Stooq fallback. Cached by (ticker, start, end).

    Raises DataSourceError if the whole ladder is exhausted — a K-line needs bars.
    """
    cache = cache if cache is not None else JsonCache()
    clock = clock or now_iso
    key = cache_key("market", ticker, start, end)

    if not no_cache and not refresh:
        cached = cache.get(key)
        if cached is not None:
            return series_from(cached)

    fetched_at = clock()
    failures: list[str] = []
    for source in _MARKET_SOURCES:
        try:
            raw = _fetch_market(source, ticker, start, end)
            bars = _parse_market(source, raw, ticker, start, end, fetched_at)
            if not bars:
                raise EmptyResultError(f"{source}: 0 in-range rows")
            series = PriceSeries(
                ticker=ticker,
                bars=bars,
                prov=Provenance(source, _source_url(source, ticker), fetched_at,
                                f"{ticker}|{start}|{end}"),
            )
            if not no_cache:
                cache.set(key, asdict(series))
            return series
        except DataSourceError as exc:
            failures.append(str(exc))
            continue

    raise DataSourceError("market_data ladder exhausted: " + "; ".join(failures))
