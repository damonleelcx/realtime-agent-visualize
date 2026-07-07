"""P1 tests for `news_fetch` (T1.3–T1.8)."""

from __future__ import annotations

import importlib
from pathlib import Path
from unittest.mock import Mock

import pytest

from agent.cache import JsonCache
from agent.tools._util import valid_http_url
from agent.tools.errors import DataSourceError, EmptyResultError

# `news_fetch` function is re-exported on the package, shadowing the submodule
# attribute — import the module object explicitly for monkeypatching.
nf = importlib.import_module("agent.tools.news_fetch")

FIX = Path(__file__).parent / "fixtures"
FROZEN = "2025-01-01T00:00:00Z"
NOV_DEC = ("2022-11-01", "2022-12-31")


def _hn_raw() -> str:
    return (FIX / "hn_algolia.json").read_text(encoding="utf-8")


# --- Golden parse + permalink-for-null-url ---------------------------------- #
def test_parse_hn_golden_and_permalink() -> None:
    items = nf.parse_hn(_hn_raw(), "AI", *NOV_DEC, FROZEN, 200)
    # GPT-4 (2023-03) filtered out; two Nov–Dec items remain, ascending.
    assert [i.published_at for i in items] == ["2022-11-30", "2022-12-05"]
    assert items[0].url == "https://openai.com/blog/chatgpt"
    # null story URL → HN permalink, never empty (P-INV-1).
    assert items[1].url == "https://news.ycombinator.com/item?id=33800000"


# --- T1.3 fallback ladder HN → RSS → seed ----------------------------------- #
def test_fallback_ladder_to_seed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(nf, "_fetch_hn", Mock(side_effect=DataSourceError("hn down")))
    monkeypatch.setattr(nf, "_fetch_rss", Mock(side_effect=EmptyResultError("rss empty")))
    items = nf.news_fetch("AI", *NOV_DEC, cache=JsonCache(tmp_path), clock=lambda: FROZEN)
    assert items, "seed must supply items when HN and RSS fail"
    assert all(i.prov.source == "seed" for i in items)
    assert any("ChatGPT" in i.title for i in items)


# --- T1.4/T1.5 provenance completeness + url mirroring ---------------------- #
def test_provenance_complete_and_url_mirrored(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(nf, "_fetch_hn", Mock(return_value=_hn_raw()))
    items = nf.news_fetch("AI", *NOV_DEC, cache=JsonCache(tmp_path), clock=lambda: FROZEN)
    assert items
    for i in items:
        assert i.prov.source_url and i.prov.source and i.prov.fetched_at
        assert i.url == i.prov.source_url  # mirrored
        assert valid_http_url(i.url)


# --- T1.6 cache hit avoids network ------------------------------------------ #
def test_cache_hit_avoids_network(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fetch = Mock(return_value=_hn_raw())
    monkeypatch.setattr(nf, "_fetch_hn", fetch)
    cache = JsonCache(tmp_path)
    nf.news_fetch("AI", *NOV_DEC, cache=cache, clock=lambda: FROZEN)
    nf.news_fetch("AI", *NOV_DEC, cache=cache, clock=lambda: FROZEN)
    assert fetch.call_count == 1
    nf.news_fetch("AI", *NOV_DEC, cache=cache, refresh=True, clock=lambda: FROZEN)
    assert fetch.call_count == 2


# --- T1.7 date-range filtering ---------------------------------------------- #
def test_date_range_excludes_out_of_window() -> None:
    items = nf.parse_hn(_hn_raw(), "AI", *NOV_DEC, FROZEN, 200)
    assert all(i.published_at <= "2022-12-31" for i in items)
    assert not any(i.published_at.startswith("2023") for i in items)  # GPT-4 excluded


# --- T1.8 graceful degradation: exhausted ladder returns [] ----------------- #
def test_exhausted_ladder_returns_empty(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(nf, "_fetch_hn", Mock(side_effect=DataSourceError("down")))
    monkeypatch.setattr(nf, "_fetch_rss", Mock(side_effect=DataSourceError("down")))
    # A window no seed event falls in → seed also empty → [] (not an exception).
    items = nf.news_fetch("AI", "1990-01-01", "1990-12-31",
                          cache=JsonCache(tmp_path), clock=lambda: FROZEN)
    assert items == []
