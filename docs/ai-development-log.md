# AI-Assisted Development Log

The exercise asks for a record of the development process. This project was built
with an AI pair (Claude Code, Opus 4.8) under human direction, phase by phase.

## AI tools used

- **Claude Code (Opus 4.8)** — the primary pair: planning, doc authoring,
  implementation, test writing, and live verification.
- **Parallel subagents** (Claude Code's Agent tool) — used once, to fan out the
  six per-phase spec/plan/test docs from a shared template. This mirrors the
  tool/subagent split the product itself uses.
- **Claude API skill** — consulted before writing the LLM client, to use the
  current model IDs (`claude-opus-4-8`) and the `output_config.format` structured-
  output pattern rather than a stale recollection.
- **Preview/browser tools** — used to load the generated HTML in a real browser
  and confirm the chart draws and the click→drill-down→clickable-source works.

## Process

Work proceeded as **doc-first, phase-gated**:

1. **Design docs before code.** An anchor overview + conventions fixed the data
   contract and five cross-cutting invariants; six per-phase docs (P0–P5) each
   specified Spec / Plan / Test. Only then did implementation start.
2. **One phase per step, each verified before moving on.** Every phase ended with
   `ruff` + `mypy --strict` + `pytest` green, and — where it mattered — a live
   run against real data or a browser screenshot.

## What the AI did, per phase

| Phase | AI contribution |
|-------|-----------------|
| Docs | Drafted the architecture and the per-phase spec/plan/test docs (six fanned out to parallel subagents, then reviewed for consistency). |
| P0 | Scaffolding, the `models.py` contract, cache, orchestrator stub, CLI, CI, tests. |
| P1 | `market_data` + `news_fetch` with fallback ladders, provenance stamping, caching; fixture-backed offline tests. |
| P2 | Deterministic `detect_inflections` (ruptures PELT + slope/gap classifier); golden fixture + high-coverage tests. |
| P3 | `event_curator` + `signal_analyst` subagents with the boundary-enforcement logic; `event-align` skill; stub-LLM tests. |
| P4 | `report_builder` + `kline-viz` (interactive HTML) + `office-export` (xlsx/pptx/docx); vendored ECharts; escaping/self-containment tests. |
| P5 | Loop/Harness orchestration, backend seam, CLI, the aggregate invariant suite, integration tests, these docs, CI. |

## Key human judgement & corrections

These were the decisions and catches that shaped the result — the parts where
human direction mattered, not just code generation:

- **SDK choice** — chose the Claude Agent SDK model (tools/subagents/skills as
  first-class primitives) to make the graded architecture axis explicit, with a
  bare-API fallback behind the same façade.
- **Non-negotiables set up front** — inflection detection must be a deterministic
  algorithm (auditability over convenience); provenance must be first-class from
  fetch time; artifacts must be self-contained and secret-free by construction.
- **Two real bugs caught during P2 by inspecting live behavior** — (a) ruptures'
  rbf cost *absorbed* a single-bar gap, so an independent gap-scan pass was added;
  (b) a linear ramp has tiny σ, so `2.5σ` flagged every step as a "gap" — fixed
  with an absolute 8% gap floor, confirmed by re-running with warnings-as-errors.
- **P3 boundary framing** — insisted the subagents *enforce* citation integrity
  and temporal sanity in code (not trust the model), and that injection headlines
  be treated as data; the tests assert the enforcement, not model prose.
- **Verification discipline** — required live end-to-end runs (real NVDA data +
  real Claude curation correctly aligning the 2023-05-25 breakout to NVIDIA's
  actual earnings beat) and a browser screenshot of the interactive HTML, rather
  than trusting unit tests alone.
- **Test-vs-reality reconciliation** — when the user's local `.env` appeared, the
  security test was corrected from "`.env` must not exist" to the real invariant,
  "`.env` must not be *tracked* by git."

## Reproducibility

Everything above is reproducible from the repo: `pytest -q` runs the whole suite
offline (81 tests), and `examples/live_smoke.py` / `python -m agent.run` exercise
the live path. The committed `samples/` were produced by the same code path the
integration test drives, so a stale sample would surface as a failing test.
