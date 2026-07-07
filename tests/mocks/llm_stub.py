"""Deterministic stub LLM for offline, reproducible subagent tests (P3 T3.8).

Returns a fixed structured object and records every call, so tests assert on the
subagent's boundary behavior — not on model prose.
"""

from __future__ import annotations

from typing import Any


class StubLLM:
    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((system, user))
        return self.response
