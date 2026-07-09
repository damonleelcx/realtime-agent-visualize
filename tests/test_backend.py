"""Backend selection + Claude Agent SDK client seam (agent/backend.py, sdk_backend.py).

Offline: the SDK's `query()` (a CLI subprocess) is never invoked — we monkeypatch
the client's `_query` and the availability probe, so these run with no network,
no key, and no Claude Code CLI.
"""

from __future__ import annotations

import asyncio

import agent.backend as backend
from agent.llm import AnthropicClient
from agent.sdk_backend import ClaudeAgentClient, _run_sync, sdk_available


def test_default_is_agent_sdk_when_available(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_BACKEND", "auto")
    monkeypatch.setattr(backend, "sdk_available", lambda: True)
    assert isinstance(backend.default_client(), ClaudeAgentClient)


def test_auto_falls_back_to_bare_api_without_sdk(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_BACKEND", "auto")
    monkeypatch.setattr(backend, "sdk_available", lambda: False)
    assert isinstance(backend.default_client(), AnthropicClient)


def test_explicit_backend_override(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_BACKEND", "api")
    assert isinstance(backend.default_client(), AnthropicClient)
    monkeypatch.setenv("AGENT_BACKEND", "sdk")
    assert isinstance(backend.default_client(), ClaudeAgentClient)


def test_sdk_available_true_when_package_installed() -> None:
    # The `sdk` extra is installed in this env; the probe must see it.
    assert sdk_available() is True


def test_complete_embeds_schema_and_parses(monkeypatch) -> None:
    captured: dict[str, str] = {}

    async def fake_query(self: ClaudeAgentClient, system_prompt: str, user: str) -> str:
        captured["system"] = system_prompt
        return '{"events": [{"title": "A"}]}'

    monkeypatch.setattr(ClaudeAgentClient, "_query", fake_query)
    out = ClaudeAgentClient().complete("SYS", "USER", {"type": "object"})
    assert out == {"events": [{"title": "A"}]}
    # The JSON schema is injected into the system prompt for the SDK path.
    assert '"type": "object"' in captured["system"]
    assert "JSON Schema" in captured["system"]


def test_run_sync_works_inside_a_running_loop() -> None:
    async def caller() -> str:
        # _run_sync must not touch the already-running loop; it uses a worker.
        async def coro() -> str:
            return "ok"

        return _run_sync(coro())

    assert asyncio.run(caller()) == "ok"
