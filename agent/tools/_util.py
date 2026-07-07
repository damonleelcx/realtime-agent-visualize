"""Small shared helpers for the data tools: an injectable clock and URL check."""

from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import urlparse


def now_iso() -> str:
    """Default clock — ISO-8601 UTC. Tests inject a frozen clock for stable golden output."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def ts_to_date(unix_seconds: int) -> str:
    """Unix seconds → 'YYYY-MM-DD' in UTC."""
    return datetime.fromtimestamp(unix_seconds, UTC).strftime("%Y-%m-%d")


def date_to_ts(date: str) -> int:
    """'YYYY-MM-DD' (UTC midnight) → unix seconds. Empty string → 0."""
    if not date:
        return 0
    return int(datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=UTC).timestamp())


def in_range(date: str, start: str, end: str) -> bool:
    """Inclusive [start, end] filter. Empty bound = unbounded on that side.

    ISO 'YYYY-MM-DD' strings sort lexicographically == chronologically.
    """
    if start and date < start:
        return False
    if end and date > end:
        return False
    return True


def valid_http_url(url: str) -> bool:
    """True iff `url` is a syntactically valid http(s) URL with a host."""
    try:
        p = urlparse(url)
    except ValueError:
        return False
    return p.scheme in ("http", "https") and bool(p.netloc)
