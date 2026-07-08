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
import re
from typing import Any, Protocol

# Model IDs per the Anthropic model catalog (2026). Opus 4.8 is the default;
# override with AGENT_MODEL. Structured outputs are supported on this model.
DEFAULT_MODEL = os.environ.get("AGENT_MODEL", "claude-opus-4-8")
# Generous output headroom — curating many events emits large JSON. 16k stays
# under the SDK's non-streaming timeout guard. Override with AGENT_MAX_TOKENS.
DEFAULT_MAX_TOKENS = int(os.environ.get("AGENT_MAX_TOKENS", "16000"))


class SubagentError(RuntimeError):
    """The LLM returned malformed/unusable output after retries."""


class LLMClient(Protocol):
    """Returns a schema-validated JSON object for (system, user)."""

    def complete(self, system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]: ...


def _parse_json(text: str) -> dict[str, Any]:
    """Parse the model's JSON, salvaging a response truncated at `max_tokens`.

    Structured output is `{"<key>": [ {...}, {...}, ... ]}`. If the last object
    was cut off mid-write (Unterminated string), keep the complete objects and
    close the array — better a partial, valid result than dropping everything.
    """
    text = text.strip()
    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        result = _salvage(text)
    if not isinstance(result, dict):
        raise SubagentError("expected a JSON object from the model")
    return result


def _salvage(text: str) -> dict[str, Any]:
    m = re.match(r'\s*\{\s*"(\w+)"\s*:\s*\[', text)
    if not m:
        raise SubagentError("model output was not parseable JSON and could not be salvaged")
    key, start = m.group(1), m.end()
    depth = last_close = 0
    in_str = esc = False
    for i in range(start, len(text)):
        c = text[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                last_close = i
    if not last_close:
        return {key: []}
    try:
        return dict(json.loads(text[: last_close + 1] + "]}"))
    except json.JSONDecodeError as exc:
        raise SubagentError(f"could not salvage truncated model output: {exc}") from exc


class AnthropicClient:
    """Production backend. Lazy-imports `anthropic` so the package imports
    without the `sdk` extra; only real runs need the dependency + a key.
    """

    def __init__(self, model: str = DEFAULT_MODEL, max_tokens: int = DEFAULT_MAX_TOKENS) -> None:
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
        except Exception as exc:  # noqa: BLE001
            raise SubagentError(f"anthropic completion failed: {exc}") from exc
        return _parse_json(text)
