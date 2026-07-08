# Design Writeup

A compact tour of the structure and the key trade-offs. Full rationale lives in
[00-overview](./00-overview.md); this is the "why it's shaped this way" summary.

## The shape

One autonomous agent turns a natural-language task into traceable deliverables.
It is built as the five-layer **Harness** model from the brief:

```
Loop        agent/run.py          sense task → hand one goal to Harness → stop on done/cap
Harness     agent/orchestrator.py Plan → Act → Observe → Validate → Retry (turn-capped)
  Tools     agent/tools/          market_data · news_fetch · detect_inflections · artifact_io
  Subagents agent/subagents/      event_curator · signal_analyst · report_builder
  Skills    agent/skills/         event-align · kline-viz · office-export
```

Data flows through one contract — the provenance-carrying records in
[`agent/models.py`](../agent/models.py) — so every stage speaks the same
language and `AnalysisResult` is the single payload all four exporters render.

## The five decisions that shaped it

1. **Tools are deterministic; only subagents run an LLM.** Anything a reviewer
   must re-check — prices, the inflection math, file writing — is plain code with
   no model in the loop. The *only* non-determinism is confined to
   `event_curator` / `signal_analyst`, and even there every output is grounded in
   a cited source. This is the backbone of "可复核" (re-checkable).

2. **Inflection detection is an algorithm, not an LLM.** `detect_inflections`
   uses `ruptures` PELT change-point detection plus a transparent slope/gap
   classifier. Same bars → identical points, pinned by golden tests. A reader
   re-runs the math; they can't re-run a model's intuition.

3. **Provenance is a first-class field from fetch time.** Every `Bar`,
   `NewsItem`, `CuratedEvent` carries a clickable `source_url` and `fetched_at`
   the moment it's created. That plumbing is what makes the HTML marker →
   drill-down → clickable source chain work, and what the `Validate` step and the
   invariant tests check end-to-end.

4. **Subagents are trust boundaries, not just prompts.** The LLM *proposes*
   events and alignments; the subagent code *enforces* the invariants regardless
   of what the model returns — citations filtered to real input URLs (P-INV-2),
   `lag_days` recomputed from dates (P-INV-3), injection headlines wrapped in an
   "untrusted data" envelope. A fabricated citation can't reach an artifact.

5. **Deliverables are self-contained and secret-free by construction.** The HTML
   inlines a vendored ECharts (no CDN → no CORS, offline-openable), every field is
   `html.escape`d, and nothing from the environment is ever interpolated into a
   template. The default data path is keyless, so "no secrets" holds without
   discipline.

## Boundaries & extension points

- **Backend swap** ([`agent/backend.py`](../agent/backend.py)): the orchestrator
  depends only on the `LLMClient` protocol. The default is the bare Messages-API
  client; pointing it at the Claude Agent SDK is a one-module change because the
  tool/subagent/skill boundaries are ours, not the SDK's.
- **New data source** → a new function behind the `market_data`/`news_fetch`
  fallback ladder; provenance stamping is already there.
- **New deliverable** → a new render function + one line in `report_builder`'s
  dispatch table; it consumes the same `AnalysisResult`.
- **Termination**: a hard `MAX_TURNS` / per-step retry cap means a wedged step
  raises `TerminationError` and the run fails cleanly instead of hanging;
  cooperative `should_cancel` (checked at step boundaries) lets the dashboard's
  Stop button halt a run.
- **Live surface** ([`agent/web/`](../agent/web)): the orchestrator's `on_event`
  hook is streamed over SSE to a conversational dashboard that narrates the loop
  and renders the events + chart + files inline. It's a *view* of the same run —
  no analysis logic lives there.
- **Robustness**: the LLM boundary ([`agent/llm.py`](../agent/llm.py)) salvages a
  structured response truncated at `max_tokens` (keeps the complete objects,
  closes the array) rather than failing the whole run.

## Known limitations / next steps

- News is **fully dynamic** — pulled live from Hacker News (Algolia historical
  search) → Yahoo RSS at run time, then curated by the LLM into material events.
  Nothing about the events is hardcoded. Breadth therefore depends on what those
  keyless sources return for the query/window; a keyed premium source (e.g. Alpha
  Vantage News, Finnhub) would widen coverage and would slot in behind the same
  `Provenance` stamping, its key living only in `.env`.
- Alignment is a bounded-window heuristic with an LLM confidence, not a causal
  model; it's designed to be *auditable* (every link cites a source), not proven.
- The Claude Agent SDK backend is scaffolded behind the façade but the shipped
  default is the Messages-API path.
