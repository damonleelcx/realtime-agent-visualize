"""Shared data contract for the whole agent.

Every layer (tools → subagents → skills → exporters) passes these
provenance-carrying, frozen records around. Field names are load-bearing:
the HTML/Office renderers and the test invariants depend on them.

See docs/01-conventions.md §2 for the canonical definitions.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any


# --------------------------------------------------------------------------- #
# Provenance — the spine of traceability (docs/01-conventions.md §1)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Provenance:
    """Where a datum or claim came from. `source_url` must be clickable."""

    source: str          # "yfinance" | "stooq" | "hackernews" | "yahoo_rss" | ...
    source_url: str      # canonical URL a human can click to verify (never empty)
    fetched_at: str      # ISO-8601 UTC, e.g. "2025-07-07T05:00:00Z"
    query: str = ""      # the exact query/ticker/range used, for reproducibility
    note: str = ""       # optional: transform applied, page, row id, etc.


# --------------------------------------------------------------------------- #
# Market data
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Bar:
    """One daily OHLCV bar."""

    date: str            # "YYYY-MM-DD"
    open: float
    high: float
    low: float
    close: float
    volume: int
    prov: Provenance


@dataclass(frozen=True)
class PriceSeries:
    ticker: str
    bars: list[Bar]      # ascending by date
    prov: Provenance     # provenance of the series-level fetch


# --------------------------------------------------------------------------- #
# News / events
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class NewsItem:
    title: str
    url: str             # article/source URL (mirrored in prov.source_url)
    published_at: str    # "YYYY-MM-DD"
    summary: str
    prov: Provenance


# --------------------------------------------------------------------------- #
# Inflections (deterministic detector output — docs/phases/P2)
# --------------------------------------------------------------------------- #
class InflectionKind(StrEnum):
    TURNING_UP = "turning_up"        # local trough → reversal upward
    TURNING_DOWN = "turning_down"    # local peak → reversal downward
    ACCELERATE = "accelerate"        # trend slope steepens
    BREAKOUT_UP = "breakout_up"      # sustained up move / gap up
    BREAKDOWN = "breakdown"          # sustained down move / gap down


@dataclass(frozen=True)
class Inflection:
    date: str                        # bar date where it triggers
    kind: InflectionKind
    significance: float              # 0..1 normalized magnitude (top-N ranking)
    price: float                     # close at trigger
    window: tuple[str, str]          # (start_date, end_date) the detector used
    evidence_bars: list[str]         # dates of the bars that produced this signal
    detector: str                    # algorithm id + params, e.g. "pelt:rbf:pen=8"


# --------------------------------------------------------------------------- #
# Curated events + alignments (subagent output — docs/phases/P3)
# --------------------------------------------------------------------------- #
class Impact(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass(frozen=True)
class CuratedEvent:
    title: str
    date: str
    category: str                    # "model_release" | "chip" | "policy" | ...
    impact: Impact
    rationale: str                   # WHY this rating — grounded in the source
    news_refs: list[str]             # NewsItem urls backing this event (>=1)
    prov: Provenance


@dataclass(frozen=True)
class Alignment:
    inflection: Inflection
    events: list[CuratedEvent]       # events within the match window, ranked
    lag_days: int                    # event_date → inflection_date lag (signed)
    confidence: float                # 0..1 model-assigned link strength
    explanation: str                 # cites event.news_refs


# --------------------------------------------------------------------------- #
# The single payload every exporter consumes (docs/phases/P4)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class AnalysisResult:
    ticker: str
    range: tuple[str, str]
    series: PriceSeries
    inflections: list[Inflection]
    events: list[CuratedEvent]
    alignments: list[Alignment]
    generated_at: str

    # -- serialization (used by the CLI and the round-trip contract test) -- #
    def to_dict(self) -> dict[str, Any]:
        """JSON-safe dict. str-Enums serialize to their values via asdict."""
        return asdict(self)

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    @staticmethod
    def from_dict(d: dict[str, Any]) -> AnalysisResult:
        return _analysis_from_dict(d)

    @staticmethod
    def from_json(s: str) -> AnalysisResult:
        return _analysis_from_dict(json.loads(s))


# --------------------------------------------------------------------------- #
# Reconstruction helpers (explicit, so mypy --strict stays happy)
# --------------------------------------------------------------------------- #
def _prov(d: dict[str, Any]) -> Provenance:
    return Provenance(**d)


def _bar(d: dict[str, Any]) -> Bar:
    return Bar(
        date=d["date"], open=d["open"], high=d["high"], low=d["low"],
        close=d["close"], volume=d["volume"], prov=_prov(d["prov"]),
    )


def _series(d: dict[str, Any]) -> PriceSeries:
    return PriceSeries(
        ticker=d["ticker"],
        bars=[_bar(b) for b in d["bars"]],
        prov=_prov(d["prov"]),
    )


def _inflection(d: dict[str, Any]) -> Inflection:
    return Inflection(
        date=d["date"], kind=InflectionKind(d["kind"]),
        significance=d["significance"], price=d["price"],
        window=(d["window"][0], d["window"][1]),
        evidence_bars=list(d["evidence_bars"]), detector=d["detector"],
    )


def _event(d: dict[str, Any]) -> CuratedEvent:
    return CuratedEvent(
        title=d["title"], date=d["date"], category=d["category"],
        impact=Impact(d["impact"]), rationale=d["rationale"],
        news_refs=list(d["news_refs"]), prov=_prov(d["prov"]),
    )


def _alignment(d: dict[str, Any]) -> Alignment:
    return Alignment(
        inflection=_inflection(d["inflection"]),
        events=[_event(e) for e in d["events"]],
        lag_days=d["lag_days"], confidence=d["confidence"],
        explanation=d["explanation"],
    )


def _analysis_from_dict(d: dict[str, Any]) -> AnalysisResult:
    return AnalysisResult(
        ticker=d["ticker"],
        range=(d["range"][0], d["range"][1]),
        series=_series(d["series"]),
        inflections=[_inflection(i) for i in d["inflections"]],
        events=[_event(e) for e in d["events"]],
        alignments=[_alignment(a) for a in d["alignments"]],
        generated_at=d["generated_at"],
    )
