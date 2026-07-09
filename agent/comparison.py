"""Comparison harness — multi-asset comparison + strategy backtest (docs/phases/P7).

A deterministic, LLM-free sibling of the single-ticker `Orchestrator.run`: it runs
the same Plan → Act → Observe → Validate cycle (reusing the harness's bounded
retry) over quantitative capabilities only, so the whole pipeline is offline and
reproducible. Produces one `ComparisonResult` and renders the HTML/Office trio.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import (
    BacktestConfig,
    ComparisonResult,
    PriceSeries,
)
from .orchestrator import (
    MAX_TURNS,
    EventCb,
    MarketFn,
    Orchestrator,
    RunCancelled,
    ValidationError,
)
from .subagents.report_builder import comparison_report_builder
from .tools import align_closes, asset_metrics, correlate, market_data, run_backtest
from .tools._util import now_iso

_PLAN_STEPS = [
    "fetch market data for each asset (tool: market_data)",
    "align to common trading dates (tool: compare.align_closes)",
    "compute per-asset metrics (tool: compare.asset_metrics)",
    "compute pairwise correlations (tool: compare.correlate)",
    "run strategy backtests (tool: compare.run_backtest)",
    "assemble comparison payload",
    "render deliverables (comparison_report_builder)",
    "validate provenance + artifacts",
]


@dataclass(frozen=True)
class ComparisonRunResult:
    result: ComparisonResult
    artifacts: list[str]
    plan: list[str]


def default_weights(tickers: list[str]) -> dict[str, float]:
    """Equal weight across the assets."""
    n = len(tickers)
    return {t: 1.0 / n for t in tickers} if n else {}


def run_comparison(
    tickers: list[str],
    start: str,
    end: str,
    outputs: list[str],
    *,
    title: str = "",
    weights: dict[str, float] | None = None,
    rebalance: str = "monthly",
    cost_bps: float = 10.0,
    initial_capital: float = 10_000.0,
    rolling_window: int = 60,
    cache: Any | None = None,
    clock: Callable[[], str] | None = None,
    out_dir: str = "artifacts",
    market_data_fn: MarketFn = market_data,
    max_turns: int = MAX_TURNS,
    on_event: EventCb = None,
    should_cancel: Callable[[], bool] | None = None,
) -> ComparisonRunResult:
    """Compare `tickers` over [start, end] and render the deliverables."""
    if len(tickers) < 2:
        raise ValueError("comparison needs at least two tickers")
    clk = clock or now_iso
    emit = on_event or (lambda _e: None)
    w = weights or default_weights(tickers)
    disp_title = title or " vs ".join(tickers)
    harness = Orchestrator()  # reuse its bounded Act+Retry
    ctx: dict[str, Any] = {"feedback": []}

    def s_fetch(c: dict[str, Any]) -> None:
        c["series"] = [
            market_data_fn(t, start, end, cache=cache, clock=clk) for t in tickers
        ]

    def s_align(c: dict[str, Any]) -> None:
        c["dates"], c["closes"] = align_closes(c["series"])

    def s_metrics(c: dict[str, Any]) -> None:
        c["metrics"] = [
            asset_metrics(t, c["closes"][t], c["dates"]) for t in tickers
        ]

    def s_corr(c: dict[str, Any]) -> None:
        pairs = []
        for i in range(len(tickers)):
            for j in range(i + 1, len(tickers)):
                a, b = tickers[i], tickers[j]
                pairs.append(
                    correlate(a, c["closes"][a], b, c["closes"][b], c["dates"], rolling_window)
                )
        c["correlations"] = pairs

    def s_backtest(c: dict[str, Any]) -> None:
        strat = BacktestConfig(
            name=f"{rebalance}-rebalanced portfolio",
            weights=w, rebalance=rebalance, cost_bps=cost_bps,
            initial_capital=initial_capital,
        )
        bench = BacktestConfig(
            name="buy & hold (no rebalance)",
            weights=w, rebalance="none", cost_bps=0.0, initial_capital=initial_capital,
        )
        c["backtests"] = [run_backtest(cfg, c["dates"], c["closes"]) for cfg in (strat, bench)]

    def s_assemble(c: dict[str, Any]) -> None:
        c["result"] = ComparisonResult(
            title=disp_title, range=(start, end), series=c["series"],
            aligned_dates=c["dates"], metrics=c["metrics"],
            correlations=c["correlations"], backtests=c["backtests"], generated_at=clk(),
        )

    def s_render(c: dict[str, Any]) -> None:
        c["artifacts"] = comparison_report_builder(c["result"], list(outputs), out_dir=out_dir)

    # Step names are prefixes of the plan labels above, so the dashboard's
    # prefix-match lights each step up as it runs.
    Detail = Callable[[dict[str, Any]], str]
    steps: list[tuple[str, Callable[[dict[str, Any]], None], Detail]] = [
        ("fetch market data", s_fetch, lambda c: f"{len(c['series'])} series"),
        ("align to common trading dates", s_align, lambda c: f"{len(c['dates'])} common days"),
        ("compute per-asset metrics", s_metrics, lambda c: f"{len(c['metrics'])} assets"),
        ("compute pairwise correlations", s_corr, lambda c: f"{len(c['correlations'])} pairs"),
        ("run strategy backtests", s_backtest, lambda c: f"{len(c['backtests'])} strategies"),
        ("assemble comparison payload", s_assemble, lambda _c: "payload assembled"),
        ("render deliverables", s_render, lambda c: f"{len(c['artifacts'])} artifacts"),
    ]

    emit({"type": "plan", "steps": list(_PLAN_STEPS)})
    turns = 0
    for name, fn, detail in steps:
        if should_cancel is not None and should_cancel():
            raise RunCancelled(f"cancelled before '{name}'")
        emit({"type": "act", "step": name})
        # After align, fail fast with a clear message if the assets never overlap.
        turns = harness._act(name, fn, ctx, turns, max_turns, emit)
        if name.startswith("align to common") and len(ctx["dates"]) < 2:
            raise ValidationError(
                f"assets share {len(ctx['dates'])} common trading days — need >= 2 to compare"
            )
        emit({"type": "observe", "step": name, "detail": detail(ctx)})

    _validate(ctx, list(outputs))
    emit({"type": "validate", "ok": True})
    r = ctx["result"]
    emit({
        "type": "result", "title": r.title, "assets": len(r.series),
        "days": len(r.aligned_dates), "backtests": len(r.backtests),
    })
    return ComparisonRunResult(result=r, artifacts=ctx["artifacts"], plan=list(_PLAN_STEPS))


def _validate(ctx: dict[str, Any], outputs: list[str]) -> None:
    """Invariant gate: provenance complete + artifacts on disk (P-INV-1)."""
    fails: list[str] = []
    series: list[PriceSeries] = ctx["series"]
    for s in series:
        if not s.prov.source_url:
            fails.append(f"series {s.ticker} missing source_url")
    for p in ctx["artifacts"]:
        if not Path(p).exists():
            fails.append(f"artifact missing on disk: {p}")
    if fails:
        raise ValidationError("; ".join(fails))
