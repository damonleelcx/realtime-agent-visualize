# P5 · Orchestration, Testing & Docs

> **Timeline:** 1 h · **Depends on:** [P1](./P1-data-tools.md), [P2](./P2-analysis-inflection.md), [P3](./P3-event-curation.md), [P4](./P4-visualization-artifacts.md) · **Blocks:** — (final phase)
> **Anchors:** [00-overview](../00-overview.md) · [01-conventions](../01-conventions.md)

---

## Spec — what & why

Close the loop. P1–P4 built the tools, the inflection math, the judgement subagents, and the
renderers as independent parts. This phase **wires the control flow** that strings them into one
autonomous run, adds the **end-to-end test suite + invariants** that prove the whole thing holds
together, and writes the **deliverable docs** (README, design writeup, AI-development log). Nothing
new gets computed here — P5 is orchestration, verification, and packaging.

**Goals**
- G5.1 **Loop → Harness → Orchestrator** control flow implemented: `orchestrator.run(task)` performs Plan→Act→Observe→Validate→Retry over the P1–P4 capabilities per [overview §5](../00-overview.md#5-architecture-system-design-steps-45-mapped-to-the-harness-model), with a hard turn/budget cap so it can neither spin nor early-exit.
- G5.2 Typed façade `run_analysis(ticker, start, end, outputs) -> AnalysisResult` finalized for tests/CI, sitting *under* the NL entrypoint `python -m agent.run "<task>"`.
- G5.3 **SDK-vs-fallback swap boundary** documented and exercised: Claude Agent SDK backend and a bare-API fallback both sit behind the identical façade per [overview §6](../00-overview.md#6-agent-sdk-selection).
- G5.4 **Full end-to-end integration test** on a committed fixture dataset (no live network) that produces all four artifact types into `artifacts/`, and **sample outputs committed** into `samples/`.
- G5.5 **All five cross-cutting invariants** from [conventions §7](../01-conventions.md#7-test-strategy-applies-to-every-phase) wired as automated tests (P-INV-1…5); this phase **owns the aggregate invariant suite**.
- G5.6 Deliverable docs: README (one-command local run), design writeup, and the required **AI-development-process log**; `.env.example` present; **no-secret gate** in CI.
- G5.7 CI wiring: `ruff`, `mypy --strict agent/`, `pytest` all green in one pipeline.

**Non-goals:** new data sources, new detectors, new renderers, or new subagent judgement — those are owned by P1–P4. P5 only orchestrates and verifies them.

**Outer Loop vs inner Harness (from the brief).** The **Loop** (`agent/run.py`) is thin: it senses the NL task, decides to hand exactly one goal to the Harness, observes the returned summary, and terminates on goal-reached or the turn/budget cap. The **Harness** (`agent/orchestrator.py`) is the machinery — context management, the Plan→Act→Observe→Validate→Retry cycle over tools/subagents/skills, capability wiring, and termination/permission enforcement. The Loop owns *when to stop*; the Harness owns *how the work gets done*.

**The Plan→Act→Observe→Validate→Retry cycle:**
- **Plan** — decompose the task into an ordered checklist (the read-path in [overview §5](../00-overview.md#5-architecture-system-design-steps-45-mapped-to-the-harness-model): fetch market + news → detect → curate → align → render).
- **Act** — execute the next checklist step by calling a tool or delegating to a subagent; the orchestrator receives only structured summaries, never a subagent's raw scratch context.
- **Observe** — feed each step's typed result back into the running context for the next step.
- **Validate** — after the render step, check invariants: provenance complete, citations resolve, artifacts exist on disk.
- **Retry** — on a validation miss or a transient tool failure, re-run the failed step **with feedback** appended; bounded by the cap.
- **Termination** — a turn/budget cap (per [overview §3](../00-overview.md#3-non-functional-requirements-system-design-step-2)) bounds total steps + retries so a wedged step fails cleanly instead of hanging or looping forever.

---

## Plan — how

1. **Implement `orchestrator.run(task)`** as the Harness: `plan(task)` (now real, replacing the P0 stub) emits the checklist; a driver loop advances Act→Observe over each step, calling the P1 tools and P3 subagents, then P4's `report_builder`.
2. **Wire Validate** — after render, run the invariant checks (provenance non-empty, `news_refs`/`Alignment` citations resolve to fetched `NewsItem`s, each requested artifact path exists). A failed validate feeds back into Retry.
3. **Wire Retry with feedback + cap** — wrap each step in a bounded retry that appends the failure/validation message to the step context. A module-level `MAX_TURNS` / budget guard raises a typed `TerminationError` when exceeded so the run **fails cleanly**.
4. **Finalize the `run_analysis()` façade** — `run_analysis(ticker, start, end, outputs) -> AnalysisResult` builds the task, invokes `orchestrator.run`, and returns the validated `AnalysisResult`. This is the deterministic entrypoint every test targets.
5. **Backend swap boundary** — a `backend` module selects Claude Agent SDK vs bare-API loop behind the façade; both consume the same tool/subagent/skill definitions (the boundaries are ours, not the SDK's). Document the swap in the design writeup + [overview §6](../00-overview.md#6-agent-sdk-selection).
6. **Wire the NL Loop** — `python -m agent.run "<task>"` parses the task and calls the Harness; exit 0 on success, non-zero + message on `TerminationError`.
7. **Build the fixture** — commit a small OHLCV + news fixture under `tests/fixtures/` seeding the `.cache/`, so the integration test runs with **no live network** and a frozen clock.
8. **Write the aggregate invariant suite** — one `tests/test_invariants.py` asserting **P-INV-1…5** against the artifacts produced by a fixture `run_analysis()`; plus retry-path, termination-cap, and graceful-degradation tests.
9. **Commit sample outputs** — run the fixture end-to-end, copy the four artifacts into `samples/` (committed, so a grader sees deliverables without running anything).
10. **Docs.** Fill the README (one-command run + how to swap backend), a `docs/` design writeup, and the **AI-development-process log**: which AI tools were used, what the AI did, and the key human judgement/edits. Confirm `.env.example` is committed and keyless.
11. **CI.** Finalize `.github/workflows/ci.yml`: `ruff check`, `mypy --strict agent/`, `pytest`, and the **no-secret grep gate** over `artifacts/` + `samples/`.

**Files produced:** `agent/orchestrator.py` (full), `agent/run.py` (full), `agent/backend.py`, `tests/fixtures/*`, `tests/test_integration.py`, `tests/test_invariants.py`, `samples/*` (committed artifacts), `README.md` (final), `docs/design-writeup.md`, `docs/ai-development-log.md`, finalized CI config.

---

## Test — how we know it's done

| ID | Type | Assertion |
|----|------|-----------|
| T5.1 | Integration | `run_analysis(ticker, start, end, ["html","xlsx","pptx","docx"])` on the fixture returns a well-formed `AnalysisResult` (series/inflections/events/alignments populated) and writes **all four** artifact types into `artifacts/`. |
| T5.2 | Contract | **P-INV-1** provenance completeness — every `Bar`, `NewsItem`, `CuratedEvent` in the result has non-empty `source_url`. |
| T5.3 | Contract | **P-INV-2** citation integrity — every `CuratedEvent.news_refs` and `Alignment` citation URL exists among the fetched `NewsItem`s. |
| T5.4 | Contract | **P-INV-3** temporal sanity — every `Alignment.lag_days` is within the configured match window (event date ≤ inflection date + window). |
| T5.5 | Security | **P-INV-4** no-secret — no artifact under `artifacts/` or `samples/` contains a key-shaped string (`grep` gate; same check runs in CI). |
| T5.6 | Integration | **P-INV-5** self-contained HTML — the produced HTML has **no** external `http(s)://` `src`/`href` in `<script>`/`<link>` (offline-openable). |
| T5.7 | Integration | Determinism — two fixture runs under a frozen clock produce **byte-identical** deterministic core (bars, inflections, alignments); only `generated_at`/`fetched_at` may differ, and they're frozen too. |
| T5.8 | Integration | Retry path — inject a **transient** tool failure (fails once, then succeeds); the orchestrator retries with feedback and the run still completes with a valid `AnalysisResult`. |
| T5.9 | Integration | Termination cap — a **wedged** step (always fails) hits the turn/budget cap and raises `TerminationError` → the run **fails cleanly** (bounded, no hang, non-zero exit), rather than spinning. |
| T5.10 | Integration | Graceful degradation — with the news source empty, the run still produces the HTML + inflections; `events`/`alignments` are empty and a visible "no events sourced" note appears (per [conventions §6](../01-conventions.md#6-error-handling--degradation)). |
| T5.11 | Integration | CLI smoke — `python -m agent.run "Analyze NVDA…"` (fixture-backed) exits **0** and prints the plan + result summary. |
| T5.12 | Tooling | `ruff check`, `mypy --strict agent/`, and `pytest` all pass in CI; the no-secret grep gate (T5.5) is a CI step. |

**Exit criteria:** T5.1–T5.12 green; four sample artifacts committed under `samples/`; README documents the one-command run and the SDK↔fallback swap; the AI-development log is present; CI runs lint + types + tests + the no-secret gate on every push.

**Risks / mitigations**
- *Orchestrator loops or early-exits* → hard turn/budget cap raises `TerminationError`; T5.9 proves it fails cleanly.
- *Flaky integration from live network* → committed fixture cache + frozen clock; tests never touch the network (T5.7).
- *SDK unavailable in grader env* → bare-API fallback behind the identical `run_analysis()` façade; the tool/subagent/skill boundaries are ours, so the suite passes on either backend ([overview §6](../00-overview.md#6-agent-sdk-selection)).
- *Secret leaks into a deliverable* → P-INV-4 grep gate over `artifacts/` + `samples/` in CI blocks the merge (T5.5).
- *Sample artifacts drift from code* → samples are regenerated from the same fixture `run_analysis()` the integration test drives, so a stale sample surfaces as a failing test.
