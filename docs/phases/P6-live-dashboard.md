# P6 · Conversational Dashboard (enhancement)

> **Timeline:** ~2 h · **Depends on:** [P5](./P5-orchestration-testing.md) · **Blocks:** —
> **Anchors:** [00-overview](../00-overview.md) · [design-writeup](../design-writeup.md)

An enhancement beyond the required file deliverables: a local **chat** where you
ask the agent to analyze a stock and **watch it work** — it streams its
Plan→Act→Observe→Validate loop as conversation, then presents the events, the
interactive chart, and the downloadable files inline.

## Spec — what & why

The exercise requires interactive, *file* deliverables (which P4 produced). This
adds a **conversational view of the agent loop** — the "watch the agent think"
surface — strengthening the "AI Agent 构建深度" axis without changing the
analysis. The run is the *same* orchestrator; the dashboard wires its `on_event`
hook to a browser over Server-Sent Events.

**Goals**
- G6.1 Non-invasive instrumentation: `orchestrator.run(..., on_event=cb)` emits
  `plan / act / observe / retry / validate / result` events. Default `None` → zero
  behavior change; every existing test still passes.
- G6.2 A FastAPI server streams those events over **SSE** while the real pipeline
  runs in a worker thread, then streams the curated **event cards** and serves the
  produced HTML inline (`/runs/<id>/…`) plus xlsx/pptx/docx download links.
- G6.3 **Conversational UI**: a chat thread — user question → agent "On it" →
  a live step card (each Harness step ✓ with its detail) → a natural-language
  summary → **event cards** (impact badge, date, rationale, alignment, clickable
  source) → the embedded chart + downloads.
- G6.4 **Stop button**: while a run streams, Send becomes a red Stop. Clicking it
  closes the SSE stream; the server detects the disconnect and sets a cancel flag
  the orchestrator checks at each step boundary (`should_cancel` → `RunCancelled`),
  so the pipeline actually halts (cooperative — a blocking LLM call in flight
  finishes first).
- G6.5 Graceful **no-key** mode: with `ANTHROPIC_API_KEY` unset, a `NullLLM`
  proposes nothing, so the K-line + inflections still render (events empty).
- G6.6 Same-origin, self-contained: the produced HTML is unchanged (no CDN/CORS).

**Non-goals:** hosting/auth/multi-user; realtime tick streaming; changing the
analysis. The dashboard is a *view*, not new capability.

## Plan — how

1. **Instrument** `orchestrator.run` / `_act` with an `on_event` callback (per-step
   detail like `"208 bars"`) and a `should_cancel` hook checked between steps.
   Backward-compatible (defaults `None`).
2. **`agent/web/server.py`** — `create_app()` builds a FastAPI app: `GET /` serves
   the chat UI; `GET /api/run?ticker=&start=&end=` runs the pipeline in a worker
   thread, pushes each event onto a queue, and streams them as SSE; on completion
   it also emits `events` (flattened `_event_cards`) and `artifacts`. `/runs`
   mounts the artifacts dir. A per-run `threading.Event` is set when the SSE
   generator closes (Stop/disconnect) → `should_cancel`. `NullLLM` + a tiny `.env`
   loader handle the no-key path.
3. **`agent/web/index.html`** — self-contained **chat**: user/agent bubbles, a live
   step card (spinner → ✓ + detail, retries in amber), a summary bubble, event
   cards, an `<iframe>` for the chart, and download links. `EventSource` consumes
   the stream; the composer toggles Send ↔ Stop.
4. **`python -m agent.web`** launches uvicorn.

**Files produced:** `agent/web/{__init__,server,__main__}.py`, `agent/web/index.html`;
`tests/{test_events,test_web}.py`; `web` extra in `pyproject.toml`. (`should_cancel`
also lives in `agent/orchestrator.py`; the cancellation test in `tests/test_integration.py`.)

## Test — how we know it's done

| ID | Type | Assertion |
|----|------|-----------|
| T6.1 | Unit | `on_event` streams the loop: first event is `plan`; every acted step has a matching `observe` in order; `result` carries the counts (`tests/test_events.py`). |
| T6.2 | Unit | Retries surface as `retry` events with the step name and attempt. |
| T6.3 | Integration | `create_app()` builds; `GET /` returns the chat HTML referencing `/api/run` (skipped when the `web` extra isn't installed). |
| T6.4 | Unit | `NullLLM.complete` returns empty events/alignments (no-key degrade path). |
| T6.5 | Unit | `should_cancel` stops the run → `RunCancelled` (`tests/test_integration.py`). |
| T6.6 | Manual | Browser: sending a question streams the 8 steps live, renders event cards + the interactive chart + downloads; Stop mid-run halts it (verified live for NVDA). |

**Exit criteria:** T6.1–T6.5 green in CI (T6.3/T6.4 skip without the extra); the
dashboard runs a real end-to-end analysis conversationally and Stop cancels it;
core CI (`pip install -e .[dev]`) stays green because the web tests skip when
fastapi is absent.

## Run it

```bash
pip install -e ".[dev,full,web,sdk]"     # + requests + fastapi/uvicorn + anthropic
cp .env.example .env                      # add ANTHROPIC_API_KEY for LLM curation (optional)
python -m agent.web                       # → http://127.0.0.1:8000
```
