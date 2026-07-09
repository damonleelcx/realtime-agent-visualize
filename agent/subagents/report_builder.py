"""`report_builder` (docs/phases/P4).

Orchestrates the render skills to emit the requested deliverables from one
AnalysisResult and returns their absolute paths. It RENDERS ONLY — no fetch, no
recompute, no LLM, no network. Unknown/empty `outputs` → [] (no-op).

Note: despite living under subagents/, this is a deterministic dispatcher — the
judgement-bearing LLM work already happened in P3. It is grouped here because it
is the capability that assembles the final deliverables.
"""

from __future__ import annotations

from collections.abc import Callable

from ..models import AnalysisResult
from ..skills.kline_viz import render_html
from ..skills.loader import load_skill
from ..skills.office_export import to_docx, to_pptx, to_xlsx
from ..tools import artifact_io

# format -> (skill package dir, extension, builder returning str|bytes). Each
# render skill is loaded from its SKILL.md at dispatch, so the office/html skills
# are first-class packages the harness consults at run time — not name-only dirs.
_BUILDERS: dict[str, tuple[str, str, Callable[[AnalysisResult], str | bytes]]] = {
    "html": ("kline_viz", "html", render_html),
    "xlsx": ("office_export", "xlsx", to_xlsx),
    "pptx": ("office_export", "pptx", to_pptx),
    "docx": ("office_export", "docx", to_docx),
}


def report_builder(
    result: AnalysisResult,
    outputs: list[str],
    *,
    out_dir: str = "artifacts",
) -> list[str]:
    """Write each requested deliverable and return the absolute paths."""
    paths: list[str] = []
    for fmt in outputs:
        entry = _BUILDERS.get(fmt)
        if entry is None:
            continue
        skill_dir, ext, build = entry
        load_skill(skill_dir)  # enforce the render skill's package/contract exists
        data = build(result)
        path = artifact_io.write(f"{out_dir}/{result.ticker}_analysis.{ext}", data)
        paths.append(path)
    return paths
