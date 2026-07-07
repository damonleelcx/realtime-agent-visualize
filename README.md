# realtime-agent-visualize · 实时数据 Agent 与可视化

An **autonomous agent** that reviews a stock's price history, aligns it with same-period industry
events, marks the causal moments on an interactive K-line chart, and produces **traceable**
deliverables (HTML + Word / PPT / Excel) where every conclusion links back to its raw source.

> Example task the agent completes on its own:
> *"回顾英伟达（NVDA）近五年行情，梳理同期 AI 行业大事件，在 K 线图上标记行情拐点触发时刻的主要事件与影响评级，产物可交互、可溯源，最终生成一个 HTML。"*

---

## Status

| Phase | What | State |
|-------|------|-------|
| Docs | Architecture + per-phase spec/plan/test | ✅ [`docs/`](docs/00-overview.md) |
| **P0** | Scaffolding, shared data contract, CLI, secret isolation, tests | ✅ **done** |
| P1 | Data tools (`market_data`, `news_fetch`) + provenance + cache | ⏳ next |
| P2 | Deterministic inflection detector | ⏳ |
| P3 | Event-curation + alignment subagents | ⏳ |
| P4 | Interactive HTML + Word/PPT/Excel exporters | ⏳ |
| P5 | Loop/Harness orchestration + end-to-end tests | ⏳ |

At P0 the agent runs end-to-end as a **skeleton**: it prints its plan and returns a well-formed
(empty) result. No data is fetched or rendered yet — that arrives in P1–P4.

---

## Quick start (local, one command)

Requires **Python 3.11+** (repo tested on 3.13). No API key needed for the scaffold.

```bash
# 1. from the repo root, create a venv and install the dev toolchain
python3.13 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 2. run the agent (P0: prints the plan + an empty, well-formed result)
python -m agent.run "Analyze NVDA over the last 5 years and mark AI events on inflection points"
```

Expected output: a numbered `PLAN:` (the tool/subagent pipeline) followed by a `RESULT` JSON block.

---

## How to test

```bash
# unit + contract + CLI + security tests (P0 suite)
pytest -q

# lint + strict types (same gates CI runs)
ruff check agent tests
mypy agent
```

The P0 suite covers, per [`docs/phases/P0-scaffolding.md`](docs/phases/P0-scaffolding.md):

| Test file | Covers | ID |
|-----------|--------|----|
| `tests/test_models.py` | models import, are frozen/immutable, and `AnalysisResult` round-trips through JSON | T0.1, T0.2 |
| `tests/test_cli.py` | `python -m agent.run` exits 0 and emits a valid plan + result; façade returns a well-formed empty result | T0.3 |
| `tests/test_security.py` | `.env` is git-ignored and uncommitted; `.env.example` holds no real secret | T0.4 (P-INV-4) |

Tests use **no network** and **no API key** — they run on a fresh clone.

---

## Architecture (one screen)

Five-layer Harness model. Full rationale in [`docs/00-overview.md`](docs/00-overview.md).

```
Loop  (CLI: sense → decide → act → observe)                      agent/run.py
 └─ Harness / Orchestrator  (Plan → Act → Observe → Validate)    agent/orchestrator.py
      ├─ Tools      atomic, DETERMINISTIC, no LLM inside         agent/tools/       (P1–P2)
      │   market_data · news_fetch · detect_inflections · artifact_io
      ├─ Subagents  isolated context, judgement only (LLM here)  agent/subagents/   (P3–P4)
      │   event_curator · signal_analyst · report_builder
      └─ Skills     injected instructions + templates            agent/skills/      (P3–P4)
          kline-viz · event-align · office-export
```

- **Tools = reproducibility.** Anything a reader must re-check (prices, inflection math) is plain
  code with no model in the loop.
- **Subagents = isolated judgement.** Language tasks (which headlines are material? how strong is
  the causal link?) run in their own context; the orchestrator only sees the structured summary.
- **Skills = reusable know-how.** Rendering the K-line or a PPT framework is packaged once and
  loaded on demand.

Every record carries a [`Provenance`](agent/models.py) (`source_url` + `fetched_at`) from fetch time,
so any marker in the final HTML links back to the exact datum or article behind it.

---

## Security & front-end safety (by construction)

- **No secrets in the repo or in any artifact.** `.env` is git-ignored; only `.env.example` is
  committed; the default data path is **keyless**. A test asserts `.env` is ignored and the template
  holds no real value.
- **Self-contained deliverables (P4).** The produced HTML inlines/vendors ECharts — no CDN `<script
  src>` — so it opens offline via `file://` with no CORS or supply-chain exposure.
- **Fetched content is data, not instructions.** Curation subagents summarize/rate headlines; they
  never act on anything a headline "asks". All interpolated text is HTML-escaped.

Details: [`docs/00-overview.md#8`](docs/00-overview.md#8-security-model-system-design-step-20--prompts-explicit-asks).

---

## Repository layout

```
agent/
  run.py           CLI entrypoint (Loop)
  orchestrator.py  Harness: plan → act → observe → validate  (P0 stub)
  models.py        shared, provenance-carrying data contract
  cache.py         on-disk keyed cache (sha256(source|args))
  tools/           deterministic tools           (filled P1–P2)
  subagents/       isolated-context LLM agents    (filled P3–P4)
  skills/          templates + injected know-how  (filled P3–P4)
docs/              overview, conventions, per-phase spec/plan/test
tests/             unit + contract + CLI + security
samples/           committed example outputs      (added P5)
artifacts/         generated deliverables (git-ignored)
```

---

## Design docs

- [00 · Overview & architecture](docs/00-overview.md) — requirements, scale, SDK choice, security, trade-offs
- [01 · Conventions & contracts](docs/01-conventions.md) — provenance schema, data records, test strategy, invariants
- Per-phase spec/plan/test: [P0](docs/phases/P0-scaffolding.md) · [P1](docs/phases/P1-data-tools.md) · [P2](docs/phases/P2-analysis-inflection.md) · [P3](docs/phases/P3-event-curation.md) · [P4](docs/phases/P4-visualization-artifacts.md) · [P5](docs/phases/P5-orchestration-testing.md)

---

## AI-assisted development log

This project is built with AI coding assistance (Claude Code). The process is recorded as it goes:

- **AI tools used:** Claude Code (Opus) as the primary pair — planning, doc authoring, and
  implementation.
- **AI's role so far:**
  - Drafted the architecture and the per-phase spec/plan/test docs. The six phase docs were fanned
    out to **parallel subagents** working from a shared template + the two anchor docs, then reviewed
    for consistency — mirroring the tool/subagent split the product itself uses.
  - Implemented P0: the `models.py` contract, cache, orchestrator stub, CLI, tests, and CI.
- **Key human judgement / edits:**
  - Chose the **Claude Agent SDK** (tools/subagents/skills as first-class primitives) over LangGraph
    to make the graded architecture axis explicit.
  - Set the non-negotiable that **inflection detection is a deterministic algorithm, not an LLM** —
    auditability over convenience.
  - Made **provenance a first-class field from fetch time** and required **self-contained artifacts**
    to satisfy the no-secret / no-CORS constraints by construction.

This section is extended at each phase (P5 consolidates the full log).
