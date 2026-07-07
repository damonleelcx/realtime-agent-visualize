"""`signal_analyst` subagent (docs/phases/P3).

Aligns each price inflection to the plausible event(s) within a time window.
Loads the `event-align` skill (not inlined) for the alignment/provenance rules.
The trust boundary here enforces:

- temporal sanity (P-INV-3): event within the window; `lag_days` recomputed
  deterministically from the dates, never trusted from the model;
- citation integrity (P-INV-2): an explanation may cite only URLs present in the
  referenced events' news_refs — a foreign URL discards the alignment.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from ..llm import LLMClient
from ..models import Alignment, CuratedEvent, Inflection
from ..skills.loader import load_skill

DEFAULT_WINDOW_DAYS = 45

ANALYST_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "alignments": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "inflection_date": {"type": "string"},
                    "event_indices": {"type": "array", "items": {"type": "integer"}},
                    "confidence": {"type": "number"},
                    "explanation": {"type": "string"},
                },
                "required": ["inflection_date", "event_indices", "confidence", "explanation"],
            },
        }
    },
    "required": ["alignments"],
}

_RULES = (
    "\n\nYou are the signal_analyst. Follow the event-align skill above. Return "
    "structured alignments only. Reference events by their index in the provided "
    "list. Cite only URLs that appear in those events' news_refs."
)

_URL_RE = re.compile(r"https?://[^\s)\]}<>\"']+")


def _date(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d")


def _extract_urls(text: str) -> list[str]:
    return [u.rstrip(".,") for u in _URL_RE.findall(text)]


def build_user_prompt(inflections: list[Inflection], events: list[CuratedEvent]) -> str:
    lines = ["INFLECTIONS:"]
    for inf in inflections:
        lines.append(
            f"  {inf.date}  {inf.kind.value}  price={inf.price:.2f}  sig={inf.significance:.2f}"
        )
    lines.append("\nEVENTS (index: date | impact | title | news_refs):")
    for i, ev in enumerate(events):
        refs = ", ".join(ev.news_refs)
        lines.append(f"  [{i}] {ev.date} | {ev.impact.value} | {ev.title} | {refs}")
    return "\n".join(lines)


def enforce_alignments(
    raw: list[dict[str, Any]],
    inflections: list[Inflection],
    events: list[CuratedEvent],
    window_days: int,
) -> list[Alignment]:
    """Apply temporal sanity + citation integrity to raw model output."""
    infl_by_date = {i.date: i for i in inflections}
    allowed_urls: set[str] = set()
    for ev in events:
        allowed_urls.update(ev.news_refs)

    out: list[Alignment] = []
    for a in raw:
        infl = infl_by_date.get(str(a.get("inflection_date", "")))
        if infl is None:
            continue
        idx = [j for j in a.get("event_indices", []) if isinstance(j, int) and 0 <= j < len(events)]

        # Temporal sanity (P-INV-3): recompute signed lag; keep only in-window events.
        sane: list[tuple[CuratedEvent, int]] = []
        for j in idx:
            ev = events[j]
            lag = (_date(infl.date) - _date(ev.date)).days
            if abs(lag) <= window_days:
                sane.append((ev, lag))
        if not sane:
            continue

        # Citation integrity (P-INV-2): no fabricated URL in the explanation.
        explanation = str(a.get("explanation", "")).strip()
        if any(u not in allowed_urls for u in _extract_urls(explanation)):
            continue

        sane.sort(key=lambda t: abs(t[1]))  # nearest event first
        confidence = max(0.0, min(1.0, float(a.get("confidence", 0.0))))
        out.append(
            Alignment(
                inflection=infl,
                events=[ev for ev, _ in sane],
                lag_days=sane[0][1],
                confidence=confidence,
                explanation=explanation,
            )
        )
    return out


def signal_analyst(
    inflections: list[Inflection],
    events: list[CuratedEvent],
    *,
    client: LLMClient,
    window_days: int = DEFAULT_WINDOW_DAYS,
) -> list[Alignment]:
    """Align inflections to events. Empty inflections or events → [] (no LLM call)."""
    if not inflections or not events:
        return []
    system = load_skill("event-align") + _RULES
    raw = client.complete(system, build_user_prompt(inflections, events), ANALYST_SCHEMA)
    return enforce_alignments(list(raw.get("alignments", [])), inflections, events, window_days)
