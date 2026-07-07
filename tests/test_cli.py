"""CLI / plan wiring tests (the P0 empty-stub behavior is superseded by P5;
full pipeline coverage lives in test_integration.py / test_invariants.py)."""

from __future__ import annotations

import subprocess
import sys

from agent.orchestrator import Orchestrator


def test_cli_plan_only_exits_zero_and_prints_plan() -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "agent.run", "Analyze NVDA over 5 years", "--plan-only"],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert "PLAN:" in proc.stdout
    assert "TASK:" in proc.stdout


def test_plan_has_expected_steps() -> None:
    steps = Orchestrator().plan("anything")
    assert len(steps) >= 5
    joined = " ".join(steps).lower()
    for expected in ["market", "news", "inflection", "event", "deliverable"]:
        assert expected in joined
