"""P3 tests for `signal_analyst` (T3.5, T3.6, T3.7, plus lag/confidence)."""

from __future__ import annotations

from agent.models import CuratedEvent, Impact, Inflection, InflectionKind, Provenance
from agent.subagents import signal_analyst
from agent.subagents.signal_analyst import enforce_alignments
from tests.mocks.llm_stub import StubLLM

_PROV = Provenance("curated", "https://openai.com/blog/chatgpt", "2025-01-01T00:00:00Z", "NVDA")


def _inflection(date: str) -> Inflection:
    return Inflection(
        date=date, kind=InflectionKind.BREAKOUT_UP, significance=1.0, price=100.0,
        window=(date, date), evidence_bars=[date], detector="pelt:rbf:pen=8",
    )


def _event(date: str, url: str = "https://openai.com/blog/chatgpt") -> CuratedEvent:
    return CuratedEvent(
        title="ChatGPT launch", date=date, category="model_release",
        impact=Impact.HIGH, rationale="demand cycle", news_refs=[url], prov=_PROV,
    )


# --- T3.5 temporal sanity (P-INV-3) --------------------------------------- #
def test_in_window_alignment_kept_with_recomputed_lag() -> None:
    infl = _inflection("2023-01-20")
    ev = _event("2023-01-10")  # 10 days before → within window
    stub = StubLLM({"alignments": [{
        "inflection_date": "2023-01-20", "event_indices": [0],
        "confidence": 0.8, "explanation": "See https://openai.com/blog/chatgpt",
    }]})
    aligns = signal_analyst([infl], [ev], client=stub, window_days=45)
    assert len(aligns) == 1
    assert aligns[0].lag_days == 10  # recomputed deterministically, not trusted
    assert aligns[0].events == [ev]


def test_out_of_window_alignment_dropped() -> None:
    infl = _inflection("2023-01-20")
    ev = _event("2021-12-01")  # >400 days before → outside window
    stub = StubLLM({"alignments": [{
        "inflection_date": "2023-01-20", "event_indices": [0],
        "confidence": 0.9, "explanation": "unrelated",
    }]})
    assert signal_analyst([infl], [ev], client=stub, window_days=45) == []


# --- T3.6 citation integrity in the explanation (P-INV-2) ----------------- #
def test_explanation_with_foreign_url_dropped() -> None:
    infl = _inflection("2023-01-20")
    ev = _event("2023-01-10")
    raw = [{
        "inflection_date": "2023-01-20", "event_indices": [0],
        "confidence": 0.7,
        "explanation": "Per https://fabricated.example.com/story it rallied.",
    }]
    assert enforce_alignments(raw, [infl], [ev], 45) == []


def test_explanation_citing_input_url_kept() -> None:
    infl = _inflection("2023-01-20")
    ev = _event("2023-01-10")
    raw = [{
        "inflection_date": "2023-01-20", "event_indices": [0],
        "confidence": 0.7,
        "explanation": "Per https://openai.com/blog/chatgpt demand rose.",
    }]
    assert len(enforce_alignments(raw, [infl], [ev], 45)) == 1


# --- confidence clamping + out-of-range indices --------------------------- #
def test_confidence_clamped_and_bad_indices_ignored() -> None:
    infl = _inflection("2023-01-20")
    ev = _event("2023-01-10")
    raw = [{
        "inflection_date": "2023-01-20", "event_indices": [0, 99],  # 99 out of range
        "confidence": 5.0, "explanation": "grounded",
    }]
    aligns = enforce_alignments(raw, [infl], [ev], 45)
    assert aligns[0].confidence == 1.0
    assert aligns[0].events == [ev]


# --- T3.7 empty input → [] with no LLM call ------------------------------- #
def test_empty_events_short_circuits() -> None:
    stub = StubLLM({"alignments": []})
    assert signal_analyst([_inflection("2023-01-20")], [], client=stub) == []
    assert stub.calls == []


def test_empty_inflections_short_circuits() -> None:
    stub = StubLLM({"alignments": []})
    assert signal_analyst([], [_event("2023-01-10")], client=stub) == []
    assert stub.calls == []
