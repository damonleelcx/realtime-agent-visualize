"""Realtime market-data analysis agent.

Public façade re-exported for convenience:

    from agent import run_analysis, AnalysisResult
"""

from __future__ import annotations

from .models import (
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
from .orchestrator import Orchestrator, run_analysis

__all__ = [
    "run_analysis",
    "Orchestrator",
    "AnalysisResult",
    "PriceSeries",
    "Bar",
    "NewsItem",
    "Inflection",
    "InflectionKind",
    "CuratedEvent",
    "Impact",
    "Alignment",
    "Provenance",
]
