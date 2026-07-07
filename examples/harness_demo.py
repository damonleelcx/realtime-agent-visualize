"""Exercise the agent Harness (agent/orchestrator.py) end-to-end, offline.

Runs the Plan → Act → Observe → Validate → Retry loop through every behavior it
is designed for — with fake tools + a stub LLM, so there is NO network and NO
API key involved. Nothing is written into the repo (a temp dir is used).

    source .venv/bin/activate
    pip install -e ".[dev]"          # numpy/ruptures/openpyxl/pptx/docx
    python examples/harness_demo.py

Each scenario prints PASS/FAIL; the script exits non-zero if any fail.
"""

from __future__ import annotations

import re
import shutil
import tempfile
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from agent.models import Bar, InflectionKind, NewsItem, PriceSeries, Provenance
from agent.orchestrator import (
    DEFAULT_WINDOW_DAYS,
    TerminationError,
    ValidationError,
    run,
)
from agent.tools import detect_inflections
from agent.tools.errors import DataSourceError

FROZEN = "2025-01-01T00:00:00Z"
START, END = "2023-05-01", "2023-05-25"
NEWS_URL = "https://nvidianews.example.com/q1-fy24"
_EXTERNAL = re.compile(r"<(?:script|link)\b[^>]*\b(?:src|href)\s*=\s*['\"]https?://", re.I)


# --------------------------------------------------------------------------- #
# Fake data + fake tools (the seams the Harness exposes for testing)
# --------------------------------------------------------------------------- #
def build_series(ticker: str = "NVDA") -> PriceSeries:
    # 15 flat days, a +20% gap up, then flat → one unambiguous BREAKOUT_UP.
    closes = [30.0] * 15 + [36.0] * 10
    prov = Provenance("yahoo", f"https://finance.yahoo.com/quote/{ticker}/history", FROZEN, ticker)
    d0 = date.fromisoformat(START)
    bars = [
        Bar((d0 + timedelta(days=i)).isoformat(), c, c * 1.01, c * 0.99, c, 1_000_000, prov)
        for i, c in enumerate(closes)
    ]
    return PriceSeries(ticker, bars, prov)


def good_market(ticker: str, start: str, end: str, **_kw: Any) -> PriceSeries:
    return build_series(ticker)


def flaky_market() -> Any:
    """Fails once (transient), then succeeds — to exercise Retry."""
    state = {"n": 0}

    def fn(ticker: str, start: str, end: str, **_kw: Any) -> PriceSeries:
        state["n"] += 1
        if state["n"] == 1:
            raise DataSourceError("transient outage")
        return build_series(ticker)

    return fn


def wedged_market(ticker: str, start: str, end: str, **_kw: Any) -> PriceSeries:
    """Always fails — to exercise the Termination cap."""
    raise DataSourceError("wedged source")


def good_news(query: str, start: str, end: str, **_kw: Any) -> list[NewsItem]:
    prov = Provenance("hackernews", NEWS_URL, FROZEN, "NVDA")
    return [NewsItem("NVIDIA reports blowout Q1 FY24 data-center revenue",
                     NEWS_URL, "2023-05-15", "Record AI data-center guidance.", prov)]


def empty_news(query: str, start: str, end: str, **_kw: Any) -> list[NewsItem]:
    return []


class StubLLM:
    """Deterministic LLM: returns fixed structured objects; records calls."""

    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((system, user))
        return self.response


def stub_llm() -> StubLLM:
    # The alignment must reference the inflection the detector actually finds.
    infl = detect_inflections(build_series())
    breakout = next(i.date for i in infl if i.kind is InflectionKind.BREAKOUT_UP)
    return StubLLM({
        "events": [{
            "title": "NVIDIA reports blowout Q1 FY24 data-center revenue",
            "date": "2023-05-15", "category": "earnings", "impact": "high",
            "rationale": "Record data-center revenue guidance drove the breakout.",
            "news_refs": [NEWS_URL],
        }],
        "alignments": [{
            "inflection_date": breakout, "event_indices": [0], "confidence": 0.9,
            "explanation": f"The breakout aligns with the earnings beat. See {NEWS_URL}",
        }],
    })


def _run(out_dir: str, *, market: Any = good_market, news: Any = good_news,
         outputs: list[str] | None = None) -> Any:
    return run(
        "NVDA", START, END, outputs or ["html", "xlsx", "pptx", "docx"],
        client=stub_llm(), clock=lambda: FROZEN, out_dir=out_dir,
        market_data_fn=market, news_fetch_fn=news,
    )


# --------------------------------------------------------------------------- #
# Scenarios
# --------------------------------------------------------------------------- #
def scenario_happy_path(work: Path) -> None:
    rr = _run(str(work / "happy"))
    r = rr.result
    print("    plan:", " → ".join(s.split(" (")[0] for s in rr.plan))
    print(f"    bars={len(r.series.bars)} inflections={len(r.inflections)} "
          f"events={len(r.events)} alignments={len(r.alignments)}")
    assert r.series.bars and r.inflections and r.events and r.alignments
    assert len(rr.artifacts) == 4 and all(Path(p).exists() for p in rr.artifacts)


