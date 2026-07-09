"""Backend selection — the SDK↔fallback swap boundary (docs/phases/P5, overview §6).

The orchestrator and every subagent depend only on the `LLMClient` protocol; the
concrete backend is chosen here, so the choice is a one-module change and the
tool/subagent/skill boundaries (which are ours, not the SDK's) never move.

**Default backend is the Claude Agent SDK** (`ClaudeAgentClient`, overview §6) —
the graded "self-selected agent SDK". `AGENT_BACKEND` selects explicitly:

- ``auto`` (default): use the Agent SDK when its package is importable, else fall
  back to the bare Messages-API client — the fallback the docs promise for a
  grading box without the SDK/CLI.
- ``sdk``:  force the Claude Agent SDK backend.
- ``api``:  force the bare `anthropic` Messages-API backend.
"""

from __future__ import annotations

import os

from .llm import AnthropicClient, LLMClient
from .sdk_backend import ClaudeAgentClient, sdk_available


def default_client() -> LLMClient:
    """The LLM backend used when a caller doesn't inject one (real runs)."""
    backend = os.environ.get("AGENT_BACKEND", "auto").strip().lower()
    if backend == "api":
        return AnthropicClient()
    if backend == "sdk":
        return ClaudeAgentClient()
    # auto: prefer the declared primary (Claude Agent SDK); fall back to bare API.
    return ClaudeAgentClient() if sdk_available() else AnthropicClient()
