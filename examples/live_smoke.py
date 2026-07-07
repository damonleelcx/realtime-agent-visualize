"""Live end-to-end smoke test (P1 → P2 → P3) against the real Claude model.

Run:
    pip install -e ".[full,sdk]"      # requests + anthropic
    # ensure ANTHROPIC_API_KEY is exported (or in .env, loaded by your shell)
    python examples/live_smoke.py [TICKER] [START] [END]

Defaults to NVDA over the ChatGPT era. Prints the fetched data, detected
inflections, curated events, and the event↔inflection alignments, then checks
citation integrity (P-INV-2) on the live output.
"""

from __future__ import annotations

import os
import sys

from agent.llm import AnthropicClient
from agent.subagents import event_curator, signal_analyst
from agent.tools import detect_inflections, market_data, news_fetch


def main() -> int:
    ticker = sys.argv[1] if len(sys.argv) > 1 else "NVDA"
    start = sys.argv[2] if len(sys.argv) > 2 else "2022-09-01"
    end = sys.argv[3] if len(sys.argv) > 3 else "2023-07-01"

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY not set — export it or load your .env first.")
        return 1

    client = AnthropicClient()

    series = market_data(ticker, start, end)
    inflections = detect_inflections(series, top_n=6)
    news = news_fetch(f"{ticker} OpenAI ChatGPT AI chip", start, end, limit=40)
    src = news[0].prov.source if news else "none"
    print(f"{ticker} {start}..{end}: {len(series.bars)} bars, "
          f"{len(inflections)} inflections, {len(news)} news (source={src})")

    events = event_curator(news, ticker, (start, end), client=client)
    print(f"\ncurated {len(events)} events:")
    for e in events:
        print(f"  {e.date} [{e.impact.value:6}] {e.title[:52]!r}  refs={len(e.news_refs)}")

    aligns = signal_analyst(inflections, events, client=client, window_days=45)
    print(f"\n{len(aligns)} alignments:")
    for a in aligns:
        top = a.events[0].title[:44]
        print(f"  {a.inflection.date} {a.inflection.kind.value:12} <- {top!r}  "
              f"lag={a.lag_days}d  conf={a.confidence:.2f}")

    # P-INV-2: every cited URL exists among the fetched news items.
    urls = {n.url for n in news}
    assert all(all(r in urls for r in e.news_refs) for e in events), "P-INV-2 violated"
    print("\nP-INV-2 (citation integrity) holds on live output.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
