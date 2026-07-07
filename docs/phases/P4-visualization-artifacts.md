# P4 · Visualization & Artifacts (skill)

> **Timeline:** 1.5–2 h · **Depends on:** [P2](./P2-analysis-inflection.md), [P3](./P3-event-curation.md) · **Blocks:** [P5](./P5-orchestration-testing.md)
> **Anchors:** [00-overview](../00-overview.md) · [01-conventions](../01-conventions.md)

---

## Spec — what & why

Turn one `AnalysisResult` payload into the four **deliverables** — the interactive HTML plus the
Office trio (xlsx / pptx / docx). Everything in this phase is a **pure function of
`AnalysisResult`** ([conventions §2, "one payload, many renderers"](../01-conventions.md#2-core-data-records-passed-between-layers)):
no exporter fetches, re-computes, or touches the network, so all four deliverables tell the *same*
story from the *same* provenance. This is also where the front-end **security posture** of
[overview §8](../00-overview.md#8-security-model-system-design-step-20--prompts-explicit-asks)
becomes concrete: self-containment, output escaping, and no-secret guarantees are enforced at
render time, not aspired to.

**Goals**
- G4.1 `report_builder(result, outputs) -> list[str]` subagent orchestrates the skills to emit the requested files and returns their absolute paths (matches the [conventions §4](../01-conventions.md#4-subagent-contracts-isolated-context-structured-output) signature). It renders only; it never fetches or re-derives.
- G4.2 **`kline-viz` skill** renders the interactive self-contained HTML: ECharts candlestick (OHLC) + volume subplot, event markers placed at inflection dates, inflection markers colored **by `InflectionKind`**. Hover tooltip shows OHLCV + `fetched_at`; clicking an event marker opens a drill-down panel with the `CuratedEvent` rationale, impact rating, `lag_days`, and **clickable `source_url` links** back to the raw `NewsItem` (可溯源).
- G4.3 **`office-export` skill** renders three files from the *same* payload:
  - `xlsx` — the backtest 底稿: raw bars + inflections + events + alignments across tabs, **every row carrying `source_url`**.
  - `pptx` — a decision-framework deck (context → inflections → aligned events → impact).
  - `docx` — a strategy / analysis report (narrative over the same records).
- G4.4 **Self-containment (P-INV-5):** ECharts + all CSS/JS are **vendored and inlined at build time** — no `<script src="https://cdn…">`, no external `<link>`. The HTML opens offline via `file://`; runtime CORS, CDN availability, and CDN-tamper risk are removed by construction.
- G4.5 **Traceability propagated to the UI:** every marker/conclusion in the HTML **and** every row in the xlsx links back to a `source_url` or the raw bar it came from — [P-INV-1](../01-conventions.md#7-test-strategy-applies-to-every-phase) carried all the way to the rendered surface.
- G4.6 **Safe rendering:** every interpolated data field passes through `html.escape` (stored-XSS prevention, [conventions §8](../01-conventions.md#8-coding-conventions)); URLs are validated before being written as `href`s; **no secret** is ever written into any artifact ([P-INV-4](../01-conventions.md#7-test-strategy-applies-to-every-phase)).

**Non-goals:** any fetch / recompute / LLM call inside an exporter (those belong to [P1](./P1-data-tools.md)/[P2](./P2-analysis-inflection.md)/[P3](./P3-event-curation.md)); real-time chart updates; server-hosted dashboards ([overview §2](../00-overview.md#2-functional-requirements-system-design-step-1), out of scope).

**Key decision:** the vendored ECharts bundle is committed under `agent/skills/kline-viz/vendor/` and **inlined** at render time, not linked. Larger HTML (target < 3 MB per [overview §4](../00-overview.md#4-scale--constraints-system-design-step-3)) is the deliberate price of zero CORS/CDN/secret-leak risk and offline-openability — one of the standing trade-offs in [overview §11](../00-overview.md#11-key-trade-offs-system-design-step-24-summary).

---

## Plan — how

1. **`report_builder` subagent** (`agent/subagents/report_builder.py`). Input `(result: AnalysisResult, outputs: list[str])`; for each requested format dispatch to the matching skill, write via `artifact_io.write` ([conventions §3](../01-conventions.md#3-tool-signature-contracts-deterministic-no-llm-inside)), collect and return absolute paths. Pure w.r.t. its input — no network, no recompute. Empty/unknown `outputs` → no-op returning `[]`.
2. **`kline-viz` skill** (`agent/skills/kline-viz/`): `SKILL.md` (when-to-use + template contract), `template.html` (ECharts option skeleton + drill-down panel markup), `vendor/echarts.min.js` (committed), and `render.py` building the ECharts `option` from `result`.
   - Candlestick series from `series.bars` (OHLC); volume as a second axis/subplot.
   - Inflection markers at `inflection.date`, **color keyed by `InflectionKind`** (a fixed kind→color map); tooltip shows OHLCV + `Bar.prov.fetched_at`.
   - Event markers at aligned inflection dates; each carries a JSON payload of its `CuratedEvent` (rationale, `impact`, `Alignment.lag_days`, `news_refs`). Click → drill-down panel renders that payload with each `source_url` as an `<a href>`.
3. **Escaping & URL validation** (shared helper in the skill): route **every** interpolated field (`title`, `rationale`, `explanation`, tooltip text) through `html.escape`; validate every URL (scheme in `http/https`, non-empty) before emitting it as an `href` — otherwise drop the link and keep the text.
4. **Inline, don't link:** at render time read `vendor/echarts.min.js` and the CSS and inline them into `<script>`/`<style>` tags. Assert (in-code) the emitted HTML contains no external `http(s)` `src`/`href` before returning.
5. **`office-export` skill** (`agent/skills/office-export/`): `SKILL.md` + `templates/` + `render.py` with `to_xlsx/to_pptx/to_docx(result) -> bytes`.
   - **xlsx** (`openpyxl`): tabs `Bars`, `Inflections`, `Events`, `Alignments`; every row appends its `source_url` (bar → `Bar.prov.source_url`; event → `CuratedEvent.prov.source_url` / `news_refs`).
   - **pptx** (`python-pptx`): title / context → inflection overview → per-inflection aligned events + impact → sources appendix. Ticker + top events on the opening slides.
   - **docx** (`python-docx`): headed report — summary, methodology (deterministic detector id), findings per alignment citing `news_refs`, sources.
6. **Graceful-empty rendering:** when `events`/`alignments` are empty the K-line + inflections **still render**, with a visible "no events sourced" note ([conventions §6](../01-conventions.md#6-error-handling--degradation)); Office files emit their tabs/slides/sections with empty bodies rather than raising.
7. **No-secret guard at write time:** `report_builder` runs the `artifacts/`/`samples/` no-secret grep gate ([P-INV-4](../01-conventions.md#7-test-strategy-applies-to-every-phase)) conceptually mirrored in tests; nothing from `os.environ` is ever interpolated into a template.
8. **Samples:** write a golden HTML + xlsx/pptx/docx from the committed fixture `AnalysisResult` into `samples/` for review and the integration tests to re-open.

**Files produced:** `agent/subagents/report_builder.py`; `agent/skills/kline-viz/{SKILL.md,template.html,render.py,vendor/echarts.min.js}`; `agent/skills/office-export/{SKILL.md,render.py,templates/}`; sample deliverables under `samples/`.

---

## Test — how we know it's done

| ID | Type | Assertion |
|----|------|-----------|
| T4.1 | Security | Produced HTML is **self-contained**: no external `http(s)://` `src`/`href` in any `<script>`/`<link>`; the ECharts bundle text is inlined in the document (**P-INV-5**). |
| T4.2 | Contract | Every event marker in the HTML resolves to a real `source_url` that exists among the fetched `NewsItem`s — traceability propagated (**P-INV-1 / P-INV-2** at the UI). |
| T4.3 | Security | Injecting `<script>alert(1)</script>` into an event `title` fixture appears **escaped** (`&lt;script&gt;…`) in the HTML, not as an executable tag (`html.escape` applied). |
| T4.4 | Contract | The xlsx has the expected tabs (`Bars`, `Inflections`, `Events`, `Alignments`) and **every event row carries a non-empty `source_url`** (re-opened with `openpyxl`). |
| T4.5 | Contract | The pptx and docx **open** (`python-pptx` / `python-docx`) and contain the ticker string + the titles of the top events — structure asserted, not byte-diffed. |
| T4.6 | Security | No-secret grep over **all** produced artifacts (html/xlsx/pptx/docx) finds no key-shaped string (**P-INV-4**). |
| T4.7 | Contract | Exporters are **pure**: same `AnalysisResult` → structurally identical artifacts, with **no network** access (asserted via a network-forbidding fixture); wall-clock fields frozen for stability. |
| T4.8 | Integration | With `events`/`alignments` **empty**, the HTML still renders a valid K-line + inflections and shows the "no events sourced" note; Office files still open with empty bodies (graceful degradation). |

> Binary Office files are validated by **re-opening** them with `openpyxl` / `python-pptx` /
> `python-docx` and asserting structure (tabs, slide/paragraph text), never by byte-diff — they are
> not byte-stable. HTML, being text, is asserted on structure + substrings.

**Exit criteria:** T4.1–T4.8 green; `report_builder(result, ["html","xlsx","pptx","docx"])` writes all four to `artifacts/` and returns their absolute paths; sample deliverables committed under `samples/`; the vendored ECharts bundle is committed and inlined (never linked).

**Risks / mitigations**
- *Vendored ECharts bloats HTML past the 3 MB budget* → ship the minified build; data payload is small (~1.3k bars); assert size in CI and trim series precision if needed.
- *A malformed/hostile `source_url` slips into an `href`* → scheme+non-empty validation before emit; drop the link but keep escaped text — never emit an unvalidated `href`.
- *Office layout drift breaks re-open tests* → assert on **content** (ticker, event titles, tab names), not on exact positions/styling, so template polish doesn't churn tests.
- *An exporter tempted to "fill a gap" by fetching* → forbidden by contract; T4.7's network-forbidding fixture fails the build if any exporter touches the network.
