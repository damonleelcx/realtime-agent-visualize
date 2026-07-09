---
name: event-align
description: Align a detected price inflection to the AI-industry event(s) that plausibly caused it, ranking by causal plausibility and keeping every claim traceable to a real input source. Load in the signal_analyst subagent when correlating inflections with curated events.
---

# Skill: event-align

Reusable know-how for the `signal_analyst` subagent: how to align a detected
price **inflection** to the industry **event(s)** that plausibly caused it, and
how to keep every claim traceable back to a real source.

## Alignment rules

1. **Window.** Consider only events whose date is within the configured match
   window of the inflection date. Events outside the window are not candidates —
   the harness drops them regardless of what you say.
2. **Signed lag.** `lag_days = inflection_date − event_date`. Positive means the
   event preceded the inflection (the usual causal direction); a small negative
   lag (event slightly after) is allowed within the window. The harness
   recomputes `lag_days` from the dates — do not compute it yourself.
3. **Plausibility ranking.** When several events fall in the window, rank by
   causal plausibility: larger `impact`, shorter lag, and topical fit to the
   inflection `kind` (a chip/model launch fits a BREAKOUT_UP; a policy shock fits
   a BREAKDOWN). List the most plausible events first.
4. **Confidence.** Assign `confidence ∈ [0,1]` — how strongly the evidence
   supports this event → inflection link. Be conservative; uncertain links get
   low confidence, not omission.

## Provenance-link rules (traceability)

- Every `explanation` must ground its claim in the cited events. **Only cite
  URLs that appear in the referenced events' `news_refs`.** A URL not present in
  the input is a fabrication and the alignment is discarded.
- Prefer to name the event and paraphrase its source over quoting raw text.
- If no in-window event plausibly explains an inflection, return no alignment
  for it — never invent a cause.

## Output contract

Return structured alignments only (no prose outside the schema): each carries the
inflection date, the indices of the referenced events, a confidence, and an
explanation that cites only in-input URLs.
