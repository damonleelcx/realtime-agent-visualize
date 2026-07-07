"""P5 integration tests — determinism, retry, termination, degradation, CLI
(T5.7–T5.11)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from agent.orchestrator import TerminationError, run
from tests.integration_fixtures import (
    FROZEN,
    always_fails_market_data,
    empty_news,
    fixture_market_data,
    fixture_news,
    flaky_market_data,
    stub_llm,
)


def _core(rr: object) -> object:
    r = rr.result  # type: ignore[attr-defined]
    return (
        [(b.date, b.close) for b in r.series.bars],
        [(i.date, i.kind.value, i.significance) for i in r.inflections],
        [(a.inflection.date, a.lag_days, a.confidence) for a in r.alignments],
    )


# --- T5.7 determinism under a frozen clock -------------------------------- #
def test_two_runs_are_deterministic(tmp_path: Path) -> None:
    kw = dict(client=stub_llm(), clock=lambda: FROZEN,
              market_data_fn=fixture_market_data, news_fetch_fn=fixture_news)
    a = run("NVDA", "2023-05-01", "2023-05-25", ["html"], out_dir=str(tmp_path / "a"), **kw)
    b = run("NVDA", "2023-05-01", "2023-05-25", ["html"], out_dir=str(tmp_path / "b"), **kw)
    assert _core(a) == _core(b)
    assert a.result.generated_at == b.result.generated_at == FROZEN


# --- T5.8 retry path recovers from a transient failure -------------------- #
def test_retry_recovers_from_transient_failure(tmp_path: Path) -> None:
    rr = run(
        "NVDA", "2023-05-01", "2023-05-25", ["html"],
        client=stub_llm(), clock=lambda: FROZEN, out_dir=str(tmp_path),
        market_data_fn=flaky_market_data(), news_fetch_fn=fixture_news,
    )
    assert rr.result.series.bars and rr.result.alignments  # completed despite one failure


# --- T5.9 termination cap fails cleanly on a wedged step ------------------ #
def test_wedged_step_hits_termination_cap(tmp_path: Path) -> None:
    with pytest.raises(TerminationError):
        run(
            "NVDA", "2023-05-01", "2023-05-25", ["html"],
            client=stub_llm(), clock=lambda: FROZEN, out_dir=str(tmp_path),
            market_data_fn=always_fails_market_data, news_fetch_fn=fixture_news,
        )


# --- T5.10 graceful degradation when no news is sourced ------------------- #
def test_empty_news_degrades_gracefully(tmp_path: Path) -> None:
    rr = run(
        "NVDA", "2023-05-01", "2023-05-25", ["html"],
        client=stub_llm(), clock=lambda: FROZEN, out_dir=str(tmp_path),
        market_data_fn=fixture_market_data, news_fetch_fn=empty_news,
    )
    assert rr.result.events == []
    assert rr.result.alignments == []
    assert rr.result.inflections  # K-line data still present
    html = Path(next(p for p in rr.artifacts if p.endswith(".html"))).read_text(encoding="utf-8")
    assert "No industry events were sourced" in html


# --- T5.11 CLI smoke (plan-only, offline) --------------------------------- #
def test_cli_plan_only_exits_zero() -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "agent.run", "Analyze NVDA over the last 5 years", "--plan-only"],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert "PLAN:" in proc.stdout
    assert "detect price inflections" in proc.stdout
