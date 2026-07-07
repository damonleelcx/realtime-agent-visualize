"""Skill loader — reads a skill's SKILL.md on demand (docs/phases/P3, P4).

A skill packages reusable instructions/templates loaded only when a subagent
needs them, keeping that knowledge single-sourced and out of the parent context.
"""

from __future__ import annotations

from pathlib import Path

_SKILLS_DIR = Path(__file__).parent


def load_skill(name: str) -> str:
    """Return the SKILL.md text for `name` (e.g. 'event-align')."""
    path = _SKILLS_DIR / name / "SKILL.md"
    return path.read_text(encoding="utf-8")
