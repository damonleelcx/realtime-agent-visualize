"""Claude Agent SDK backend — the declared primary LLM backend (overview §6).

`ClaudeAgentClient` drives the **Claude Agent SDK** (`claude_agent_sdk.query`)
behind the same `LLMClient.complete()` seam the bare-API path uses. The SDK runs
the agent loop (a Claude Code CLI subprocess); we constrain it to a single,
tool-free turn and ask for schema-conforming JSON, then reuse the shared
parse/salvage from `llm.py` so the subagents' trust boundaries operate on
structured data exactly as they do on the bare-API path.

The SDK is async and `complete()` is synchronous (subagents are synchronous), so
we drive the one-shot query on a private event loop — isolated in a worker thread
when the caller already holds a running loop (e.g. the FastAPI dashboard).
"""

from __future__ import annotations

import asyncio
import json
import threading
from typing import Any

from .llm import DEFAULT_MODEL, SubagentError, _parse_json


def sdk_available() -> bool:
    """True when the Claude Agent SDK package is importable.

    The SDK additionally needs the Claude Code CLI at run time; if it is missing,
    `complete()` raises `SubagentError` and `default_client()`'s `auto` mode has
    already preferred this backend, so a real run surfaces the cause explicitly
    rather than silently degrading.
    """
    try:
        import claude_agent_sdk  # noqa: F401, PLC0415
    except ImportError:
        return False
    return True


_JSON_INSTRUCTION = (
    "\n\nOutput ONLY a single JSON object that validates against this JSON Schema. "
    "No prose, no markdown fences, no commentary — emit just the JSON object.\n"
    "JSON Schema:\n"
)


class ClaudeAgentClient:
    """Production backend on the Claude Agent SDK.

    Constrains the agent to one tool-free turn returning schema-shaped JSON, so
    every subagent sees the same structured contract as with the bare-API path.
    """

    def __init__(self, model: str = DEFAULT_MODEL, max_turns: int = 1) -> None:
        self.model = model
        self.max_turns = max_turns

    def complete(  # pragma: no cover - needs the SDK CLI + network
        self, system: str, user: str, schema: dict[str, Any]
    ) -> dict[str, Any]:
        system_prompt = system + _JSON_INSTRUCTION + json.dumps(schema)
        text = _run_sync(self._query(system_prompt, user))
        return _parse_json(text)

    async def _query(self, system_prompt: str, user: str) -> str:  # pragma: no cover
        from claude_agent_sdk import (  # noqa: PLC0415
            AssistantMessage,
            ClaudeAgentOptions,
            TextBlock,
            query,
        )

        options = ClaudeAgentOptions(
            model=self.model,
            system_prompt=system_prompt,
            max_turns=self.max_turns,
            allowed_tools=[],  # pure completion — the agent may not call tools
            permission_mode="bypassPermissions",
            setting_sources=[],  # ignore ambient user/project settings for determinism
        )
        parts: list[str] = []
        try:
            async for msg in query(prompt=user, options=options):
                if isinstance(msg, AssistantMessage):
                    parts.extend(b.text for b in msg.content if isinstance(b, TextBlock))
        except Exception as exc:  # noqa: BLE001
            raise SubagentError(f"claude agent sdk query failed: {exc}") from exc
        text = "".join(parts).strip()
        if not text:
            raise SubagentError("claude agent sdk returned no text output")
        return text


def _run_sync(coro: Any) -> str:  # pragma: no cover - exercised only on real runs
    """Await `coro` to completion from synchronous code.

    Uses `asyncio.run` when no loop is running; otherwise runs it on a private
    loop in a worker thread so we never touch a foreign running loop.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return _await(coro)

    box: dict[str, Any] = {}

    def worker() -> None:
        try:
            box["value"] = _await(coro)
        except BaseException as exc:  # noqa: BLE001
            box["error"] = exc

    thread = threading.Thread(target=worker, name="claude-agent-sdk")
    thread.start()
    thread.join()
    if "error" in box:
        raise box["error"]
    return str(box["value"])


def _await(coro: Any) -> str:  # pragma: no cover
    result: str = asyncio.run(coro)
    return result
