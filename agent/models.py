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
# Multi-asset comparison + strategy backtest (docs/phases/P7)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class AssetMetrics:
    """Deterministic buy-&-hold performance stats for one asset over the aligned
    window. Annualization uses 252 trading days; risk-free rate is 0."""

    ticker: str
    start_price: float
    end_price: float
    total_return: float              # end/start - 1
    cagr: float                      # calendar-annualized compound return
    annual_vol: float                # stdev(daily returns) * sqrt(252)
    sharpe: float                    # mean/stdev(daily returns) * sqrt(252), rf=0
    max_drawdown: float              # most negative peak-to-trough (<= 0)
    drawdown_window: tuple[str, str]  # (peak_date, trough_date) of that drawdown


@dataclass(frozen=True)
class PairCorrelation:
    """Pearson correlation of two assets' daily returns + a rolling series."""

    ticker_a: str
    ticker_b: str
    pearson: float                   # -1..1 over the whole window
    rolling_window: int              # trailing window (trading days) for the series
    rolling: list[tuple[str, float]]  # (date, correlation) — empty if window > N


@dataclass(frozen=True)
class BacktestConfig:
    """A portfolio strategy to simulate over the aligned window."""

    name: str                        # e.g. "60/40 monthly-rebalanced"
    weights: dict[str, float]        # ticker -> target weight (sums to ~1)
    rebalance: str                   # "none" | "monthly" | "quarterly"
    cost_bps: float                  # round-trip transaction cost per unit turnover
    initial_capital: float


@dataclass(frozen=True)
class BacktestResult:
    """Outcome of simulating one `BacktestConfig`."""

    config: BacktestConfig
    equity_curve: list[tuple[str, float]]  # (date, portfolio value)
    total_return: float
    cagr: float
    annual_vol: float
    sharpe: float
    max_drawdown: float
    n_rebalances: int
    total_cost: float                # currency lost to transaction costs
    cost_drag: float                 # total_cost / initial_capital


@dataclass(frozen=True)
class ComparisonResult:
    """The single payload every comparison exporter consumes (docs/phases/P7).

    Deterministic and LLM-free: quantitative multi-asset comparison plus strategy
    backtests, driven from provenance-carrying price series.
    """

    title: str                       # e.g. "Gold vs Bitcoin"
    range: tuple[str, str]
    series: list[PriceSeries]        # each carries its own provenance
    aligned_dates: list[str]         # common trading dates used for all math
    metrics: list[AssetMetrics]
    correlations: list[PairCorrelation]
    backtests: list[BacktestResult]
    generated_at: str

    @property
    def tickers(self) -> list[str]:
        return [s.ticker for s in self.series]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    @staticmethod
    def from_dict(d: dict[str, Any]) -> ComparisonResult:
        return _comparison_from_dict(d)

    @staticmethod
    def from_json(s: str) -> ComparisonResult:
        return _comparison_from_dict(json.loads(s))


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


def _pairs(rows: list[list[Any]]) -> list[tuple[str, float]]:
    return [(str(r[0]), float(r[1])) for r in rows]


def _metrics(d: dict[str, Any]) -> AssetMetrics:
    return AssetMetrics(
        ticker=d["ticker"], start_price=d["start_price"], end_price=d["end_price"],
        total_return=d["total_return"], cagr=d["cagr"], annual_vol=d["annual_vol"],
        sharpe=d["sharpe"], max_drawdown=d["max_drawdown"],
        drawdown_window=(d["drawdown_window"][0], d["drawdown_window"][1]),
    )


def _correlation(d: dict[str, Any]) -> PairCorrelation:
    return PairCorrelation(
        ticker_a=d["ticker_a"], ticker_b=d["ticker_b"], pearson=d["pearson"],
        rolling_window=d["rolling_window"], rolling=_pairs(d["rolling"]),
    )


def _backtest(d: dict[str, Any]) -> BacktestResult:
    c = d["config"]
    return BacktestResult(
        config=BacktestConfig(
            name=c["name"], weights={str(k): float(v) for k, v in c["weights"].items()},
            rebalance=c["rebalance"], cost_bps=c["cost_bps"],
            initial_capital=c["initial_capital"],
        ),
        equity_curve=_pairs(d["equity_curve"]),
        total_return=d["total_return"], cagr=d["cagr"], annual_vol=d["annual_vol"],
        sharpe=d["sharpe"], max_drawdown=d["max_drawdown"],
        n_rebalances=d["n_rebalances"], total_cost=d["total_cost"], cost_drag=d["cost_drag"],
    )


def _comparison_from_dict(d: dict[str, Any]) -> ComparisonResult:
    return ComparisonResult(
        title=d["title"],
        range=(d["range"][0], d["range"][1]),
        series=[_series(s) for s in d["series"]],
        aligned_dates=list(d["aligned_dates"]),
        metrics=[_metrics(m) for m in d["metrics"]],
        correlations=[_correlation(c) for c in d["correlations"]],
        backtests=[_backtest(b) for b in d["backtests"]],
        generated_at=d["generated_at"],
    )
