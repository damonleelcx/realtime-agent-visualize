"""`kline-viz` skill — render the interactive, self-contained HTML (docs/phases/P4).

Pure function of AnalysisResult. No fetch, no recompute, no network. Security is
enforced at render time:
- ECharts is read from vendor/ and INLINED (never linked) → self-contained,
  offline-openable, no CORS/CDN risk (P-INV-5).
- Every interpolated data field passes through html.escape; source URLs are
  validated before being emitted as <a href> (P-INV-4/T4.3).
- Embedded JSON has its `<`/`>` unicode-escaped so no data can break out of the
  <script> tag, while escaped sequences like `&lt;` stay literal in the file.
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from ...models import Alignment, AnalysisResult, InflectionKind
from ...tools._util import valid_http_url

_VENDOR = Path(__file__).parent / "vendor" / "echarts.min.js"

# Inflection markers colored by kind (G4.2).
KIND_COLORS: dict[InflectionKind, str] = {
    InflectionKind.TURNING_UP: "#26a69a",
    InflectionKind.TURNING_DOWN: "#ef5350",
    InflectionKind.ACCELERATE: "#ab47bc",
    InflectionKind.BREAKOUT_UP: "#66bb6a",
    InflectionKind.BREAKDOWN: "#e53935",
}


def _js_json(obj: Any) -> str:
    """JSON safe to embed inside a <script>: no raw `<`/`>` can break the tag."""
    return json.dumps(obj, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e")


def _drill_fragment(alignment: Alignment) -> str:
    """Pre-escaped HTML for one inflection's drill-down panel (rationale +
    impact + lag + clickable, validated source links)."""
    blocks: list[str] = []
    for ev in alignment.events:
        links: list[str] = []
        for url in ev.news_refs:
            if valid_http_url(url):
                href = html.escape(url, quote=True)
                links.append(
                    f'<a href="{href}" target="_blank" rel="noopener">{html.escape(url)}</a>'
                )
            else:  # never emit an unvalidated href — keep escaped text only
                links.append(html.escape(url))
        srcs = " · ".join(links) if links else "—"
        blocks.append(
            f'<div class="evt">'
            f'<div class="evt-h">'
            f'<span class="badge {html.escape(ev.impact.value)}">{html.escape(ev.impact.value.upper())}</span> '
            f'<b>{html.escape(ev.title)}</b> '
            f'<span class="date">{html.escape(ev.date)}</span></div>'
            f'<div class="rat">{html.escape(ev.rationale)}</div>'
            f'<div class="meta">lag {alignment.lag_days}d · confidence {alignment.confidence:.0%}</div>'
            f'<div class="src">Sources: {srcs}</div>'
            f"</div>"
        )
    expl = html.escape(alignment.explanation)
    return f'<div class="drill"><div class="expl">{expl}</div>{"".join(blocks)}</div>'


def build_view_model(result: AnalysisResult) -> dict[str, Any]:
    """Assemble the JSON data + drill map the front-end consumes."""
    bars = result.series.bars
    dates = [b.date for b in bars]
    ohlc = [[b.open, b.close, b.low, b.high] for b in bars]
    vol = [b.volume for b in bars]
    fetched = [b.prov.fetched_at for b in bars]
    price_at = {b.date: b.close for b in bars}

    inflections = [
        {
            "date": inf.date,
            "price": inf.price,
            "kind": inf.kind.value,
            "color": KIND_COLORS.get(inf.kind, "#888"),
            "significance": inf.significance,
        }
        for inf in result.inflections
    ]

    events = []
    drill: dict[str, str] = {}
    for a in result.alignments:
        d = a.inflection.date
        events.append({"date": d, "price": price_at.get(d, a.inflection.price)})
        drill[d] = _drill_fragment(a)

    data = {
        "ticker": result.ticker,
        "range": list(result.range),
        "generatedAt": result.generated_at,
        "dates": dates,
        "ohlc": ohlc,
        "vol": vol,
        "fetched": fetched,
        "inflections": inflections,
        "events": events,
        "hasEvents": bool(result.alignments),
    }
    return {"data": data, "drill": drill}


def render_html(result: AnalysisResult) -> str:
    vm = build_view_model(result)
    echarts_js = _VENDOR.read_text(encoding="utf-8")
    title = html.escape(f"{result.ticker} — market & AI-event analysis")
    note = (
        ""
        if vm["data"]["hasEvents"]
        else '<div class="note">No industry events were sourced for this window — '
        "K-line and inflections are shown without event annotations.</div>"
    )
    return _TEMPLATE.format(
        title=title,
        ticker=html.escape(result.ticker),
        range0=html.escape(result.range[0]),
        range1=html.escape(result.range[1]),
        generated=html.escape(result.generated_at),
        note=note,
        data_json=_js_json(vm["data"]),
        drill_json=_js_json(vm["drill"]),
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
  .wrap {{ display: flex; gap: 16px; padding: 16px 24px; align-items: flex-start; }}
  #chart {{ flex: 1 1 auto; height: 560px; min-width: 0; background: #fff;
           border: 1px solid #eee; border-radius: 8px; }}
  #panel {{ flex: 0 0 320px; background: #fff; border: 1px solid #eee; border-radius: 8px;
           padding: 16px; max-height: 560px; overflow: auto; }}
  #panel h2 {{ font-size: 14px; margin: 0 0 8px; }}
  #panel .hint {{ color: #999; font-size: 13px; }}
  .note {{ margin: 8px 24px 0; padding: 8px 12px; background: #fff8e1; border: 1px solid #ffe082;
          border-radius: 6px; font-size: 13px; color: #8d6e00; }}
  .drill .expl {{ font-size: 13px; color: #444; margin-bottom: 10px; }}
  .evt {{ border-top: 1px solid #eee; padding: 8px 0; }}
  .evt-h {{ font-size: 13px; }}
  .badge {{ display: inline-block; font-size: 10px; font-weight: 700; padding: 1px 6px;
           border-radius: 4px; color: #fff; vertical-align: middle; }}
  .badge.high {{ background: #e53935; }} .badge.medium {{ background: #fb8c00; }}
  .badge.low {{ background: #7cb342; }}
  .date {{ color: #999; font-size: 12px; }}
  .rat {{ font-size: 13px; color: #333; margin: 4px 0; }}
  .meta {{ font-size: 12px; color: #888; }}
  .src {{ font-size: 12px; margin-top: 4px; word-break: break-all; }}
  .src a {{ color: #3949ab; }}
  .legend {{ font-size: 12px; color: #777; padding: 0 24px 16px; }}
  .legend span {{ margin-right: 12px; }}
  .dot {{ display: inline-block; width: 10px; height: 10px; border-radius: 50%;
         margin-right: 4px; vertical-align: middle; }}
</style>
</head>
<body>
<header>
  <h1>{ticker} — 行情与 AI 行业事件对齐分析</h1>
  <div class="sub">Range {range0} .. {range1} · generated {generated} · click an event marker to trace its source</div>
</header>
{note}
<div class="wrap">
  <div id="chart"></div>
  <div id="panel"><h2>Event detail</h2><div class="hint">Click a blue event marker on the chart to see the aligned event, impact rating, and clickable sources.</div></div>
</div>
<div class="legend" id="legend"></div>
<script>{echarts}</script>
<script>window.__DATA__ = {data_json}; window.__DRILL__ = {drill_json};</script>
<script>
(function() {{
  var D = window.__DATA__, DRILL = window.__DRILL__;
  var chart = echarts.init(document.getElementById('chart'));
  var infMarks = D.inflections.map(function(i) {{
    return {{ coord: [i.date, i.price], value: i.kind, itemStyle: {{ color: i.color }},
             symbol: 'pin', symbolSize: 34 }};
  }});
  var option = {{
    animation: false,
    tooltip: {{ trigger: 'axis', axisPointer: {{ type: 'cross' }}, formatter: function(ps) {{
      var k = ps.find(function(x) {{ return x.seriesName === 'K'; }});
      if (!k) return '';
      var i = k.dataIndex, o = D.ohlc[i], v = D.vol[i];
      return '<b>' + D.dates[i] + '</b><br>O ' + o[0] + '  C ' + o[1] + '<br>L ' + o[2] +
             '  H ' + o[3] + '<br>Vol ' + v + '<br><span style="color:#999">fetched ' +
             D.fetched[i] + '</span>';
    }} }},
    axisPointer: {{ link: [{{ xAxisIndex: [0, 1] }}] }},
    grid: [{{ left: 60, right: 20, top: 20, height: '58%' }},
           {{ left: 60, right: 20, top: '74%', height: '16%' }}],
    xAxis: [{{ type: 'category', data: D.dates, boundaryGap: true, axisLine: {{ onZero: false }} }},
            {{ type: 'category', gridIndex: 1, data: D.dates, axisLabel: {{ show: false }} }}],
    yAxis: [{{ scale: true, name: 'Price' }},
            {{ gridIndex: 1, name: 'Vol', axisLabel: {{ show: false }}, splitLine: {{ show: false }} }}],
    dataZoom: [{{ type: 'inside', xAxisIndex: [0, 1] }},
               {{ type: 'slider', xAxisIndex: [0, 1], bottom: 8, height: 16 }}],
    series: [
      {{ name: 'K', type: 'candlestick', data: D.ohlc,
         itemStyle: {{ color: '#26a69a', color0: '#ef5350',
                      borderColor: '#26a69a', borderColor0: '#ef5350' }},
         markPoint: {{ data: infMarks, tooltip: {{ show: false }} }} }},
      {{ name: 'Volume', type: 'bar', xAxisIndex: 1, yAxisIndex: 1, data: D.vol,
         itemStyle: {{ color: '#b0bec5' }} }},
      {{ name: 'Events', type: 'scatter',
         data: D.events.map(function(e) {{ return {{ value: [e.date, e.price], date: e.date }}; }}),
         symbol: 'circle', symbolSize: 15,
         itemStyle: {{ color: '#3949ab', borderColor: '#fff', borderWidth: 2 }}, z: 10 }}
    ]
  }};
  chart.setOption(option);
  function openDrill(d) {{
    var p = document.getElementById('panel');
    p.innerHTML = '<h2>Event detail</h2>' + (DRILL[d] || '<div class="hint">No event for this point.</div>');
  }}
  chart.on('click', function(p) {{
    if (p.seriesName === 'Events' && p.data && p.data.date) openDrill(p.data.date);
    else if (p.componentType === 'markPoint' && p.data && p.data.coord && DRILL[p.data.coord[0]])
      openDrill(p.data.coord[0]);
  }});
  window.addEventListener('resize', function() {{ chart.resize(); }});
  // kind legend
  var seen = {{}}, leg = '';
  D.inflections.forEach(function(i) {{
    if (seen[i.kind]) return; seen[i.kind] = 1;
    leg += '<span><span class="dot" style="background:' + i.color + '"></span>' + i.kind + '</span>';
  }});
  leg += '<span><span class="dot" style="background:#3949ab"></span>event (click to trace)</span>';
  document.getElementById('legend').innerHTML = leg;
}})();
</script>
</body>
</html>
"""
