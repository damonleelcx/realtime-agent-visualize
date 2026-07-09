---
name: compare-viz
description: Render a multi-asset ComparisonResult into an interactive, self-contained HTML report — rebased performance lines, backtest equity curves, a rolling-correlation panel, and traceable per-asset sources. Load in the comparison_report_builder when producing the browser deliverable for a gold-vs-bitcoin style comparison.
---

# Skill: compare-viz

Renders one `ComparisonResult` into an **interactive, self-contained HTML** report
comparing two or more assets and one or more strategy backtests.

## When to use

Load for the browser deliverable of a *comparison* task (e.g. Gold vs Bitcoin) —
distinct from `kline-viz`, which renders a single-ticker candlestick + event view.

## Contract

`render_comparison_html(result: ComparisonResult) -> str` — a pure function. No
fetch, no recompute, no network.

- **Performance chart:** every asset's close rebased to 100 at the window start,
  plus each backtest's equity curve rebased to 100, on one shared axis so relative
  performance is directly comparable.
- **Rolling-correlation panel:** the pairwise trailing-window correlation series.
- **Tables:** per-asset metrics (total/annualized return, vol, Sharpe, max
  drawdown) and per-strategy backtest results (return, drawdown, rebalances, cost
  drag), followed by clickable per-asset **source** links (可溯源).

## Security (enforced at render time)

- `../kline_viz/vendor/echarts.min.js` is **inlined**, never linked — opens
  offline via `file://` with no CDN/CORS dependency (P-INV-5).
- Every interpolated field passes through `html.escape`; every `href` is
  validated (`http`/`https`) before emission, else only escaped text remains.
- Embedded JSON has `<`/`>` unicode-escaped so no datum can break out of a
  `<script>` tag. Nothing from the environment is ever interpolated.
