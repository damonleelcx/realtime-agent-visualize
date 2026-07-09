"""Skill loader — reads and validates a skill package on demand (P3, P4).

A skill is a self-contained package (`<dir>/SKILL.md`) following the Anthropic
Agent Skills convention: YAML frontmatter (`name`, `description`) plus a Markdown
body of reusable instructions/templates, loaded only when a capability needs it
so that knowledge stays single-sourced and out of the parent context.

The loader ENFORCES the standard — a `SKILL.md` without valid frontmatter, or
whose `name` does not match its directory, is a `SkillError`, not a silent
free-text read. `discover_skills()` walks the package so CI can assert every
shipped skill conforms.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_SKILLS_DIR = Path(__file__).parent
_FRONTMATTER_RE = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*\r?\n?(.*)\Z", re.DOTALL)
_NAME_RE = re.compile(r"\A[a-z0-9]+(?:-[a-z0-9]+)*\Z")  # kebab-case, per the standard


class SkillError(RuntimeError):
    """A skill package is missing or does not conform to the standard."""


@dataclass(frozen=True)
class Skill:
    """A parsed, validated skill package."""

    name: str  # canonical kebab-case identifier (matches the directory)
    description: str  # what it is / when to use it (frontmatter)
    instructions: str  # the Markdown body, frontmatter stripped
    path: Path  # the SKILL.md this was read from


def _canonical(dir_name: str) -> str:
    """Directory name → the canonical kebab-case skill name (kline_viz → kline-viz)."""
    return dir_name.replace("_", "-")


def _parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Split ``---`` frontmatter from the body. Returns (fields, body).

    Deliberately a minimal `key: value` reader (no YAML dep): the standard's
    required fields are flat scalars, so this stays dependency-light while still
    rejecting a file that lacks a frontmatter block at all.
    """
    m = _FRONTMATTER_RE.match(text)
    if not m:
        raise SkillError("SKILL.md has no '---' frontmatter block")
    fields: dict[str, str] = {}
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition(":")
        if not sep:
            raise SkillError(f"malformed frontmatter line: {line!r}")
        fields[key.strip()] = value.strip().strip("'\"")
    return fields, m.group(2).strip()


def load_skill(dir_name: str) -> Skill:
    """Load, validate, and return the skill package in ``<skills>/<dir_name>``.

    ``dir_name`` is the on-disk directory (e.g. ``event-align``, ``kline_viz``);
    its frontmatter ``name`` must equal the canonical kebab form of that directory.
    """
    path = _SKILLS_DIR / dir_name / "SKILL.md"
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise SkillError(f"no such skill: {dir_name} (expected {path})") from exc

    fields, body = _parse_frontmatter(text)
    name = fields.get("name", "")
    description = fields.get("description", "")
    if not _NAME_RE.match(name):
        raise SkillError(f"skill {dir_name!r}: frontmatter 'name' must be kebab-case, got {name!r}")
    if name != _canonical(dir_name):
        raise SkillError(f"skill {dir_name!r}: frontmatter name {name!r} != directory")
    if not description:
        raise SkillError(f"skill {dir_name!r}: frontmatter 'description' is required")
    if not body:
        raise SkillError(f"skill {dir_name!r}: body (instructions) is empty")
    return Skill(name=name, description=description, instructions=body, path=path)


def discover_skills() -> list[Skill]:
    """Every valid skill package under the skills directory, ordered by name."""
    skills = [
        load_skill(child.name)
        for child in _SKILLS_DIR.iterdir()
        if child.is_dir() and (child / "SKILL.md").is_file()
    ]
    return sorted(skills, key=lambda s: s.name)