def scenario_determinism(work: Path) -> None:
    def core(rr: Any) -> Any:
        r = rr.result
        return ([(b.date, b.close) for b in r.series.bars],
                [(i.date, i.kind.value, i.significance) for i in r.inflections],
                [(a.inflection.date, a.lag_days, a.confidence) for a in r.alignments])

    a = _run(str(work / "det_a"), outputs=["html"])
    b = _run(str(work / "det_b"), outputs=["html"])
    assert core(a) == core(b), "deterministic core differs between runs"
    assert a.result.generated_at == b.result.generated_at == FROZEN
    print("    two frozen-clock runs produced an identical deterministic core")


def scenario_retry(work: Path) -> None:
    rr = _run(str(work / "retry"), market=flaky_market(), outputs=["html"])
    assert rr.result.series.bars and rr.result.alignments
    print("    market_data failed once, Harness retried with feedback and completed")


def scenario_termination(work: Path) -> None:
    try:
        _run(str(work / "term"), market=wedged_market, outputs=["html"])
    except TerminationError as exc:
        print(f"    wedged step failed cleanly: {exc}")
        return
    raise AssertionError("expected TerminationError, got a completed run")


def scenario_degradation(work: Path) -> None:
    rr = _run(str(work / "degrade"), news=empty_news, outputs=["html"])
    assert rr.result.events == [] and rr.result.alignments == []
    assert rr.result.inflections, "K-line data should still be present"
    html = Path(next(p for p in rr.artifacts if p.endswith(".html"))).read_text(encoding="utf-8")
    assert "No industry events were sourced" in html
    print("    empty news → K-line + inflections still rendered, events empty, note shown")


def scenario_invariants(work: Path) -> None:
    """The Validate step's guarantees, re-checked on the produced artifacts."""
    rr = _run(str(work / "inv"))
    r = rr.result
    news_urls = {n.url for n in good_news("", "", "")}
    # P-INV-1 provenance completeness
    assert all(b.prov.source_url for b in r.series.bars)
    assert all(e.prov.source_url for e in r.events)
    # P-INV-2 citation integrity
    assert all(ref in news_urls for e in r.events for ref in e.news_refs)
    # P-INV-3 temporal sanity
    assert all(abs(a.lag_days) <= DEFAULT_WINDOW_DAYS for a in r.alignments)
    # P-INV-4 no secret in artifacts  P-INV-5 self-contained HTML
    secret = re.compile(r"sk-[A-Za-z0-9]{16,}|AKIA[0-9A-Z]{16}")
    for p in rr.artifacts:
        text = Path(p).read_text(encoding="utf-8", errors="ignore")
        assert not secret.search(text)
        if p.endswith(".html"):
            assert not _EXTERNAL.search(text)
    print("    P-INV-1..5 all hold on the produced result + artifacts")


def scenario_validate_gate_raises(work: Path) -> None:
    """Prove the Validate gate actually rejects a bad run (missing artifact)."""
    from agent.orchestrator import Orchestrator  # noqa: PLC0415

    orch = Orchestrator()
    ctx = {
        "series": build_series(),
        "news": good_news("", "", ""),
        "events": [],
        "alignments": [],
        "artifacts": ["/tmp/definitely-does-not-exist-xyz.html"],
    }
    try:
        orch._validate(ctx, ["html"], DEFAULT_WINDOW_DAYS)  # noqa: SLF001 — demo of the gate
    except ValidationError as exc:
        print(f"    Validate gate rejected a missing artifact: {exc}")
        return
    raise AssertionError("expected ValidationError for a missing artifact")


SCENARIOS = [
    ("Happy path — Plan→Act→Observe→render→Validate", scenario_happy_path),
    ("Determinism (frozen clock)", scenario_determinism),
    ("Retry — recover from a transient tool failure", scenario_retry),
    ("Termination — wedged step hits the cap", scenario_termination),
    ("Graceful degradation — empty news", scenario_degradation),
    ("Invariants P-INV-1..5 on the result", scenario_invariants),
    ("Validate gate rejects a bad run", scenario_validate_gate_raises),
]


def main() -> int:
    work = Path(tempfile.mkdtemp(prefix="harness_demo_"))
    passed = 0
    print(f"Harness demo — artifacts in {work}\n")
    try:
        for name, fn in SCENARIOS:
            print(f"[ .. ] {name}")
            try:
                fn(work)
                print(f"[PASS] {name}\n")
                passed += 1
            except Exception as exc:  # noqa: BLE001 — demo harness
                print(f"[FAIL] {name}: {exc}\n")
    finally:
        shutil.rmtree(work, ignore_errors=True)

    total = len(SCENARIOS)
    print(f"==> {passed}/{total} scenarios passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
