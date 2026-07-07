"""P5 aggregate invariant suite — P-INV-1..5 over a fixture end-to-end run
(T5.1–T5.6). This module owns the cross-cutting invariant checks."""

from __future__ import annotations

import re
from pathlib import Path

from agent.orchestrator import RunResult, run
from tests.integration_fixtures import (
    FROZEN,
    NEWS_URL,
    fixture_market_data,
    fixture_news,
    load_news,
    stub_llm,
)

_EXTERNAL = re.compile(r"<(?:script|link)\b[^>]*\b(?:src|href)\s*=\s*['\"]https?://", re.I)
_SECRET = re.compile(r"sk-[A-Za-z0-9]{16,}|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_\-]{20,}")


def _run(tmp_path: Path) -> RunResult:
    return run(
        "NVDA", "2023-05-01", "2023-05-25", ["html", "xlsx", "pptx", "docx"],
        client=stub_llm(), clock=lambda: FROZEN, out_dir=str(tmp_path),
        market_data_fn=fixture_market_data, news_fetch_fn=fixture_news,
    )


# --- T5.1 well-formed result + all four artifacts ------------------------- #
def test_end_to_end_produces_result_and_artifacts(tmp_path: Path) -> None:
    rr = _run(tmp_path)
    r = rr.result
    assert r.ticker == "NVDA"
    assert r.series.bars and r.inflections and r.events and r.alignments
    assert len(rr.artifacts) == 4
    exts = sorted(Path(p).suffix for p in rr.artifacts)
    assert exts == [".docx", ".html", ".pptx", ".xlsx"]
    for p in rr.artifacts:
        assert Path(p).exists()


# --- T5.2 P-INV-1 provenance completeness --------------------------------- #
def test_provenance_complete(tmp_path: Path) -> None:
    r = _run(tmp_path).result
    for b in r.series.bars:
        assert b.prov.source_url
    for e in r.events:
        assert e.prov.source_url
    for n in load_news():  # the NewsItems that fed the run
        assert n.prov.source_url


# --- T5.3 P-INV-2 citation integrity -------------------------------------- #
def test_citation_integrity(tmp_path: Path) -> None:
    r = _run(tmp_path).result
    news_urls = {n.url for n in load_news()}
    for e in r.events:
        for ref in e.news_refs:
            assert ref in news_urls
    for a in r.alignments:
        cited = re.findall(r"https?://[^\s)]+", a.explanation)
        for u in cited:
            assert u.rstrip(".,") in news_urls


# --- T5.4 P-INV-3 temporal sanity ----------------------------------------- #
def test_temporal_sanity(tmp_path: Path) -> None:
    from agent.subagents.signal_analyst import DEFAULT_WINDOW_DAYS  # noqa: PLC0415

    r = _run(tmp_path).result
    for a in r.alignments:
        assert abs(a.lag_days) <= DEFAULT_WINDOW_DAYS


# --- T5.5 P-INV-4 no secret in artifacts ---------------------------------- #
def test_no_secret_in_artifacts(tmp_path: Path) -> None:
    rr = _run(tmp_path)
    for p in rr.artifacts:
        text = Path(p).read_text(encoding="utf-8", errors="ignore")
        assert not _SECRET.search(text), f"key-shaped string in {p}"


# --- T5.6 P-INV-5 self-contained HTML ------------------------------------- #
def test_html_self_contained(tmp_path: Path) -> None:
    rr = _run(tmp_path)
    html_path = next(p for p in rr.artifacts if p.endswith(".html"))
    html = Path(html_path).read_text(encoding="utf-8")
    assert not _EXTERNAL.search(html)
    assert NEWS_URL in html  # the source is clickable in the drill-down
