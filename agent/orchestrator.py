"""Harness / orchestration layer (docs/00-overview.md §5, docs/phases/P5).

Strings the P1–P4 capabilities into one autonomous run via a
Plan → Act → Observe → Validate → Retry cycle, bounded by a hard turn cap so a
wedged step fails cleanly instead of hanging or spinning.

- **Plan**: decompose into an ordered checklist.
- **Act**: run the next step (a tool, or a subagent that receives only structured
  input and returns structured output — never raw scratch context).
- **Observe**: feed each typed result into the running context.
- **Validate**: after render, check the invariants (provenance complete,
  citations resolve, artifacts exist on disk).
- **Retry**: on a transient failure, re-run the step with feedback appended,
  bounded by MAX_STEP_RETRIES / MAX_TURNS → TerminationError.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .llm import LLMClient
from .models import AnalysisResult
from .subagents.event_curator import event_curator
from .subagents.report_builder import report_builder
from .subagents.signal_analyst import DEFAULT_WINDOW_DAYS, signal_analyst
from .tools import detect_inflections, market_data, news_fetch
from .tools._util import now_iso

MAX_TURNS = 40          # global cap on step attempts (steps + retries)
MAX_STEP_RETRIES = 2    # per-step retries before a step is declared wedged
TOP_N_INFLECTIONS = 25

# Search news by company name, not the ticker — forums/news index "NVIDIA", not "NVDA".
_COMPANY = {
    "NVDA": "NVIDIA", "TSLA": "Tesla", "AAPL": "Apple", "MSFT": "Microsoft",
    "GOOGL": "Google", "GOOG": "Google", "AMZN": "Amazon", "META": "Meta",
    "AMD": "AMD", "INTC": "Intel", "TSM": "TSMC",
}


def _news_query(ticker: str) -> str:
    return f"{_COMPANY.get(ticker.upper(), ticker)} AI"

# The plan the Loop displays; mirrors the read-path in overview §5.
_PLAN_STEPS = [
    "fetch market data (tool: market_data)",
    "fetch industry news (tool: news_fetch)",
    "detect price inflections (tool: detect_inflections)",
    "curate events + impact ratings (subagent: event_curator)",
    "align inflections ↔ events (subagent: signal_analyst)",
    "assemble analysis payload",
    "render deliverables (report_builder)",
    "validate provenance + artifacts",
]


class TerminationError(RuntimeError):
    """The run hit the turn/retry cap — a step could not complete."""


class ValidationError(RuntimeError):
    """The rendered run failed an invariant check."""


class RunCancelled(RuntimeError):
    """The caller cancelled the run (e.g. the dashboard Stop button)."""


@dataclass(frozen=True)
class RunResult:
    result: AnalysisResult
    artifacts: list[str]
    plan: list[str]


MarketFn = Callable[..., Any]
NewsFn = Callable[..., Any]
EventCb = Callable[[dict[str, Any]], None] | None  # progress hook (e.g. the live dashboard)


class Orchestrator:
    """The Harness: owns *how* the work gets done (the Loop owns *when to stop*)."""

    def plan(self, task: str) -> list[str]:
        """Decompose a task into the ordered checklist (task-independent here)."""
        return list(_PLAN_STEPS)

    def run(
        self,
        ticker: str,
        start: str,
        end: str,
        outputs: list[str],
        *,
        client: LLMClient,
        cache: Any | None = None,
        clock: Callable[[], str] | None = None,
        out_dir: str = "artifacts",
        market_data_fn: MarketFn = market_data,
        news_fetch_fn: NewsFn = news_fetch,
        window_days: int = DEFAULT_WINDOW_DAYS,
        max_turns: int = MAX_TURNS,
        on_event: EventCb = None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> RunResult:
        clk = clock or now_iso
        emit = on_event or (lambda _e: None)
        query = _news_query(ticker)
        ctx: dict[str, Any] = {"feedback": []}

        def s_market(c: dict[str, Any]) -> None:
            c["series"] = market_data_fn(ticker, start, end, cache=cache, clock=clk)

        def s_news(c: dict[str, Any]) -> None:
            c["news"] = news_fetch_fn(query, start, end, cache=cache, clock=clk)

        def s_detect(c: dict[str, Any]) -> None:
            c["inflections"] = detect_inflections(c["series"], top_n=TOP_N_INFLECTIONS)

        def s_curate(c: dict[str, Any]) -> None:
            c["events"] = event_curator(c["news"], ticker, (start, end), client=client)

        def s_align(c: dict[str, Any]) -> None:
            c["alignments"] = signal_analyst(
                c["inflections"], c["events"], client=client, window_days=window_days
            )

        def s_assemble(c: dict[str, Any]) -> None:
            c["result"] = AnalysisResult(
                ticker=ticker, range=(start, end), series=c["series"],
                inflections=c["inflections"], events=c["events"],
                alignments=c["alignments"], generated_at=clk(),
            )

        def s_render(c: dict[str, Any]) -> None:
            c["artifacts"] = report_builder(c["result"], list(outputs), out_dir=out_dir)

        def _src(c: dict[str, Any]) -> str:
            return c["news"][0].prov.source if c["news"] else "none"

        # (name, action, detail-for-Observe) — detail is streamed to the dashboard.
        Detail = Callable[[dict[str, Any]], str]
        steps: list[tuple[str, Callable[[dict[str, Any]], None], Detail]] = [
            ("fetch market data", s_market, lambda c: f"{len(c['series'].bars)} bars"),
            ("fetch industry news", s_news,
             lambda c: f"{len(c['news'])} items (source: {_src(c)})"),
            ("detect price inflections", s_detect,
             lambda c: f"{len(c['inflections'])} inflections"),
            ("curate events", s_curate, lambda c: f"{len(c['events'])} events"),
            ("align inflections ↔ events", s_align,
             lambda c: f"{len(c['alignments'])} alignments"),
            ("assemble analysis payload", s_assemble, lambda _c: "payload assembled"),
            ("render deliverables", s_render, lambda c: f"{len(c['artifacts'])} artifacts"),
        ]

        emit({"type": "plan", "steps": self.plan("")})
        turns = 0
        for name, fn, detail in steps:
            if should_cancel is not None and should_cancel():
                raise RunCancelled(f"cancelled before '{name}'")
            emit({"type": "act", "step": name})
            turns = self._act(name, fn, ctx, turns, max_turns, emit)
            emit({"type": "observe", "step": name, "detail": detail(ctx)})

        self._validate(ctx, list(outputs), window_days)
        emit({"type": "validate", "ok": True})
        r = ctx["result"]
        emit({
            "type": "result", "ticker": r.ticker,
            "bars": len(r.series.bars), "inflections": len(r.inflections),
            "events": len(r.events), "alignments": len(r.alignments),
        })
        return RunResult(result=r, artifacts=ctx["artifacts"], plan=self.plan(""))

    def _act(
        self,
        name: str,
        fn: Callable[[dict[str, Any]], None],
        ctx: dict[str, Any],
        turns: int,
        max_turns: int,
        emit: Callable[[dict[str, Any]], None] = lambda _e: None,
    ) -> int:
        """Act + Observe with bounded Retry-with-feedback. Raises TerminationError
        when a step stays wedged or the global turn cap is exceeded."""
        attempt = 0
        while True:
            turns += 1
            if turns > max_turns:
                raise TerminationError(f"exceeded {max_turns} turns at step '{name}'")
            try:
                fn(ctx)
                return turns
            except Exception as exc:  # noqa: BLE001 — observe any failure, then decide
                attempt += 1
                msg = f"{name} failed (attempt {attempt}): {exc}"
                ctx["feedback"].append(msg)
                emit({"type": "retry", "step": name, "attempt": attempt, "error": str(exc)})
                if attempt > MAX_STEP_RETRIES:
                    raise TerminationError(
                        f"step '{name}' failed after {attempt} attempts: {exc}"
                    ) from exc

    def _validate(self, ctx: dict[str, Any], outputs: list[str], window_days: int) -> None:
        """Validate — the invariant gate before returning (P-INV-1/2/3 + artifacts)."""
        fails: list[str] = []
        news_urls = {n.url for n in ctx["news"]}

        for b in ctx["series"].bars:
            if not b.prov.source_url:
                fails.append(f"bar {b.date} missing source_url")
        for e in ctx["events"]:
            if not e.prov.source_url:
                fails.append(f"event {e.title!r} missing source_url")
            for ref in e.news_refs:
                if ref not in news_urls:
                    fails.append(f"event {e.title!r} cites non-input url {ref}")
        for a in ctx["alignments"]:
            if abs(a.lag_days) > window_days:
                fails.append(f"alignment {a.inflection.date} lag {a.lag_days} out of window")
        for p in ctx["artifacts"]:
            if not Path(p).exists():
                fails.append(f"artifact missing on disk: {p}")

        if fails:
            raise ValidationError("; ".join(fails))


def run_analysis(
    ticker: str = "NVDA",
    start: str = "",
    end: str = "",
    outputs: list[str] | None = None,
    *,
    client: LLMClient | None = None,
    cache: Any | None = None,
    clock: Callable[[], str] | None = None,
    out_dir: str = "artifacts",
    market_data_fn: MarketFn = market_data,
    news_fetch_fn: NewsFn = news_fetch,
) -> AnalysisResult:
    """Typed façade under the NL CLI (overview §2). Deterministic entrypoint every
    test targets. Injects the default backend when a client isn't supplied."""
    from .backend import default_client  # noqa: PLC0415 — avoid import cycle at module load

    start2, end2 = _default_range(start, end)
    return run(
        ticker, start2, end2, outputs or ["html"],
        client=client or default_client(), cache=cache, clock=clock, out_dir=out_dir,
        market_data_fn=market_data_fn, news_fetch_fn=news_fetch_fn,
    ).result


def run(
    ticker: str,
    start: str,
    end: str,
    outputs: list[str],
    *,
    client: LLMClient,
    cache: Any | None = None,
    clock: Callable[[], str] | None = None,
    out_dir: str = "artifacts",
    market_data_fn: MarketFn = market_data,
    news_fetch_fn: NewsFn = news_fetch,
    on_event: EventCb = None,
    should_cancel: Callable[[], bool] | None = None,
) -> RunResult:
    """Module-level convenience wrapper returning the full RunResult (used by the CLI/web)."""
    return Orchestrator().run(
        ticker, start, end, outputs, client=client, cache=cache, clock=clock,
        out_dir=out_dir, market_data_fn=market_data_fn, news_fetch_fn=news_fetch_fn,
        on_event=on_event, should_cancel=should_cancel,
    )


def _default_range(start: str, end: str) -> tuple[str, str]:
    """Empty dates default to the last ~5 years (the '近五年' brief)."""
    if start and end:
        return start, end
    today = datetime.now(UTC).date()
    e = end or today.isoformat()
    s = start or today.replace(year=today.year - 5).isoformat()
    return s, e
