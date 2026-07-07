"""`artifact_io` tool — read/write deliverable files (docs/phases/P4).

Deterministic, no LLM, no network. The single seam through which the
report_builder writes artifacts, so paths and directory creation are consistent.
"""

from __future__ import annotations

from pathlib import Path


def write(path: str | Path, data: bytes | str) -> str:
    """Write bytes or text to `path` (creating parents); return the absolute path."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, str):
        p.write_text(data, encoding="utf-8")
    else:
        p.write_bytes(data)
    return str(p.resolve())


def read(path: str | Path) -> bytes:
    return Path(path).read_bytes()
