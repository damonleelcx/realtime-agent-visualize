"""Isolated-context subagents (the only place an LLM runs).

P3: event_curator, signal_analyst. P4 adds report_builder.
"""

from __future__ import annotations

from .event_curator import event_curator
from .signal_analyst import signal_analyst

__all__ = ["event_curator", "signal_analyst"]
