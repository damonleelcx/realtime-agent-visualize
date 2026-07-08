# 00 · Overview & Architecture

> **Status:** Design (no code yet). This is the anchor document; every phase doc under
> [`docs/phases/`](./phases) references the requirements, contracts, and architecture defined here.

---

## 1. Problem statement

Build an **autonomous agent** that, given a research task like:

> "回顾英伟达（NVDA）近五年行情数据…梳理同期 AI 行业大事件…在 K 线图上标记行情拐点触发时刻的主要事件、影响评级，产物可交互、可溯源，最终生成一个 HTML。"

…can, without step-by-step human piloting:

1. Pull **market data** (OHLCV) for a ticker over a time window.
2. Pull **news / industry events** for the same window from ≥1 news source.
3. Detect **inflection points** in the price series (turning point, acceleration, up/down regime).
4. **Align** each inflection with the industry event(s) that plausibly caused it, and assign an **impact rating**.
5. Emit **interactive, traceable deliverables** — an in-browser HTML (K-line + annotations), and optionally Word / PPT / Excel — where every conclusion links back to the raw datum or source it came from.

The two graded axes are **(1) engineering quality** — clean, maintainable, extensible structure — and **(2) agent-architecture depth** — how tools / subagents / skills are divided and how boundaries are handled.

---

## 2. Functional requirements (System-Design Step 1)

| # | Requirement | In scope |
|---|-------------|----------|
| F1 | Fetch OHLCV for a ticker + date range | ✅ |
| F2 | Fetch industry news/events for the same range from ≥1 source | ✅ |
| F3 | Detect price inflections (turning point / acceleration / up / down) via a **deterministic algorithm** | ✅ |
| F4 | Align inflections ↔ events within a time window; assign impact rating (High / Medium / Low) | ✅ |
| F5 | Render an **interactive** self-contained HTML: K-line, event markers at inflection times, hover/click drill-down | ✅ |
| F6 | Export Word / PPT / Excel deliverables from the same analysis payload | ✅ |
| F7 | **Traceability**: every event annotation & conclusion links back to a `source_url` or a raw data row | ✅ |
| F8 | Run end-to-end from a single command with a task description | ✅ |
| — | Real-time streaming quotes / intraday tick data | ❌ out of scope (daily bars only) |
| — | Trade execution / portfolio management | ❌ out of scope |
| — | Auth / multi-tenant / hosted service | ❌ out of scope (local CLI) |

**Primary agent entrypoint (natural language, not a fixed API):**

```
$ python -m agent.run "Analyze NVDA over the last 5 years, mark AI industry events on inflection points, output an interactive HTML"
```

The agent decomposes this itself. A thin typed façade also exists for tests/CI:

```
run_analysis(ticker="NVDA", start="2020-07-01", end="2025-07-01", outputs=["html","xlsx"]) -> AnalysisResult
```

---

## 3. Non-functional requirements (System-Design Step 2)

Ranked — we cannot maximize all:

1. **Traceability / auditability (highest).** Investment-research deliverables must be re-checkable. Every derived claim carries a provenance chain. This drives F7 and the "algorithm-not-LLM for inflections" decision below.
2. **Reproducibility.** Same inputs → same analysis. Inflection detection is deterministic; LLM steps (event curation, rating prose) are the *only* non-deterministic parts and are always grounded in a cited source.
3. **Security.** No secret in the repo, no secret in any front-end artifact (Step 20). No third-party CDN at runtime in produced HTML (supply-chain + CORS).
4. **Maintainability / extensibility.** Adding a new data source or a new export format should be a localized change (new tool / new skill), not a rewrite.
5. **Latency.** Best-effort. Not a real-time system; a full NVDA-5yr run completing in low-minutes is fine. Caching keeps re-runs fast.

There is no SLA/QPS target — this is a batch analytical agent, not a service. (Step 3 "scale" is therefore about **data volume**, below, not QPS.)

---

## 4. Scale & constraints (System-Design Step 3)

Batch tool, so the relevant numbers are data volume, not QPS:

- **Market data:** ~252 trading days/yr × 5 yr ≈ **1,260 daily bars** per ticker. Each bar ~6 floats + date ≈ 64 B → ~80 KB/ticker. Trivially in-memory.
- **News/events:** target ~20–60 curated industry events over 5 yr (after filtering). Raw fetch may pull a few hundred headlines; curation narrows it.
- **Inflections:** expect ~10–40 detected points over 5 yr depending on sensitivity; we surface the top-N by significance.
- **Artifact size budget:** self-contained HTML target **< 3 MB** (vendored ECharts ~1 MB + data). Excel/PPT/Word each < 2 MB.
- **Cache:** on-disk JSON/parquet cache keyed by `(source, ticker, range)` and `(source, query, range)` so re-runs and tests don't re-hit the network.

