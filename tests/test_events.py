"""P6 — the orchestrator's on_event instrumentation (feeds the live dashboard).
No web server involved; pure Harness."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent.orchestrator import run
from tests.integration_fixtures import FROZEN, fixture_market_data, fixture_news, stub_llm


def test_on_event_streams_the_loop(tmp_path: Path) -> None:
    events: list[dict[str, Any]] = []
    run(
        "NVDA", "2023-05-01", "2023-05-25", ["html"],
        client=stub_llm(), clock=lambda: FROZEN, out_dir=str(tmp_path),
        market_data_fn=fixture_market_data, news_fetch_fn=fixture_news,
        on_event=events.append,
    )
    types = [e["type"] for e in events]

    # plan first, result last-ish; every step gets an act→observe pair in order.
    assert types[0] == "plan"
    assert "result" in types and "validate" in types
    acts = [e["step"] for e in events if e["type"] == "act"]
    observes = [e["step"] for e in events if e["type"] == "observe"]
    assert acts == observes  # every acted step was observed, same order
    assert acts[0] == "fetch market data"
    assert "render deliverables" in acts

    # observe details carry the step summaries the dashboard shows.
    detail = {e["step"]: e["detail"] for e in events if e["type"] == "observe"}
    assert "bars" in detail["fetch market data"]
    assert "inflections" in detail["detect price inflections"]

    result = next(e for e in events if e["type"] == "result")
    assert result["ticker"] == "NVDA" and result["bars"] > 0


def test_on_event_reports_retries(tmp_path: Path) -> None:
    from tests.integration_fixtures import flaky_market_data  # noqa: PLC0415

    events: list[dict[str, Any]] = []
    run(
        "NVDA", "2023-05-01", "2023-05-25", ["html"],
        client=stub_llm(), clock=lambda: FROZEN, out_dir=str(tmp_path),
        market_data_fn=flaky_market_data(), news_fetch_fn=fixture_news,
        on_event=events.append,
    )
    retries = [e for e in events if e["type"] == "retry"]
    assert len(retries) == 1
    assert retries[0]["step"] == "fetch market data"
