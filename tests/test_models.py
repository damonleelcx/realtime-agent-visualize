"""P0 tests T0.1 (models import/frozen/instantiable) and T0.2 (round-trip)."""

from __future__ import annotations

import dataclasses

import pytest

from agent.models import (
    Alignment,
    AnalysisResult,
    Bar,
    CuratedEvent,
    Impact,
    Inflection,
    InflectionKind,
    NewsItem,
    PriceSeries,
    Provenance,
)


def _sample_prov() -> Provenance:
    return Provenance(
        source="yfinance",
        source_url="https://finance.yahoo.com/quote/NVDA",
        fetched_at="2025-07-07T05:00:00Z",
        query="NVDA:2020-07-01:2025-07-01",
    )


def _sample_result() -> AnalysisResult:
    prov = _sample_prov()
    bar = Bar("2023-01-03", 14.85, 14.99, 14.10, 14.31, 401277000, prov)
    series = PriceSeries("NVDA", [bar], prov)
    infl = Inflection(
        date="2023-01-03",
        kind=InflectionKind.TURNING_UP,
        significance=0.82,
        price=14.31,
        window=("2022-12-20", "2023-01-10"),
        evidence_bars=["2022-12-28", "2023-01-03"],
        detector="pelt:rbf:pen=8",
    )
    news = NewsItem(
        "ChatGPT launches",
        "https://news.example.com/chatgpt",
        "2022-11-30",
        "OpenAI releases ChatGPT.",
        prov,
    )
    event = CuratedEvent(
        title="ChatGPT public launch",
        date="2022-11-30",
        category="model_release",
        impact=Impact.HIGH,
        rationale="Kicked off the generative-AI demand cycle.",
        news_refs=[news.url],
        prov=prov,
    )
    align = Alignment(
        inflection=infl,
        events=[event],
        lag_days=34,
        confidence=0.7,
        explanation="Reversal follows the ChatGPT-driven AI demand narrative.",
    )
    return AnalysisResult(
        ticker="NVDA",
        range=("2020-07-01", "2025-07-01"),
        series=series,
        inflections=[infl],
        events=[event],
        alignments=[align],
        generated_at="2025-07-07T05:00:00Z",
    )


# --- T0.1: every model imports, is frozen, and is instantiable --------------- #
ALL_MODELS = [
    Provenance, Bar, PriceSeries, NewsItem,
    Inflection, CuratedEvent, Alignment, AnalysisResult,
]


@pytest.mark.parametrize("model", ALL_MODELS)
def test_models_are_frozen_dataclasses(model: type) -> None:
    assert dataclasses.is_dataclass(model)
    params = model.__dataclass_params__  # type: ignore[attr-defined]
    assert params.frozen, f"{model.__name__} must be frozen for immutability"


def test_frozen_rejects_mutation() -> None:
    prov = _sample_prov()
    with pytest.raises(dataclasses.FrozenInstanceError):
        prov.source = "mutated"  # type: ignore[misc]


def test_sample_result_instantiates() -> None:
    result = _sample_result()
    assert result.ticker == "NVDA"
    assert result.inflections[0].kind is InflectionKind.TURNING_UP
    assert result.events[0].impact is Impact.HIGH


# --- T0.2: AnalysisResult round-trips through JSON without loss --------------- #
def test_round_trip_json() -> None:
    original = _sample_result()
    restored = AnalysisResult.from_json(original.to_json())
    assert restored == original


def test_round_trip_dict() -> None:
    original = _sample_result()
    restored = AnalysisResult.from_dict(original.to_dict())
    assert restored == original


def test_enums_serialize_to_values() -> None:
    d = _sample_result().to_dict()
    assert d["inflections"][0]["kind"] == "turning_up"
    assert d["events"][0]["impact"] == "high"
