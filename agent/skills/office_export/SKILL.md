# Skill: office-export

Renders one `AnalysisResult` into the Office trio — all pure functions, no fetch,
no recompute, no network, all driven from the same payload.

## Contract

- `to_xlsx(result) -> bytes` — backtest 底稿. Tabs: **Bars**, **Inflections**,
  **Events**, **Alignments**. Every bar and event row carries its `source_url`
  so the sheet is traceable (P-INV-1).
- `to_pptx(result) -> bytes` — decision-framework deck: title → context →
  inflection overview → per-inflection aligned events + impact → sources appendix.
- `to_docx(result) -> bytes` — narrative report: summary, methodology (the
  deterministic detector id), findings per alignment citing `news_refs`, sources.

## Rules

- Never interpolate anything from the environment — no secret reaches a file (P-INV-4).
- Graceful empty: with no events/alignments, emit the tabs/slides/sections with
  empty bodies rather than raising.
- Office files are validated by re-opening (openpyxl / python-pptx / python-docx)
  and asserting structure — never byte-diffed.
