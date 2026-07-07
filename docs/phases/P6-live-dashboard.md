# P6 · Live Dashboard (enhancement)

> **Timeline:** ~1 h · **Depends on:** [P5](./P5-orchestration-testing.md) · **Blocks:** —
> **Anchors:** [00-overview](../00-overview.md) · [design-writeup](../design-writeup.md)

An optional enhancement beyond the required file deliverables: a local web app
where you **watch the Harness loop stream in real time** as it analyzes a stock,
then see the interactive chart render inline with the Office files as downloads.

## Spec — what & why

The exercise requires interactive, *file* deliverables (which P4 produced). This
adds a **live view of the agent loop** — the "watch the agent think" surface —
which strengthens the "AI Agent 构建深度" axis without changing the pipeline. The
run is the *same* orchestrator; the dashboard only wires its `on_event` hook to a
browser over Server-Sent Events.

**Goals**
- G6.1 Non-invasive instrumentation: `orchestrator.run(..., on_event=cb)` emits
  `plan / act / observe / retry / validate / result` events. Default `None` → zero
  behavior change; every existing test still passes.
- G6.2 A FastAPI server streams those events over **SSE** while the real pipeline
  runs in a worker thread, then serves the produced HTML inline (`/runs/<id>/…`)
  plus xlsx/pptx/docx download links.
- G6.3 Graceful **no-key** mode: with `ANTHROPIC_API_KEY` unset, a `NullLLM`
  proposes nothing, so the K-line + inflections still render (events empty) — the
  dashboard is demoable offline-ish (still needs the network for live quotes).
- G6.4 Same-origin, self-contained: the produced HTML is unchanged (no CDN/CORS);
  nothing new is exposed beyond the local server.

**Non-goals:** hosting/auth/multi-user; realtime tick streaming; changing the
analysis. The dashboard is a *view*, not new capability.

## Plan — how

1. **Instrument** `orchestrator.run` / `_act` with an `on_event` callback and a
   per-step detail (`"208 bars"`, `"4 inflections"`, …). Backward-compatible.
2. **`agent/web/server.py`** — `create_app()` builds a FastAPI app: `GET /` serves
   the dashboard UI; `GET /api/run?ticker=&start=&end=` starts the pipeline in a
   thread, pushes each event onto a queue, and streams them as SSE; `/runs` mounts
   the artifacts dir. `NullLLM` + a tiny `.env` loader handle the no-key path.
3. **`agent/web/index.html`** — self-contained dashboard: a form, a live step list
   (spinner → ✓ + detail, retries in amber), a result summary, an `<iframe>` for
   the chart, and download links. Consumes the SSE stream via `EventSource`.
4. **`python -m agent.web`** launches uvicorn.

**Files produced:** `agent/web/{__init__,server,__main__}.py`, `agent/web/index.html`,
`tests/test_events.py`, `tests/test_web.py`; `web` extra in `pyproject.toml`.

## Test — how we know it's done

| ID | Type | Assertion |
|----|------|-----------|
| T6.1 | Unit | `on_event` streams the loop: first event is `plan`; every acted step has a matching `observe` in order; `result` carries the counts (`tests/test_events.py`). |
| T6.2 | Unit | Retries surface as `retry` events with the step name and attempt (via the flaky-tool fixture). |
| T6.3 | Integration | `create_app()` builds; `GET /` returns the dashboard HTML referencing `/api/run` (skipped when the `web` extra isn't installed). |
| T6.4 | Unit | `NullLLM.complete` returns empty events/alignments (no-key degrade path). |
| T6.5 | Manual | Browser: clicking Analyze streams the 8 steps live and renders the interactive chart + downloads inline (verified for a live NVDA run). |

**Exit criteria:** T6.1–T6.4 green in CI (T6.3/T6.4 skip without the extra); the
dashboard runs a real end-to-end analysis and streams the Harness loop; core CI
(`pip install -e .[dev]`) stays green because the web tests skip when fastapi is absent.

## Run it

```bash
pip install -e ".[dev,full,web]"        # + requests + fastapi/uvicorn
cp .env.example .env                     # add ANTHROPIC_API_KEY for LLM curation (optional)
python -m agent.web                      # → http://127.0.0.1:8000
```
