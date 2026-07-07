"""P6 — the dashboard app builds and serves its UI.

Skipped automatically when the `web` extra (fastapi) isn't installed, so the
core CI (`pip install -e .[dev]`) stays green.
"""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from agent.web.server import NullLLM, create_app  # noqa: E402


def test_index_serves_dashboard() -> None:
    client = TestClient(create_app())
    resp = client.get("/")
    assert resp.status_code == 200
    assert "realtime-agent-visualize" in resp.text
    assert "/api/run" in resp.text  # the SSE endpoint the UI calls


def test_null_llm_returns_empty() -> None:
    out = NullLLM().complete("sys", "user", {})
    assert out == {"events": [], "alignments": []}
