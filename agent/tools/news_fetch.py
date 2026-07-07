"""`news_fetch` tool — industry headlines with provenance (docs/phases/P1).

Deterministic, no LLM inside. Fallback ladder: Hacker News Algolia (keyless)
→ Yahoo Finance RSS (keyless) → committed seed file. Each NewsItem.url is
mirrored into prov.source_url so every item is clickable. Exhausted ladder
returns [] (graceful — news is optional; the K-line still renders).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from xml.etree import ElementTree as ET

from ..cache import JsonCache, cache_key
from ..models import NewsItem, Provenance
from ._serde import newsitem_from
from ._util import date_to_ts, in_range, now_iso, ts_to_date
from .errors import DataSourceError, EmptyResultError

Clock = Callable[[], str]

_NEWS_SOURCES = ("hackernews", "yahoo_rss", "seed")
_SEED_PATH = Path(__file__).parent / "data" / "news_seed.json"

_HN_API = "https://hn.algolia.com/api/v1/search_by_date"
_HN_ITEM = "https://news.ycombinator.com/item?id={oid}"
_YAHOO_RSS = "https://feeds.finance.yahoo.com/rss/2.0/headline?s={q}&region=US&lang=en-US"


# --------------------------------------------------------------------------- #
# Transports (network). Lazy requests import; tests monkeypatch these.
# --------------------------------------------------------------------------- #
def _fetch_hn(query: str, start: str, end: str, limit: int) -> str:  # pragma: no cover
    import requests  # noqa: PLC0415

    # Server-side date filter so the API returns in-range stories, not just the
    # newest globally. end + 1 day makes the upper bound inclusive of `end`.
    numeric = []
    if start:
        numeric.append(f"created_at_i>={date_to_ts(start)}")
    if end:
        numeric.append(f"created_at_i<{date_to_ts(end) + 86400}")
    params: dict[str, str | int] = {"query": query, "tags": "story", "hitsPerPage": limit}
    if numeric:
        params["numericFilters"] = ",".join(numeric)
    try:
        resp = requests.get(_HN_API, params=params, timeout=15)
        resp.raise_for_status()
        return str(resp.text)
    except Exception as exc:  # noqa: BLE001
        raise DataSourceError(f"hn transport: {exc}") from exc


def _fetch_rss(query: str, start: str, end: str, limit: int) -> str:  # pragma: no cover
    import requests  # noqa: PLC0415

    try:
        resp = requests.get(_YAHOO_RSS.format(q=query), timeout=15)
        resp.raise_for_status()
        return str(resp.text)
    except Exception as exc:  # noqa: BLE001
        raise DataSourceError(f"rss transport: {exc}") from exc


# --------------------------------------------------------------------------- #
# Parsers (pure)
# --------------------------------------------------------------------------- #
def parse_hn(raw: str, query: str, start: str, end: str, at: str, limit: int) -> list[NewsItem]:
    """Hacker News Algolia JSON → ascending, range-filtered items.

    Uses the story URL when present, else the HN permalink — never empty.
    """
    try:
        hits = json.loads(raw)["hits"]
    except (KeyError, ValueError, TypeError) as exc:
        raise DataSourceError(f"hn parse: {exc}") from exc

    items: list[NewsItem] = []
    for h in hits:
        ts = h.get("created_at_i")
        if ts is None:
            continue
        date = ts_to_date(int(ts))
        if not in_range(date, start, end):
            continue
        url = h.get("url") or _HN_ITEM.format(oid=h.get("objectID", ""))
        title = h.get("title") or h.get("story_title") or "(untitled)"
        summary = (h.get("story_text") or "")[:280]
        items.append(NewsItem(title, url, date, summary, Provenance("hackernews", url, at, query)))
        if len(items) >= limit:
            break
    items.sort(key=lambda n: n.published_at)
    return items


def parse_rss(raw: str, query: str, start: str, end: str, at: str, limit: int) -> list[NewsItem]:
    """Minimal RSS 2.0 parse → items. pubDate → 'YYYY-MM-DD' best-effort."""
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise DataSourceError(f"rss parse: {exc}") from exc

    items: list[NewsItem] = []
    for it in root.iterfind(".//item"):
        link = (it.findtext("link") or "").strip()
        title = (it.findtext("title") or "(untitled)").strip()
        pub = (it.findtext("pubDate") or "").strip()
        date = _rss_date(pub)
        if not link or not date or not in_range(date, start, end):
            continue
        items.append(NewsItem(title, link, date, "", Provenance("yahoo_rss", link, at, query)))
        if len(items) >= limit:
            break
    items.sort(key=lambda n: n.published_at)
    return items


def _rss_date(pub: str) -> str:
    """'Wed, 30 Nov 2022 00:00:00 GMT' → '2022-11-30'. Empty on failure."""
    from datetime import datetime  # noqa: PLC0415

    for fmt in ("%a, %d %b %Y %H:%M:%S %Z", "%a, %d %b %Y %H:%M:%S %z"):
        try:
            return datetime.strptime(pub, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return ""


def load_seed(
    query: str, start: str, end: str, at: str, path: Path | None = None
) -> list[NewsItem]:
    """Committed curated events, range-filtered. Last resort — never network."""
    src = path or _SEED_PATH
    try:
        rows = json.loads(src.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise DataSourceError(f"seed load: {exc}") from exc

    items: list[NewsItem] = []
    for r in rows:
        date = r["published_at"]
        if not in_range(date, start, end):
            continue
        url = r["url"]
        items.append(
            NewsItem(r["title"], url, date, r.get("summary", ""),
                     Provenance("seed", url, at, query, note=r.get("category", "")))
        )
    items.sort(key=lambda n: n.published_at)
    return items


# --------------------------------------------------------------------------- #
# Dispatch + public tool
# --------------------------------------------------------------------------- #
def _fetch_news(source: str, query: str, start: str, end: str, limit: int) -> str:
    if source == "hackernews":
        return _fetch_hn(query, start, end, limit)
    return _fetch_rss(query, start, end, limit)


def _parse_news(
    source: str, raw: str, query: str, start: str, end: str, at: str, limit: int
) -> list[NewsItem]:
    if source == "hackernews":
        return parse_hn(raw, query, start, end, at, limit)
    return parse_rss(raw, query, start, end, at, limit)


def news_fetch(
    query: str,
    start: str,
    end: str,
    limit: int = 200,
    *,
    cache: JsonCache | None = None,
    no_cache: bool = False,
    refresh: bool = False,
    clock: Clock | None = None,
) -> list[NewsItem]:
    """Fetch industry headlines for `query` in `[start, end]`.

    HN → RSS → seed ladder. Records the actual source in each Provenance so a
    degraded run is visible downstream. Exhausted ladder returns [] (graceful).
    """
    cache = cache if cache is not None else JsonCache()
    clock = clock or now_iso
    key = cache_key("news", query, start, end, limit)

    if not no_cache and not refresh:
        cached = cache.get(key)
        if cached is not None:
            return [newsitem_from(d) for d in cached]

    at = clock()
    for source in _NEWS_SOURCES:
        try:
            if source == "seed":
                items = load_seed(query, start, end, at)
            else:
                raw = _fetch_news(source, query, start, end, limit)
                items = _parse_news(source, raw, query, start, end, at, limit)
            if not items:
                raise EmptyResultError(f"{source}: 0 in-range items")
            if not no_cache:
                cache.set(key, [asdict(n) for n in items])
            return items
        except DataSourceError:
            continue

    return []  # graceful degradation — news is optional
