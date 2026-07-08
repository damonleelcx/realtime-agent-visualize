# realtime-agent-visualize · 实时数据 Agent 与可视化

An **autonomous agent** that reviews a stock's price history, aligns it with same-period AI-industry
events, marks the causal moments on an interactive K-line chart, and produces **traceable**
deliverables (HTML + Word / PPT / Excel) where every conclusion links back to its raw source.

> The task the agent completes on its own:
> *"回顾英伟达（NVDA）近五年行情，梳理同期 AI 行业大事件，在 K 线图上标记行情拐点触发时刻的主要事件与影响评级，产物可交互、可溯源，最终生成一个 HTML。"*

Sample output (real NVDA run, ChatGPT era): [`samples/NVDA_analysis.html`](samples/NVDA_analysis.html)
— open it in a browser and click a blue event marker to trace it back to its source.

---
## Demo
<img width="640" height="360" alt="2026-07-07 11-46-33" src="https://github.com/user-attachments/assets/910cf49e-69b5-4ee1-83cd-9c9956e4c526" />

## What it does

Given a natural-language task, the agent autonomously:

1. **Fetches market data** (OHLCV) and **live industry news** for the same window — two source
   categories, both keyless. News is fully **dynamic** (Hacker News historical search → Yahoo RSS);
   nothing about the events is hardcoded.
2. **Detects price inflections** (turning points, breakouts, breakdowns) with a *deterministic
   algorithm* — re-runnable, not a model guess.
3. **Curates the material AI events** and assigns impact ratings, then **aligns** each inflection to
   the event(s) that plausibly caused it — the only LLM steps, each grounded in a cited source.
4. **Renders four deliverables** from one payload: an interactive self-contained **HTML** (K-line +
   clickable event→source drill-down), plus **xlsx / pptx / docx**.

Every datum and conclusion carries a clickable `source_url` from fetch time, so the whole thing is
**可溯源** (traceable) end to end.

---

## Quick start (local)

Requires **Python 3.11+** (tested on 3.13).

```bash
# 1. venv + install (dev = test toolchain + Office renderers; all offline tests run with this)
python3.13 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 2. run the full suite offline — no network, no API key (90 tests)
pytest -q
```

### Run the agent for real

The pipeline is keyless *except* the LLM curation step (P3). Add a key, then run:

```bash
pip install -e ".[dev,full,sdk]"     # + requests (live data) + anthropic (LLM)
cp .env.example .env                 # then put your key in .env:  ANTHROPIC_API_KEY=...
set -a && . ./.env && set +a         # load it (zsh/bash safe)

python -m agent.run "Analyze NVDA over the last 5 years and mark AI events on inflection points" \
    --ticker NVDA --start 2022-09-01 --end 2023-07-01 --outputs html,xlsx,pptx,docx --out-dir artifacts
```

It prints the plan, runs the pipeline, and writes the four artifacts:

```
PLAN:  1. fetch market data … 8. validate provenance + artifacts
RESULT:  NVDA 2022-09-01..2023-07-01  bars=208 inflections=4 events=3 alignments=3
ARTIFACTS:  artifacts/NVDA_analysis.{html,xlsx,pptx,docx}
```

