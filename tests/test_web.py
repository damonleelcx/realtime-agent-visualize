"""P6 — the dashboard app builds and serves its UI.

Skipped automatically when the `web` extra (fastapi) isn't installed, so the
core CI (`pip install -e .[dev]`) stays green.
"""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from functools import partial  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

import agent.web.server as server  # noqa: E402
from agent.web.server import NullLLM, create_app  # noqa: E402
from tests.comparison_fixtures import market_data_stub  # noqa: E402


def test_index_serves_dashboard() -> None:
    client = TestClient(create_app())
    resp = client.get("/")
    assert resp.status_code == 200
    assert "realtime-agent-visualize" in resp.text
    assert "/api/run" in resp.text       # single-ticker SSE endpoint
    assert "/api/compare" in resp.text   # comparison SSE endpoint the UI calls


def test_null_llm_returns_empty() -> None:
    out = NullLLM().complete("sys", "user", {})
    assert out == {"events": [], "alignments": []}


def test_compare_endpoint_streams_offline(tmp_path, monkeypatch) -> None:
    # Inject the offline market_data stub into the comparison the server drives.
    monkeypatch.setattr(server, "run_comparison",
                        partial(server.run_comparison, market_data_fn=market_data_stub()))
    monkeypatch.setattr(server, "RUNS", tmp_path)
    client = TestClient(create_app())
    resp = client.get("/api/compare", params={
        "tickers": "GC=F,BTC-USD", "start": "2023-01-02", "end": "2023-06-01",
        "outputs": "html",
    })
    assert resp.status_code == 200
    body = resp.text
    assert "cmp_mode" in body            # comparison-specific opening event
    assert "cmp_result" in body          # metrics/backtests summary
    assert '"type": "artifacts"' in body
    assert '"type": "done"' in body
    assert '"type": "error"' not in body
