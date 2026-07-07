"""Harness / orchestration layer (docs/00-overview.md §5, docs/phases/P5).

P0 SCOPE: skeleton only. `plan()` returns a hard-coded checklist and `run()`
returns a well-formed but EMPTY AnalysisResult. No tools, subagents, or LLM
calls yet — those are wired in P1–P5. The shape of the Plan→Act→Observe→
Validate loop lives here so later phases fill in the body, not the frame.
"""

from __future__ import annotations

from datetime import UTC, datetime

from .models import AnalysisResult, PriceSeries, Provenance


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# Fixed checklist the real orchestrator will expand from a task string (P5).
_PLAN_STEPS = [
    "fetch market data (tool: market_data)",           # P1
    "fetch industry news (tool: news_fetch)",          # P1
    "detect price inflections (tool: detect_inflections)",  # P2
    "curate events + impact ratings (subagent: event_curator)",  # P3
    "align inflections ↔ events (subagent: signal_analyst)",     # P3
    "build deliverables (subagent: report_builder)",   # P4
    "validate provenance + artifacts, summarize",      # P5
]


class Orchestrator:
    """Stub harness. Later phases replace the body of `run()` with the loop."""

    def plan(self, task: str) -> list[str]:
        """Decompose a task into a checklist. P0: fixed steps (P5 makes it dynamic)."""
        return list(_PLAN_STEPS)

    def run(
        self,
        ticker: str = "NVDA",
        start: str = "",
        end: str = "",
        outputs: list[str] | None = None,
    ) -> AnalysisResult:
        """P0 stub: returns an empty, well-formed AnalysisResult (no work done)."""
        prov = Provenance(
            source="stub",
            source_url="https://example.invalid/p0-stub",
            fetched_at=_now_iso(),
            query=f"{ticker}:{start}:{end}",
            note="P0 scaffolding stub — no data fetched yet",
        )
        return AnalysisResult(
            ticker=ticker,
            range=(start, end),
            series=PriceSeries(ticker=ticker, bars=[], prov=prov),
            inflections=[],
            events=[],
            alignments=[],
            generated_at=_now_iso(),
        )


def run_analysis(
    ticker: str = "NVDA",
    start: str = "",
    end: str = "",
    outputs: list[str] | None = None,
) -> AnalysisResult:
    """Typed façade used by tests/CI (docs/00-overview.md §2).

    Sits under the natural-language CLI entrypoint. In later phases this is the
    single seam behind which the Claude Agent SDK backend or the bare-API
    fallback runs — callers never know which.
    """
    return Orchestrator().run(ticker=ticker, start=start, end=end, outputs=outputs)