- **Offline / no key:** `python -m agent.run "…" --plan-only` prints the plan without running anything.
- **Where do I get a key?** [console.anthropic.com](https://console.anthropic.com) → API Keys. It goes
  in `.env` only (git-ignored) and is **never** written into any produced artifact.

### Conversational dashboard — chat with the agent (optional)

A local **chat** where you ask the agent to analyze a stock and **watch it work**: it streams its
`Plan→Act→Observe→Validate` loop as conversation, then presents the curated **events**, the
interactive **chart**, and the **downloadable files** inline. A **Stop** button cancels a run
mid-flight (the orchestrator halts at the next step boundary).

```bash
pip install -e ".[dev,full,web,sdk]"  # + fastapi/uvicorn (web) + anthropic (LLM curation)
cp .env.example .env                   # then put your key in .env:  ANTHROPIC_API_KEY=...
python -m agent.web                    # → http://127.0.0.1:8000
```

Runs the real pipeline with LLM curation when `ANTHROPIC_API_KEY` is set (the server loads `.env`
automatically); without a key it degrades gracefully to K-line + inflections. Same-origin,
self-contained — no CDN/CORS. See
[`docs/phases/P6-live-dashboard.md`](docs/phases/P6-live-dashboard.md).

---

## How to test

```bash
pytest -q                       # 90 tests, all offline (no network, no key)
ruff check agent tests          # lint  (CI gate)
mypy agent                      # strict types  (CI gate)
```

| Suite | Covers |
|-------|--------|
| `test_models` / `test_cli` / `test_security` | data contract, CLI/plan wiring, secret isolation (P0) |
| `test_market_data` / `test_news_fetch` | fetch tools, fallback ladders, provenance, caching (P1) |
| `test_detect_inflections` | deterministic detector — golden values, determinism, gap/ramp cases (P2) |
| `test_event_curator` / `test_signal_analyst` | LLM subagents via a **stub**: citation integrity, dedup, injection defense, temporal sanity (P3) |
| `test_report_builder` | self-contained HTML, escaping, xlsx/pptx/docx structure, no-secret, no-network (P4) |
| `test_invariants` | **P-INV-1..5** over a full fixture run (P5) |
| `test_integration` | determinism, retry, termination cap, graceful degradation, CLI smoke (P5) |

Tests never touch the network and don't need an API key — the LLM steps run against a deterministic
stub. To exercise the **live** path end-to-end: `python examples/live_smoke.py`.

The five cross-cutting invariants asserted throughout: **P-INV-1** provenance completeness ·
**P-INV-2** citation integrity · **P-INV-3** temporal sanity · **P-INV-4** no secret in artifacts ·
**P-INV-5** self-contained HTML.

---

## Architecture

Five-layer Harness model. Full rationale in [`docs/00-overview.md`](docs/00-overview.md); the tour is
in [`docs/design-writeup.md`](docs/design-writeup.md).

```
Loop        agent/run.py          sense task → hand one goal to Harness → stop on done/cap
Harness     agent/orchestrator.py Plan → Act → Observe → Validate → Retry  (turn-capped)
  Tools     agent/tools/          market_data · news_fetch · detect_inflections · artifact_io   (deterministic, no LLM)
  Subagents agent/subagents/      event_curator · signal_analyst · report_builder               (isolated context; LLM here)
  Skills    agent/skills/         event-align · kline-viz · office-export                        (injected know-how + templates)
```

- **Tools = reproducibility.** Prices and the inflection math a reviewer re-checks are plain code.
- **Subagents = isolated judgement AND trust boundaries.** The LLM proposes; the subagent code
  enforces citation integrity / temporal sanity / injection defense regardless of what it returns.
- **Skills = reusable know-how.** The ECharts K-line and the Office layouts are packaged once.
- **Backend swap** ([`agent/backend.py`](agent/backend.py)): the orchestrator depends only on an
  `LLMClient` protocol. The default is the bare Messages-API client; swapping to the Claude Agent SDK
  is a one-module change — the tool/subagent/skill boundaries are ours, not the SDK's.

---

## Security & front-end safety (by construction)

- **No secrets in the repo or in any artifact.** `.env` is git-ignored; only `.env.example` is
  committed; default data path is keyless. A CI grep gate scans `samples/`/`artifacts/`; a test
  asserts `.env` is untracked.
- **Self-contained HTML.** ECharts is vendored and **inlined** — no CDN `<script src>` — so the file
  opens offline via `file://` with no CORS or supply-chain exposure.
- **Fetched content is data, not instructions.** Curation subagents wrap headlines in an "untrusted"
  envelope and never act on anything inside them; every interpolated field is `html.escape`d and every
  URL validated before it becomes an `href`.

---

## Repository layout

```
agent/
  run.py            CLI entrypoint (Loop)
  orchestrator.py   Harness: plan → act → observe → validate → retry (turn-capped)
  backend.py        LLM backend seam (SDK ↔ bare-API swap)
  llm.py            LLMClient protocol + AnthropicClient (structured output)
  models.py         shared, provenance-carrying data contract
  cache.py          on-disk keyed cache
  tools/            deterministic tools (no LLM)
  subagents/        isolated-context subagents (event_curator, signal_analyst, report_builder)
  skills/           templates + injected know-how (event-align, kline-viz, office-export + vendor/)
docs/               overview, conventions, per-phase spec/plan/test, design writeup, AI log
tests/              90 tests: unit · contract · integration · security · invariants
samples/            committed example deliverables (real NVDA run)
examples/           live_smoke.py — end-to-end against the real model
artifacts/          generated deliverables (git-ignored)
```

---

## Docs

- [00 · Overview & architecture](docs/00-overview.md) — requirements, scale, SDK choice, security, trade-offs
- [01 · Conventions & contracts](docs/01-conventions.md) — provenance schema, data records, test strategy, invariants
- [Design writeup](docs/design-writeup.md) — structure + the five decisions that shaped it
- [AI-development log](docs/ai-development-log.md) — AI tools used, AI's role, key human judgement/edits
- Per-phase spec/plan/test: [P0](docs/phases/P0-scaffolding.md) · [P1](docs/phases/P1-data-tools.md) · [P2](docs/phases/P2-analysis-inflection.md) · [P3](docs/phases/P3-event-curation.md) · [P4](docs/phases/P4-visualization-artifacts.md) · [P5](docs/phases/P5-orchestration-testing.md) · [P6](docs/phases/P6-live-dashboard.md)
