"""Skill packages conform to the Agent Skills standard (agent/skills/loader.py).

These tests are the CI enforcement of the standard the loader parses: every
shipped SKILL.md must carry valid frontmatter whose kebab-case `name` matches its
directory, plus a non-empty description and body.
"""

from __future__ import annotations

import re

import pytest

from agent.skills.loader import Skill, SkillError, discover_skills, load_skill

_KEBAB = re.compile(r"\A[a-z0-9]+(?:-[a-z0-9]+)*\Z")


def test_every_shipped_skill_is_standard_conformant() -> None:
    skills = discover_skills()
    names = {s.name for s in skills}
    # All three first-class skills are discovered — not just the LLM one.
    assert {"event-align", "kline-viz", "office-export"} <= names
    for s in skills:
        assert isinstance(s, Skill)
        assert _KEBAB.match(s.name), s.name
        assert s.description.strip(), s.name
        assert s.instructions.strip(), s.name
        assert s.path.name == "SKILL.md"


def test_load_skill_maps_directory_to_canonical_name() -> None:
    # Underscore directories expose a hyphenated canonical name.
    assert load_skill("kline_viz").name == "kline-viz"
    assert load_skill("office_export").name == "office-export"
    assert load_skill("event-align").name == "event-align"


def test_load_skill_strips_frontmatter_from_instructions() -> None:
    skill = load_skill("event-align")
    assert not skill.instructions.startswith("---")
    assert "Alignment rules" in skill.instructions


def test_unknown_skill_raises() -> None:
    with pytest.raises(SkillError):
        load_skill("no-such-skill")


def test_missing_frontmatter_raises(tmp_path, monkeypatch) -> None:
    import agent.skills.loader as loader

    pkg = tmp_path / "bad_skill"
    pkg.mkdir()
    (pkg / "SKILL.md").write_text("# no frontmatter here\n\nbody", encoding="utf-8")
    monkeypatch.setattr(loader, "_SKILLS_DIR", tmp_path)
    with pytest.raises(SkillError):
        loader.load_skill("bad_skill")


def test_name_directory_mismatch_raises(tmp_path, monkeypatch) -> None:
    import agent.skills.loader as loader

    pkg = tmp_path / "widget"
    pkg.mkdir()
    (pkg / "SKILL.md").write_text(
        "---\nname: something-else\ndescription: x\n---\nbody\n", encoding="utf-8"
    )
    monkeypatch.setattr(loader, "_SKILLS_DIR", tmp_path)
    with pytest.raises(SkillError):
        loader.load_skill("widget")
