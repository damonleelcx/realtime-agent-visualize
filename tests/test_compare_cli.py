"""CLI for the comparison entrypoint (agent/compare_run.py), offline."""

from __future__ import annotations

from functools import partial
from pathlib import Path

import agent.compare_run as cli
from tests.comparison_fixtures import market_data_stub


def test_plan_only_prints_plan_no_network(capsys) -> None:
    rc = cli.main(["--tickers", "GC=F,BTC-USD", "--plan-only"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "COMPARISON: Gold vs Bitcoin" in out
    assert "PLAN:" in out
    assert "WEIGHTS: GC=F 50%, BTC-USD 50%" in out
    assert "not executing" in out


def test_full_run_writes_artifacts(tmp_path, monkeypatch) -> None:
    # Inject the offline stub by binding market_data_fn on the real pipeline call.
    monkeypatch.setattr(cli, "run_comparison",
                        partial(cli.run_comparison, market_data_fn=market_data_stub()))
    rc = cli.main([
        "--tickers", "GC=F,BTC-USD", "--start", "2023-01-02", "--end", "2023-06-01",
        "--outputs", "html,xlsx", "--out-dir", str(tmp_path),
    ])
    assert rc == 0
    written = {p.suffix for p in Path(tmp_path).iterdir()}
    assert written == {".html", ".xlsx"}


def test_rejects_single_ticker() -> None:
    import pytest

    with pytest.raises(SystemExit):
        cli.main(["--tickers", "GC=F"])
