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
from ..skills.office_export import to_docx, to_pptx, to_xlsx
from ..tools import artifact_io

# format -> (extension, builder returning str|bytes)
_BUILDERS: dict[str, tuple[str, Callable[[AnalysisResult], str | bytes]]] = {
    "html": ("html", render_html),
    "xlsx": ("xlsx", to_xlsx),
    "pptx": ("pptx", to_pptx),
    "docx": ("docx", to_docx),
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
        ext, build = entry
        data = build(result)
        path = artifact_io.write(f"{out_dir}/{result.ticker}_analysis.{ext}", data)
        paths.append(path)
    return paths
