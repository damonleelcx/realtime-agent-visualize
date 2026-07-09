"""`compare-viz` skill — interactive self-contained HTML for a comparison (P7).

Pure function of `ComparisonResult`. No fetch, no recompute, no network. Same
render-time security as `kline-viz`: ECharts is inlined (single-sourced from the
kline_viz vendor dir), every field is `html.escape`d, every href validated, and
embedded JSON has `<`/`>` unicode-escaped so no datum can break out of a script.
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from ...models import ComparisonResult
from ...tools._util import valid_http_url

# Single-source the ~1MB vendor bundle from the kline_viz skill (no duplication).
_VENDOR = Path(__file__).parents[1] / "kline_viz" / "vendor" / "echarts.min.js"

_LINE_COLORS = ["#3949ab", "#e53935", "#00897b", "#fb8c00", "#8e24aa", "#546e7a"]


def _js_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e")


def _rebase(values: list[float]) -> list[float]:
    """Rebase a value series to 100 at its first point (comparable performance)."""
    if not values or values[0] == 0:
        return [0.0 for _ in values]
    base = values[0]
    return [round(v / base * 100.0, 4) for v in values]


def build_view_model(result: ComparisonResult) -> dict[str, Any]:
    dates = result.aligned_dates
    closes_by_ticker: dict[str, dict[str, float]] = {
        s.ticker: {b.date: b.close for b in s.bars} for s in result.series
    }

    lines: list[dict[str, Any]] = []
    ci = 0
    for s in result.series:
        cb = closes_by_ticker[s.ticker]
        series_vals = [cb[d] for d in dates]
        lines.append({
            "name": s.ticker, "kind": "asset",
            "color": _LINE_COLORS[ci % len(_LINE_COLORS)],
            "values": _rebase(series_vals),
        })
        ci += 1
    for bt in result.backtests:
        eq_by_date = dict(bt.equity_curve)
        series_vals = [eq_by_date.get(d, 0.0) for d in dates]
        lines.append({
            "name": bt.config.name, "kind": "strategy",
            "color": _LINE_COLORS[ci % len(_LINE_COLORS)],
            "values": _rebase(series_vals),
        })
        ci += 1

    corr = None
    if result.correlations:
        c = result.correlations[0]
        corr = {
            "label": f"{c.ticker_a} vs {c.ticker_b} ({c.rolling_window}d rolling)",
            "pearson": round(c.pearson, 3),
            "dates": [d for d, _ in c.rolling],
            "values": [round(v, 4) for _, v in c.rolling],
        }

    return {
        "title": result.title, "range": list(result.range),
        "generatedAt": result.generated_at, "dates": dates,
        "lines": lines, "corr": corr,
    }


def _metrics_rows(result: ComparisonResult) -> str:
    rows = []
    for m in result.metrics:
        rows.append(
            "<tr>"
            f"<td>{html.escape(m.ticker)}</td>"
            f"<td>{m.total_return:+.1%}</td>"
            f"<td>{m.cagr:+.1%}</td>"
            f"<td>{m.annual_vol:.1%}</td>"
            f"<td>{m.sharpe:.2f}</td>"
            f"<td>{m.max_drawdown:.1%}</td>"
            f"<td>{html.escape(m.drawdown_window[0])} → {html.escape(m.drawdown_window[1])}</td>"
            "</tr>"
        )
    return "".join(rows)


def _backtest_rows(result: ComparisonResult) -> str:
    rows = []
    for b in result.backtests:
        w = ", ".join(f"{html.escape(t)} {v:.0%}" for t, v in b.config.weights.items())
        rows.append(
            "<tr>"
            f"<td>{html.escape(b.config.name)}</td>"
            f"<td>{html.escape(w)}</td>"
            f"<td>{html.escape(b.config.rebalance)}</td>"
            f"<td>{b.total_return:+.1%}</td>"
            f"<td>{b.cagr:+.1%}</td>"
            f"<td>{b.annual_vol:.1%}</td>"
            f"<td>{b.sharpe:.2f}</td>"
            f"<td>{b.max_drawdown:.1%}</td>"
            f"<td>{b.n_rebalances}</td>"
            f"<td>{b.cost_drag:.2%}</td>"
            "</tr>"
        )
    return "".join(rows)


def _source_links(result: ComparisonResult) -> str:
    items = []
    for s in result.series:
        url = s.prov.source_url
        if valid_http_url(url):
            href = html.escape(url, quote=True)
            link = f'<a href="{href}" target="_blank" rel="noopener">{html.escape(url)}</a>'
        else:
            link = html.escape(url) or "—"
        items.append(
            f"<li><b>{html.escape(s.ticker)}</b> "
            f"<span class='src-meta'>({html.escape(s.prov.source)})</span> {link}</li>"
        )
    return "".join(items)


def render_comparison_html(result: ComparisonResult) -> str:
    vm = build_view_model(result)
    echarts_js = _VENDOR.read_text(encoding="utf-8")
    title = html.escape(f"{result.title} — multi-asset comparison")
    return _TEMPLATE.format(
        title=title,
        heading=html.escape(result.title),
        range0=html.escape(result.range[0]),
        range1=html.escape(result.range[1]),
        generated=html.escape(result.generated_at),
        n_days=len(result.aligned_dates),
        metrics_rows=_metrics_rows(result),
        backtest_rows=_backtest_rows(result),
        sources=_source_links(result),
        data_json=_js_json(vm),
        echarts=echarts_js,
    )


_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  body {{ font-family: -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
         margin: 0; color: #1a1a1a; background: #fafafa; }}
  header {{ padding: 16px 24px; border-bottom: 1px solid #e0e0e0; background: #fff; }}
  header h1 {{ font-size: 18px; margin: 0 0 4px; }}
  header .sub {{ color: #777; font-size: 13px; }}
  .chart {{ margin: 16px 24px; background: #fff; border: 1px solid #eee; border-radius: 8px; }}
  #perf {{ height: 460px; }}
  #corr {{ height: 240px; }}
  section {{ margin: 16px 24px; }}
  h2 {{ font-size: 15px; margin: 0 0 8px; }}
  table {{ border-collapse: collapse; width: 100%; background: #fff; font-size: 13px;
          border: 1px solid #eee; border-radius: 8px; overflow: hidden; }}
  th, td {{ text-align: right; padding: 7px 10px; border-bottom: 1px solid #f0f0f0; }}
  th:first-child, td:first-child {{ text-align: left; }}
  thead th {{ background: #f5f5f7; font-weight: 600; }}
  ul.sources {{ list-style: none; padding: 0; font-size: 13px; }}
  ul.sources li {{ padding: 4px 0; word-break: break-all; }}
  ul.sources a {{ color: #3949ab; }}
  .src-meta {{ color: #999; }}
</style>
</head>
<body>
<header>
  <h1>{heading} — 多资产对比与策略回测</h1>
  <div class="sub">Range {range0} .. {range1} · {n_days} common trading days · generated {generated}</div>
</header>
<div class="chart"><div id="perf"></div></div>
<div class="chart"><div id="corr"></div></div>
<section>
  <h2>Per-asset performance (buy &amp; hold)</h2>
  <table>
    <thead><tr><th>Asset</th><th>Total</th><th>CAGR</th><th>Vol</th><th>Sharpe</th>
      <th>Max DD</th><th>Drawdown window</th></tr></thead>
    <tbody>{metrics_rows}</tbody>
  </table>
</section>
<section>
  <h2>Strategy backtests</h2>
  <table>
    <thead><tr><th>Strategy</th><th>Weights</th><th>Rebalance</th><th>Total</th><th>CAGR</th>
      <th>Vol</th><th>Sharpe</th><th>Max DD</th><th>Rebals</th><th>Cost drag</th></tr></thead>
    <tbody>{backtest_rows}</tbody>
  </table>
</section>
<section>
  <h2>Sources (可溯源)</h2>
  <ul class="sources">{sources}</ul>
</section>
<script>{echarts}</script>
<script>window.__CMP__ = {data_json};</script>
<script>
(function() {{
  var D = window.__CMP__;
  var perf = echarts.init(document.getElementById('perf'));
  perf.setOption({{
    animation: false,
    title: {{ text: 'Rebased performance (start = 100)', left: 12, top: 8,
             textStyle: {{ fontSize: 13, color: '#555' }} }},
    tooltip: {{ trigger: 'axis' }},
    legend: {{ top: 8, right: 12, data: D.lines.map(function(l) {{ return l.name; }}) }},
    grid: {{ left: 56, right: 24, top: 48, bottom: 56 }},
    xAxis: {{ type: 'category', data: D.dates, boundaryGap: false }},
    yAxis: {{ scale: true, name: 'Index (=100)' }},
    dataZoom: [{{ type: 'inside' }}, {{ type: 'slider', bottom: 8, height: 16 }}],
    series: D.lines.map(function(l) {{
      return {{ name: l.name, type: 'line', data: l.values, showSymbol: false,
               lineStyle: {{ width: l.kind === 'strategy' ? 2.5 : 1.5,
                            type: l.kind === 'strategy' ? 'solid' : 'solid' }},
               itemStyle: {{ color: l.color }},
               areaStyle: l.kind === 'strategy' ? {{ opacity: 0.05 }} : null }};
    }})
  }});
  var corrEl = document.getElementById('corr');
  if (D.corr && D.corr.values.length) {{
    var corr = echarts.init(corrEl);
    corr.setOption({{
      animation: false,
      title: {{ text: 'Rolling correlation — ' + D.corr.label + ' (full-window r=' + D.corr.pearson + ')',
               left: 12, top: 8, textStyle: {{ fontSize: 13, color: '#555' }} }},
      tooltip: {{ trigger: 'axis' }},
      grid: {{ left: 56, right: 24, top: 44, bottom: 30 }},
      xAxis: {{ type: 'category', data: D.corr.dates, boundaryGap: false }},
      yAxis: {{ min: -1, max: 1, name: 'r' }},
      series: [{{ type: 'line', data: D.corr.values, showSymbol: false,
                 itemStyle: {{ color: '#00897b' }},
                 markLine: {{ silent: true, symbol: 'none',
                   data: [{{ yAxis: 0 }}], lineStyle: {{ color: '#bbb' }} }} }}]
    }});
    window.addEventListener('resize', function() {{ corr.resize(); }});
  }} else {{
    corrEl.parentNode.style.display = 'none';
  }}
  window.addEventListener('resize', function() {{ perf.resize(); }});
}})();
</script>
</body>
</html>
"""
