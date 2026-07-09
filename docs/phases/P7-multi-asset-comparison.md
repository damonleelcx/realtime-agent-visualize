# P7 · Multi-Asset Comparison & Strategy Backtest (generalization)

> **Timeline:** ~3 h · **Depends on:** [P4](./P4-visualization-artifacts.md), [P5](./P5-orchestration-testing.md) · **Blocks:** —
> **Anchors:** [00-overview](../00-overview.md) · [design-writeup](../design-writeup.md)

Generalizes the agent from the single-ticker "行情 + AI 事件" analysis to the
brief's *other* example shape — **compare two assets and produce an Excel / PPT /
Word system**, e.g. **Gold vs Bitcoin**. This is a second, deterministic pipeline
that reuses the same layers (tools → skills → report builder → Harness) and the
same provenance/traceability + self-contained-HTML guarantees.

## Spec — what & why

The prompt frames the graded task as *"这类任务"* and names a gold-vs-bitcoin
Excel/PPT/Word comparison as a sibling example. P0–P6 built the NVDA pipeline; P7
shows the architecture **transfers** to a comparison task without re-plumbing the
boundaries.

**Goals**
- G7.1 **Deterministic, LLM-free** comparison: the analysis is quantitative
  (returns, vol, Sharpe, drawdown, correlation, a rebalanced backtest), so the
  whole pipeline runs offline and reproducibly — same inputs, same numbers.
- G7.2 **Date-intersection correctness**: assets are compared only on days *both*
  traded, so a 7-day-a-week asset (BTC) and a weekday-only asset (gold futures)
  are aligned honestly.
- G7.3 **Strategy backtest with frictions**: a weighted portfolio simulated with a
  rebalance schedule; each rebalance charges its turnover a transaction cost, so
  rebalancing's drag is *modelled*, and a buy-&-hold benchmark is run alongside.
- G7.4 **Four deliverables from one payload**: interactive self-contained HTML
  (rebased performance + backtest equity + rolling correlation) plus the Office
  trio (xlsx 回测底稿, pptx deck, docx narrative) — every asset traceable to its
  `source_url`.
- G7.5 **Same guarantees**: HTML inlines ECharts (no CDN/CORS), all fields escaped,
  href validated, embedded JSON script-safe; no secret ever reaches a file.
- G7.6 **Standard skills**: the two new renderers are first-class Agent-Skill
  packages (`compare-viz`, `compare-office`) with valid frontmatter, discovered and
  loaded at dispatch like the others.

**Non-goals:** intraday data; live rebalancing; tax-lot accounting; per-asset event
curation (that is the NVDA pipeline's job — kept separate on purpose).

## Plan — how

1. **Model** (`agent/models.py`): `AssetMetrics`, `PairCorrelation`, `BacktestConfig`,
   `BacktestResult`, and the payload `ComparisonResult` (+ JSON round-trip helpers).
2. **Tool** (`agent/tools/compare.py`, deterministic, numpy-only): `align_closes`
   (date intersection), `asset_metrics` (252-day annualization, rf=0), `correlate`
   (pairwise Pearson + trailing-window series), `run_backtest` (weighted portfolio,
   rebalance schedule, turnover-charged cost).
3. **Skills**: `compare-viz` (HTML — rebased lines + equity curves + rolling-corr
   panel; single-sources the kline_viz ECharts vendor) and `compare-office`
   (xlsx/pptx/docx), each with standard `SKILL.md` frontmatter.
4. **Report builder**: `comparison_report_builder` dispatches formats → the two
   skills, loading each skill package at dispatch.
5. **Harness** (`agent/comparison.py`): `run_comparison(...)` runs Plan → Act →
   Observe → Validate, **reusing the P5 orchestrator's bounded `_act`** for retry,
   then validates provenance + artifacts-on-disk.
6. **CLI** (`agent/compare_run.py`, `agent-compare`): defaults to Gold (GC=F) vs
   Bitcoin (BTC-USD); `--tickers/--weights/--rebalance/--cost-bps/--outputs`;
   `--plan-only` is offline.

**Files produced:** `agent/tools/compare.py`, `agent/comparison.py`,
`agent/compare_run.py`, `agent/skills/compare_viz/*`, `agent/skills/compare_office/*`;
model additions in `agent/models.py`; `comparison_report_builder` in
`agent/subagents/report_builder.py`; `tests/{comparison_fixtures,test_compare,
test_comparison_pipeline,test_comparison_render,test_compare_cli}.py`.

## Test — how we know it's done

| ID | Type | Assertion |
|----|------|-----------|
| T7.1 | Unit | `align_closes` returns the date intersection; disjoint dates → empty (`test_compare.py`). |
| T7.2 | Unit | `asset_metrics` hits hand-checked values (total return, −25% drawdown + its window). |
| T7.3 | Unit | `correlate` = +1 on identical returns, −1 on inverse; rolling series labelled by each window's last date. |
| T7.4 | Unit | `run_backtest` buy-&-hold tracks price exactly; monthly rebalance counts month boundaries and its cost lowers the ending value vs frictionless. |
| T7.5 | Integration | `run_comparison` (offline stub) yields 2 metrics, 1 pair, 2 backtests, 4 artifacts on disk; payload JSON round-trips. |
| T7.6 | Integration | Non-overlapping assets → `ValidationError`; a single ticker → `ValueError`. |
| T7.7 | Unit | HTML is self-contained (no CDN, `echarts.init` present) and escapes an injected `<script>` in the title. |
| T7.8 | Unit | xlsx has the 6 backtest-底稿 tabs with per-asset source URLs; pptx/docx open and carry the methodology. |
| T7.9 | Unit | `agent-compare --plan-only` prints the plan/weights offline; a full stubbed run writes the requested artifacts. |
| T7.10 | Unit | All five shipped skills (incl. `compare-viz`/`compare-office`) pass the standard-frontmatter check (`test_skills.py`). |

**Exit criteria:** T7.1–T7.10 green in CI (offline, no key); `ruff` + `mypy --strict`
clean; the single-ticker pipeline and its tests are untouched.

## Run it

```bash
pip install -e ".[dev,full]"              # numpy + Office renderers + requests
python -m agent.compare_run --plan-only   # offline: gold vs bitcoin plan
python -m agent.compare_run \
  --tickers GC=F,BTC-USD --rebalance monthly --cost-bps 10 \
  --outputs html,xlsx,pptx,docx           # → artifacts/gold_vs_bitcoin_comparison.*
```