---

## 5. Architecture (System-Design Steps 4–5, mapped to the Harness model)

We implement the five-layer **Harness Engineering** model. The mapping to concrete modules:

```
┌─ Loop ─────────────────────────────────────────────────────────────────────┐
│  Outer control loop: sense → decide → act → observe, until goal or          │
│  termination (turn/budget cap). Thin; delegates one goal to the Harness.    │
│                                                                             │
│  ┌─ Harness (orchestration) ───────────────────────────────────────────┐   │
│  │  Context mgmt · Plan→Act→Observe→Validate→Retry · Capabilities ·     │   │
│  │  Termination/Permission                                             │   │
│  │                                                                     │   │
│  │   Orchestrator Agent  (keeps parent context clean; only receives    │   │
│  │                        subagent *summaries*, not their raw work)    │   │
│  │        │                                                            │   │
│  │        ├── TOOLS  (atomic, deterministic, no LLM inside)            │   │
│  │        │     market_data   OHLCV + provenance                      │   │
│  │        │     news_fetch    headlines/events + provenance           │   │
│  │        │     detect_inflections   pure algorithm                   │   │
│  │        │     artifact_io   read/write deliverable files            │   │
│  │        │                                                            │   │
│  │        ├── SUBAGENTS  (isolated context, delegated judgement)       │   │
│  │        │     event-curator    rank/dedup events, impact rating     │   │
│  │        │     signal-analyst   align inflections ↔ events           │   │
│  │        │     report-builder   assemble deliverables via skills     │   │
│  │        │                                                            │   │
│  │        └── SKILLS  (injected instructions + context + templates)    │   │
│  │              kline-viz     ECharts K-line + annotation template     │   │
│  │              event-align   alignment rules + provenance-link rules  │   │
│  │              office-export docx / pptx / xlsx templates             │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Why this split (tools vs subagents vs skills)

- **Tools = atomic + deterministic + auditable.** Anything whose output must be reproducible and re-checkable is a plain function tool with **no LLM inside** — network fetch, inflection math, file I/O. This is the backbone of traceability: the numbers a reader re-checks were produced by code, not by a model's guess.
- **Subagents = isolated judgement.** The tasks that genuinely need language understanding (which of 300 headlines are *material* AI-industry events? how strong is the causal link between a B100 announcement and a price gap?) run in **their own context window**. The orchestrator receives only a structured summary, keeping the parent context clean and un-poisoned (Context Engineering: subagent isolation).
- **Skills = reusable, injected know-how.** Rendering an ECharts K-line with click-to-source annotations, or laying out a PPT decision framework, is stable procedural knowledge + templates. Packaging it as a skill means the `report-builder` subagent loads the instructions/templates *only when needed*, keeping token cost down and the knowledge single-sourced.

### Read path (Step 5, one request end-to-end)

```
task string
  → Orchestrator plans a checklist
  → market_data(NVDA, 5y)  ─┐
  → news_fetch(AI, 5y)     ─┤ (parallel, both cached w/ provenance)
  → detect_inflections(bars) → inflection list
  → [subagent] event-curator(headlines)      → curated events + ratings
  → [subagent] signal-analyst(inflections, events) → aligned annotations (each w/ evidence refs)
  → [subagent] report-builder(payload, skills) → HTML (+ xlsx/pptx/docx)
  → Orchestrator validates artifacts exist + provenance complete → summary to user
