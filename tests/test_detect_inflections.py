"""P2 tests for `detect_inflections` (T2.1–T2.9).

The deterministic core carries the repo's highest-coverage tests: golden values,
determinism, no-false-positives, gap classification, ranking, sensitivity,
traceability, and graceful edges.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from agent.models import Bar, InflectionKind, PriceSeries, Provenance
from agent.tools.detect_inflections import MIN_BARS, detect_inflections

FIX = Path(__file__).parent / "fixtures"
_PROV = Provenance("synthetic", "https://example.test/syn", "2025-01-01T00:00:00Z")


def _series(closes: list[float], start: str = "2023-01-02", ticker: str = "SYN") -> PriceSeries:
    d0 = date.fromisoformat(start)
    bars = [
        Bar((d0 + timedelta(days=i)).isoformat(), c, c * 1.01, c * 0.99, c, 1_000_000, _PROV)
        for i, c in enumerate(closes)
    ]
    return PriceSeries(ticker, bars, _PROV)


def _fixture() -> dict:
    return json.loads((FIX / "synthetic_prices.json").read_text(encoding="utf-8"))


# --- T2.1 golden values: exact dates + kinds -------------------------------- #
def test_golden_dates_and_kinds() -> None:
    fx = _fixture()
    result = detect_inflections(_series(fx["closes"], fx["start"], fx["ticker"]))
    got = {(inf.date, inf.kind.value) for inf in result}
    expected = {(e["date"], e["kind"]) for e in fx["expect"]}
    assert expected <= got, f"missing golden inflections: {expected - got}"
    # the trough is TURNING_UP, the gap day is BREAKOUT_UP, the peak is TURNING_DOWN
    kinds = {inf.kind for inf in result}
    assert InflectionKind.TURNING_UP in kinds
    assert InflectionKind.BREAKOUT_UP in kinds
    assert InflectionKind.TURNING_DOWN in kinds


# --- T2.2 determinism ------------------------------------------------------- #
def test_determinism() -> None:
    s = _series(_fixture()["closes"])
    a = detect_inflections(s)
    b = detect_inflections(s)
    assert [(i.date, i.kind, i.significance, i.evidence_bars) for i in a] == \
           [(i.date, i.kind, i.significance, i.evidence_bars) for i in b]


# --- T2.3 no false turning points on a monotonic ramp ----------------------- #
def test_monotonic_ramp_has_no_turning_points() -> None:
    result = detect_inflections(_series([100 + 2 * i for i in range(30)]))
    kinds = {i.kind for i in result}
    assert InflectionKind.TURNING_UP not in kinds
    assert InflectionKind.TURNING_DOWN not in kinds


# --- T2.4 sharp gap classified BREAKOUT_UP / BREAKDOWN ----------------------- #
def test_gap_up_is_breakout_and_gap_down_is_breakdown() -> None:
    base = [100.0] * 10
    up = base + [100.0 * 1.20] + [120.0] * 10       # +20% single-bar jump
    down = base + [100.0 * 0.80] + [80.0] * 10      # -20% single-bar drop
    up_kinds = {(i.date, i.kind) for i in detect_inflections(_series(up))}
    down_kinds = {i.kind for i in detect_inflections(_series(down))}
    assert any(k is InflectionKind.BREAKOUT_UP for _, k in up_kinds)
    assert InflectionKind.BREAKDOWN in down_kinds


# --- T2.5 ranking + top_n truncation ---------------------------------------- #
def test_ranking_and_top_n() -> None:
    s = _series(_fixture()["closes"])
    full = detect_inflections(s, top_n=25)
    sigs = [i.significance for i in full]
    assert sigs == sorted(sigs, reverse=True)          # significance desc
    assert all(0.0 <= x <= 1.0 for x in sigs)          # normalized
    top1 = detect_inflections(s, top_n=1)
    assert len(top1) == 1
    assert top1[0].date == full[0].date                # top_n is a prefix of the full ranking


# --- T2.6 sensitivity monotonicity ------------------------------------------ #
def test_sensitivity_monotonic() -> None:
    s = _series(_fixture()["closes"])
    counts = [len(detect_inflections(s, sensitivity=x)) for x in (0.5, 1.0, 2.0, 4.0)]
    assert counts == sorted(counts), f"count must be non-decreasing in sensitivity: {counts}"


# --- T2.7 traceability: evidence_bars non-empty, within window; detector set - #
def test_evidence_bars_and_detector() -> None:
    s = _series(_fixture()["closes"])
    for inf in detect_inflections(s):
        assert inf.evidence_bars, "evidence_bars must be non-empty"
        lo, hi = inf.window
        for d in inf.evidence_bars:
            assert lo <= d <= hi, f"evidence bar {d} outside window {inf.window}"
        assert "pen=" in inf.detector and "gap_k=" in inf.detector


# --- T2.8 empty / too-short series ------------------------------------------ #
def test_empty_and_short_series() -> None:
    assert detect_inflections(_series([])) == []
    assert detect_inflections(_series([10.0] * (MIN_BARS - 1))) == []


# --- T2.9 schema: kind enum, significance range, price == close of date ------ #
def test_output_schema() -> None:
    s = _series(_fixture()["closes"])
    by_date = {b.date: b.close for b in s.bars}
    for inf in detect_inflections(s):
        assert isinstance(inf.kind, InflectionKind)
        assert 0.0 <= inf.significance <= 1.0
        assert inf.price == by_date[inf.date]
