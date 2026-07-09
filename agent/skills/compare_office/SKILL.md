---
name: compare-office
description: Render a multi-asset ComparisonResult into the local Office trio — an xlsx backtest workbook (prices, returns, correlation, backtests, sources), a pptx comparison deck, and a docx narrative — each traceable to its per-asset source_url. Load in the comparison_report_builder when producing the Office deliverables for a gold-vs-bitcoin style comparison.
---

# Skill: compare-office

Renders one `ComparisonResult` into the Office trio — all pure functions, no
fetch, no recompute, no network, all driven from the same payload.

## Contract

- `to_xlsx(result) -> bytes` — backtest 底稿. Tabs: **Overview** (per-asset
  metrics), **Prices** (aligned close matrix), **Returns** (daily returns),
  **Correlation** (pearson + rolling), **Backtests** (config, results, equity
  curves), **Sources** (per-asset `source_url`).
- `to_pptx(result) -> bytes` — comparison deck: title → context → per-asset
  performance → strategy backtests → correlation → sources appendix.
- `to_docx(result) -> bytes` — narrative report: summary, methodology (252-day
  annualization, rf=0, cost model, date-intersection), per-asset findings,
  backtest findings (rebalanced vs buy-&-hold, cost drag), correlation, sources.

## Rules

- Never interpolate anything from the environment — no secret reaches a file.
- Graceful empty: with no correlations/backtests, emit the tabs/slides/sections
  with empty bodies rather than raising.
- Office files are validated by re-opening (openpyxl / python-pptx / python-docx)
  and asserting structure — never byte-diffed.