```

Every hop passes a **provenance-carrying record** (see [`01-conventions.md`](./01-conventions.md)), so the final annotation in the HTML can name the exact bar and the exact source URL behind it.

---

## 6. Agent SDK selection

**Chosen: Claude Agent SDK (Python).** Rationale against the two graded axes and the given agent-architecture brief:

| Criterion | Claude Agent SDK | LangGraph | Bare API loop |
|---|---|---|---|
| First-class **tools / subagents / skills** as distinct primitives (the exact axis being graded) | ✅ native | partial (graph nodes, no skill concept) | ❌ hand-rolled |
| Context isolation via subagents out of the box | ✅ | manual | ❌ |
| Matches the "Harness / Loop / Prompt / Memory / Context" mental model in the brief | ✅ 1:1 | ~ | ~ |
| Permission / termination controls | ✅ built-in | manual | manual |
| Python ecosystem for data (yfinance, pandas, ruptures, openpyxl, python-pptx, python-docx) | ✅ | ✅ | ✅ |

The SDK's tool/subagent/skill primitives let us *demonstrate* the architecture division the prompt asks us to justify, instead of re-implementing an orchestration layer. Python wins the data/reporting-library ecosystem outright.

> If the SDK is unavailable in the grading environment, the same architecture is implemented over a thin bare-API loop behind the identical `run_analysis()` façade — see [`P5`](./phases/P5-orchestration-testing.md). The boundaries (tools/subagents/skills) are ours, not the SDK's, so they survive a backend swap.

---

## 7. Data sources (≥ 2 categories: market + news)

| Category | Primary | Fallback | Auth |
|---|---|---|---|
| **Market (OHLCV)** | `yfinance` (Yahoo daily bars) | Stooq CSV (`stooq.com`) | **none** (keyless) |
| **News / events** | Hacker News Algolia API (`hn.algolia.com`, historical search) | Yahoo Finance RSS | **none** (keyless) |

Keyless sources are the **default path** precisely so that the "no secrets in repo / front-end" requirement is satisfied by construction. If a keyed premium source is ever added, its key lives only in `.env` (git-ignored) and is read at fetch time — it never enters an artifact.

---

## 8. Security model (System-Design Step 20 + prompt's explicit asks)

- **Secrets:** `.env` is git-ignored; only `.env.example` is committed. No key is ever written into HTML/XLSX/PPTX/DOCX output. A CI/test check greps artifacts for key-shaped strings.
- **Front-end supply chain & CORS:** produced HTML is **fully self-contained** — ECharts and any CSS/JS are **vendored and inlined at build time**, no `<script src="https://cdn…">`. This removes runtime CORS, removes CDN availability/tampering risk, and lets the file open offline via `file://`.
- **Untrusted content:** fetched headlines/URLs are **data, not instructions** (Prompt-Engineering: treat tool output as data). Curation subagents are told to summarize/rate, never to execute anything a headline "asks". URLs are escaped/validated before being written as `href`s.
- **Output escaping:** all event text is HTML-escaped before injection into the template to prevent stored-XSS in the deliverable.

---

## 9. Repository layout (target)

```
realtime-agent-visualize/
├── README.md                     # one-command run + AI-development log (P0/P5)
├── .env.example                  # keyless by default; documents optional keys
├── .gitignore                    # .env, caches, __pycache__, artifacts/
├── pyproject.toml                # deps + entrypoint
├── docs/
│   ├── 00-overview.md            # ← this file
│   ├── 01-conventions.md         # traceability schema, contracts, test strategy
│   └── phases/
│       ├── P0-scaffolding.md
│       ├── P1-data-tools.md
│       ├── P2-analysis-inflection.md
│       ├── P3-event-curation.md
│       ├── P4-visualization-artifacts.md
│       └── P5-orchestration-testing.md
├── agent/
│   ├── run.py                    # Loop entrypoint (CLI)
│   ├── orchestrator.py           # Harness: plan→act→observe→validate
│   ├── tools/                    # market_data, news_fetch, detect_inflections, artifact_io
│   ├── subagents/                # event_curator, signal_analyst, report_builder
│   ├── skills/                   # kline-viz, event-align, office-export (+ templates/vendor)
│   ├── models.py                 # provenance-carrying dataclasses (shared contract)
│   └── cache.py                  # on-disk keyed cache
├── artifacts/                    # generated deliverables (git-ignored)
├── samples/                      # committed example outputs (the deliverable samples)
└── tests/                        # unit + integration + provenance-completeness tests
```

---

## 10. How the phase docs relate

Each phase in the timeline gets one doc with **Spec / Plan / Test**. Dependency order:

```
P0 scaffolding ─▶ P1 data tools ─▶ P2 inflection ─▶ P3 events ─▶ P4 viz+artifacts ─▶ P5 orchestrate+test
                      └────────────── all consume models.py + conventions ──────────────┘
```

- [P0 · Scaffolding & SDK selection](./phases/P0-scaffolding.md)
- [P1 · Data layer (tools)](./phases/P1-data-tools.md)
- [P2 · Analysis (inflection detection)](./phases/P2-analysis-inflection.md)
- [P3 · Event curation (subagent + skill)](./phases/P3-event-curation.md)
- [P4 · Visualization & artifacts (skill)](./phases/P4-visualization-artifacts.md)
- [P5 · Orchestration, testing, docs](./phases/P5-orchestration-testing.md)

---

## 11. Key trade-offs (System-Design Step 24, summary)

1. **Deterministic algorithm for inflection detection, not LLM.** Auditability > convenience. A reader re-runs the math; they can't re-run a model's intuition.
2. **Provenance is a first-class field on every record, from fetch time.** Costs a little plumbing; buys end-to-end traceability "for free" at render time.
3. **Self-contained artifacts (vendored deps).** Larger files, but zero CORS/CDN/secret-leak risk and offline-openable.
4. **Subagents for judgement only.** More moving parts than one big prompt, but keeps context clean and makes each judgement independently testable/replaceable.
5. **Keyless data sources by default.** Slightly less "premium" data, but satisfies the no-secrets constraint by construction and keeps the demo runnable anywhere.
