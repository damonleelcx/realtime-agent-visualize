"""Tests for the LLM client JSON parsing + truncation salvage (agent/llm.py)."""

from __future__ import annotations

import pytest

from agent.llm import SubagentError, _parse_json


def test_parses_well_formed_json() -> None:
    out = _parse_json('{"events": [{"title": "A"}, {"title": "B"}]}')
    assert [e["title"] for e in out["events"]] == ["A", "B"]


def test_salvages_truncated_array() -> None:
    # The model ran out of tokens mid-way through the 3rd object's string.
    truncated = '{"events": [{"title": "A", "impact": "high"}, {"title": "B"}, {"title": "C, unter'
    out = _parse_json(truncated)
    titles = [e["title"] for e in out["events"]]
    assert titles == ["A", "B"]  # complete objects kept, partial dropped


def test_salvages_truncated_at_first_object() -> None:
    out = _parse_json('{"alignments": [{"inflection_date": "2023-05-25", "conf')
    assert out == {"alignments": []}  # nothing complete yet → empty, not a crash


def test_unrecoverable_raises() -> None:
    with pytest.raises(SubagentError):
        _parse_json("not json at all <<<")
