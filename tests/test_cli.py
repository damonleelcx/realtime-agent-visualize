"""P0 test T0.3: the CLI runs end-to-end and emits a plan + well-formed result."""

from __future__ import annotations

import json
import subprocess
import sys

from agent.models import AnalysisResult
from agent.orchestrator import Orchestrator, run_analysis


def test_cli_exits_zero_and_prints_plan_and_result() -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "agent.run", "Analyze NVDA over 5 years"],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert "PLAN:" in proc.stdout
    assert "RESULT" in proc.stdout

    # The JSON block after the RESULT header must parse into a valid AnalysisResult.
    json_start = proc.stdout.index("{", proc.stdout.index("RESULT"))
    payload = proc.stdout[json_start:]
    result = AnalysisResult.from_dict(json.loads(payload))
    assert result.ticker == "NVDA"


def test_plan_has_expected_steps() -> None:
    steps = Orchestrator().plan("anything")
    assert len(steps) >= 5
    joined = " ".join(steps).lower()
    for expected in ["market", "news", "inflection", "event", "deliverable"]:
        assert expected in joined


def test_run_analysis_facade_returns_empty_wellformed_result() -> None:
    result = run_analysis(ticker="NVDA", start="2020-07-01", end="2025-07-01")
    assert result.ticker == "NVDA"
    assert result.range == ("2020-07-01", "2025-07-01")
    assert result.series.bars == []
    assert result.inflections == []
    # Even the stub must carry non-empty provenance (P-INV-1 posture from day one).
    assert result.series.prov.source_url
