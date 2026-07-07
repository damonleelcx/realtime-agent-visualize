"""P1 tests for `market_data` (T1.1, T1.2, T1.4–T1.8)."""

from __future__ import annotations

import importlib
from pathlib import Path
from unittest.mock import Mock

import pytest

from agent.cache import JsonCache
from agent.tools._util import valid_http_url
from agent.tools.errors import DataSourceError

# The `market_data` function is re-exported on the package, shadowing the
# submodule attribute — import the module object explicitly for monkeypatching.
md = importlib.import_module("agent.tools.market_data")

FIX = Path(__file__).parent / "fixtures"
FROZEN = "2025-01-01T00:00:00Z"


def _yahoo_raw() -> str:
    return (FIX / "yahoo_nvda_chart.json").read_text(encoding="utf-8")


def _stooq_raw() -> str:
    return (FIX / "stooq_nvda.csv").read_text(encoding="utf-8")


# --- T1.1 golden-value parse ------------------------------------------------- #
def test_parse_yahoo_golden() -> None:
    bars = md.parse_yahoo_chart(_yahoo_raw(), "NVDA", "2023-01-01", "2023-01-31", FROZEN)
    assert [b.date for b in bars] == ["2023-01-03", "2023-01-04", "2023-01-05"]  # ascending
    assert bars[0].close == 14.315
    assert bars[0].volume == 401277000
    assert bars[-1].close == 14.265
    assert bars[0].prov.source == "yahoo"


# --- T1.2 fallback path ------------------------------------------------------ #
def test_fallback_to_stooq(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(md, "_fetch_yahoo", Mock(side_effect=DataSourceError("yahoo down")))
    monkeypatch.setattr(md, "_fetch_stooq", Mock(return_value=_stooq_raw()))
    series = md.market_data(
        "NVDA", "2023-01-01", "2023-01-31",
        cache=JsonCache(tmp_path), clock=lambda: FROZEN,
    )
    assert series.prov.source == "stooq"
    assert all(b.prov.source == "stooq" for b in series.bars)
    assert len(series.bars) == 3


def test_empty_primary_falls_through(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # Yahoo responds but with an empty result set → EmptyResultError → Stooq used.
    empty = '{"chart":{"result":[],"error":null}}'
    monkeypatch.setattr(md, "_fetch_yahoo", Mock(return_value=empty))
    monkeypatch.setattr(md, "_fetch_stooq", Mock(return_value=_stooq_raw()))
    series = md.market_data(
        "NVDA", "2023-01-01", "2023-01-31",
        cache=JsonCache(tmp_path), clock=lambda: FROZEN,
    )
    assert series.prov.source == "stooq"
    assert len(series.bars) == 3


# --- T1.4 provenance completeness (P-INV-1) --------------------------------- #
def test_provenance_complete(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(md, "_fetch_yahoo", Mock(return_value=_yahoo_raw()))
    series = md.market_data(
        "NVDA", "2023-01-01", "2023-01-31",
        cache=JsonCache(tmp_path), clock=lambda: FROZEN,
    )
    assert series.prov.source_url and series.prov.source and series.prov.fetched_at
    for b in series.bars:
        assert b.prov.source_url and b.prov.source and b.prov.fetched_at


# --- T1.5 citation URL validity --------------------------------------------- #
def test_source_urls_are_valid_http() -> None:
    bars = md.parse_yahoo_chart(_yahoo_raw(), "NVDA", "2023-01-01", "2023-01-31", FROZEN)
    for b in bars:
        assert valid_http_url(b.prov.source_url)


# --- T1.6 cache hit avoids network ------------------------------------------ #
def test_cache_hit_avoids_network(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fetch = Mock(return_value=_yahoo_raw())
    monkeypatch.setattr(md, "_fetch_yahoo", fetch)
    cache = JsonCache(tmp_path)
    md.market_data("NVDA", "2023-01-01", "2023-01-31", cache=cache, clock=lambda: FROZEN)
    md.market_data("NVDA", "2023-01-01", "2023-01-31", cache=cache, clock=lambda: FROZEN)
    assert fetch.call_count == 1  # 2nd call served from cache

    md.market_data("NVDA", "2023-01-01", "2023-01-31", cache=cache, refresh=True,
                   clock=lambda: FROZEN)
    assert fetch.call_count == 2  # --refresh re-invokes the network


# --- T1.7 date-range filtering (inclusive) ---------------------------------- #
def test_date_range_inclusive() -> None:
    bars = md.parse_yahoo_chart(_yahoo_raw(), "NVDA", "2023-01-04", "2023-01-04", FROZEN)
    assert [b.date for b in bars] == ["2023-01-04"]  # boundaries inclusive, others excluded


# --- T1.8 empty-result & exhaustion ----------------------------------------- #
def test_out_of_range_yields_empty_list() -> None:
    bars = md.parse_yahoo_chart(_yahoo_raw(), "NVDA", "2019-01-01", "2019-12-31", FROZEN)
    assert bars == []


def test_market_ladder_exhausted_raises(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(md, "_fetch_yahoo", Mock(side_effect=DataSourceError("down")))
    monkeypatch.setattr(md, "_fetch_stooq", Mock(side_effect=DataSourceError("down")))
    with pytest.raises(DataSourceError):
        md.market_data("NVDA", "2023-01-01", "2023-01-31",
                       cache=JsonCache(tmp_path), clock=lambda: FROZEN)
