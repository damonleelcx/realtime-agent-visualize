# Skill: kline-viz

Renders one `AnalysisResult` into an **interactive, self-contained HTML** report.

## When to use

Load when the report_builder needs the browser deliverable — a candlestick chart
with AI-industry events aligned to price inflections, clickable back to sources.

## Contract

`render_html(result: AnalysisResult) -> str` — a pure function. No fetch, no
recompute, no network.

- **Chart:** ECharts candlestick (OHLC) + a volume subplot. Hover shows OHLCV and
  the bar's `fetched_at`.
- **Inflection markers** at each `Inflection.date`, colored by `InflectionKind`
  (see `KIND_COLORS`).
- **Event markers** at aligned inflection dates. Click → a drill-down panel with
  the `CuratedEvent` rationale, impact rating, `Alignment.lag_days`/confidence,
  and **clickable `source_url` links** (可溯源).
- **Graceful empty:** with no alignments the chart still renders, plus a visible
  "no events sourced" note.

## Security (enforced at render time)

- `vendor/echarts.min.js` is **inlined**, never linked — the file opens offline
  via `file://` with no CDN/CORS dependency (P-INV-5).
- Every interpolated field goes through `html.escape`; every `href` URL is
  validated (`http`/`https`, non-empty) before emission, else the link is dropped
  and only escaped text remains.
- Embedded JSON has `<`/`>` unicode-escaped so no datum can break out of a
  `<script>` tag.
- Nothing from the environment is ever interpolated — no secret can reach the file.
