"""Backend selection — the SDK↔fallback swap boundary (docs/phases/P5, overview §6).

The orchestrator depends only on the `LLMClient` protocol. The concrete backend
is chosen here, so swapping the Claude Agent SDK for the bare-API path (or vice
versa) is a one-module change — the tool/subagent/skill boundaries are ours, not
the SDK's, so nothing above this line moves.

Default backend is the bare-API `AnthropicClient` (Messages API + structured
output). To run on the Claude Agent SDK instead, implement an `LLMClient` here
that drives it and return that from `default_client()`.
"""

from __future__ import annotations

from .llm import AnthropicClient, LLMClient


def default_client() -> LLMClient:
    """The LLM backend used when a caller doesn't inject one (real runs)."""
    return AnthropicClient()
