"""P3 tests for `event_curator` (T3.1–T3.4, T3.7, T3.8)."""

from __future__ import annotations

import json
from pathlib import Path

from agent.models import CuratedEvent, Impact, NewsItem, Provenance
from agent.subagents import event_curator
from agent.subagents.event_curator import (
    SYSTEM_PROMPT,
    build_user_prompt,
    enforce_events,
)
from tests.mocks.llm_stub import StubLLM

FIX = Path(__file__).parent.parent / "fixtures"
WINDOW = ("2022-11-01", "2022-12-31")


def _news() -> list[NewsItem]:
    rows = json.loads((FIX / "news_sample.json").read_text(encoding="utf-8"))
    return [
        NewsItem(
            r["title"], r["url"], r["published_at"], r["summary"],
            Provenance("hackernews", r["url"], "2025-01-01T00:00:00Z", "AI"),
        )
        for r in rows
    ]


# --- T3.1 schema-valid, structured output --------------------------------- #
def test_curator_returns_structured_events() -> None:
    news = _news()
    stub = StubLLM({"events": [{
        "title": "ChatGPT public launch", "date": "2022-11-30",
        "category": "model_release", "impact": "high",
        "rationale": "Kicked off the generative-AI demand cycle.",
        "news_refs": [news[0].url, news[1].url],
    }]})
    events = event_curator(news, "NVDA", WINDOW, client=stub)
    assert len(events) == 1
    ev = events[0]
    assert isinstance(ev, CuratedEvent)
    assert ev.impact is Impact.HIGH
    assert ev.rationale
    assert len(ev.news_refs) >= 1
    # provenance stitches back to a clickable source
    assert ev.prov.source_url == news[0].url


# --- T3.2 citation integrity (P-INV-2) ------------------------------------ #
def test_fabricated_citation_is_dropped() -> None:
    news = _news()
    raw = [{
        "title": "Fake", "date": "2022-11-30", "category": "model_release",
        "impact": "high", "rationale": "x",
        "news_refs": ["https://not-in-input.example.com/made-up", news[0].url],
    }]
    events = enforce_events(raw, news, "NVDA")
    assert events[0].news_refs == [news[0].url]  # bogus URL filtered out


def test_event_with_only_fabricated_citation_is_removed() -> None:
    news = _news()
    raw = [{
        "title": "Fake", "date": "2022-11-30", "category": "x",
        "impact": "high", "rationale": "x",
        "news_refs": ["https://not-in-input.example.com/made-up"],
    }]
    assert enforce_events(raw, news, "NVDA") == []


# --- T3.3 dedup: same event, two outlets → one event, both URLs ----------- #
def test_dedup_collapses_same_event() -> None:
    news = _news()
    stub = StubLLM({"events": [
        {"title": "OpenAI launches ChatGPT", "date": "2022-11-30",
         "category": "model_release", "impact": "high", "rationale": "a",
         "news_refs": [news[0].url]},
        {"title": "ChatGPT is here", "date": "2022-11-30",
         "category": "model_release", "impact": "high", "rationale": "b",
         "news_refs": [news[1].url]},
    ]})
    events = event_curator(news, "NVDA", WINDOW, client=stub)
    assert len(events) == 1
    assert set(events[0].news_refs) == {news[0].url, news[1].url}


# --- T3.4 prompt-injection defense ---------------------------------------- #
def test_injection_headline_is_enveloped_as_data() -> None:
    news = _news()
    prompt = build_user_prompt(news, "NVDA", WINDOW)
    # the injection text is present but inside the untrusted-data envelope
    assert "Ignore previous instructions" in prompt
    assert "BEGIN UNTRUSTED SOURCE CONTENT" in prompt
    assert "END UNTRUSTED SOURCE CONTENT" in prompt
    idx_begin = prompt.index("BEGIN UNTRUSTED")
    idx_inj = prompt.index("Ignore previous instructions")
    idx_end = prompt.index("END UNTRUSTED")
    assert idx_begin < idx_inj < idx_end
    # and the system prompt establishes the data-not-instructions guard
    assert "UNTRUSTED DATA" in SYSTEM_PROMPT
    assert "only trusted instructions" in SYSTEM_PROMPT


def test_injection_headline_does_not_alter_pipeline() -> None:
    news = _news()
    # A well-behaved model rates the injection item as a normal (low) event.
    stub = StubLLM({"events": [{
        "title": "Suspicious headline reported", "date": "2022-12-02",
        "category": "other", "impact": "low",
        "rationale": "Flagged as an attempted injection; no market impact.",
        "news_refs": [news[2].url],
    }]})
    events = event_curator(news, "NVDA", WINDOW, client=stub)
    assert len(events) == 1
    assert events[0].impact is Impact.LOW  # output stays schema-valid


# --- T3.7 empty input → [] with no LLM call ------------------------------- #
def test_empty_news_short_circuits() -> None:
    stub = StubLLM({"events": []})
    assert event_curator([], "NVDA", WINDOW, client=stub) == []
    assert stub.calls == []  # no LLM call made


# --- T3.8 determinism with the stub --------------------------------------- #
def test_deterministic_with_stub() -> None:
    news = _news()
    stub = StubLLM({"events": [{
        "title": "ChatGPT", "date": "2022-11-30", "category": "model_release",
        "impact": "high", "rationale": "x", "news_refs": [news[0].url],
    }]})
    a = event_curator(news, "NVDA", WINDOW, client=stub)
    b = event_curator(news, "NVDA", WINDOW, client=stub)
    assert [(e.title, e.impact, tuple(e.news_refs)) for e in a] == \
           [(e.title, e.impact, tuple(e.news_refs)) for e in b]
