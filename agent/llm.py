"""LLM client boundary (docs/phases/P3).

The ONE seam behind which an LLM runs. Subagents depend on the `LLMClient`
protocol, never on a concrete backend — so CI runs against a deterministic stub
and production runs against Claude, with no change above this line.

Structured output is enforced at the API layer (`output_config.format` +
json_schema), so the model returns validated JSON and the subagent's boundary
checks operate on structured data, not free text.
"""

from __future__ import annotations

import json
import os
from typing import Any, Protocol

# Model IDs per the Anthropic model catalog (2026). Opus 4.8 is the default;
# override with AGENT_MODEL. Structured outputs are supported on this model.
DEFAULT_MODEL = os.environ.get("AGENT_MODEL", "claude-opus-4-8")


class SubagentError(RuntimeError):
    """The LLM returned malformed/unusable output after retries."""


class LLMClient(Protocol):
    """Returns a schema-validated JSON object for (system, user)."""

    def complete(self, system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]: ...


class AnthropicClient:
    """Production backend. Lazy-imports `anthropic` so the package imports
    without the `sdk` extra; only real runs need the dependency + a key.
    """

    def __init__(self, model: str = DEFAULT_MODEL, max_tokens: int = 8000) -> None:
        self.model = model
        self.max_tokens = max_tokens

    def complete(  # pragma: no cover
        self, system: str, user: str, schema: dict[str, Any]
    ) -> dict[str, Any]:
        import anthropic  # noqa: PLC0415

        client = anthropic.Anthropic()  # resolves ANTHROPIC_API_KEY or an `ant` profile
        try:
            resp = client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=system,
                output_config={"format": {"type": "json_schema", "schema": schema}},
                messages=[{"role": "user", "content": user}],
            )
            text = next(b.text for b in resp.content if b.type == "text")
            result = json.loads(text)
        except Exception as exc:  # noqa: BLE001
            raise SubagentError(f"anthropic completion failed: {exc}") from exc
        if not isinstance(result, dict):
            raise SubagentError("expected a JSON object from the model")
        return result
