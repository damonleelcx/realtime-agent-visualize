"""CLI entrypoint — the Loop layer (docs/00-overview.md §2, §5).

    python -m agent.run "Analyze NVDA over the last 5 years ..."

P0 SCOPE: parses the task, prints the plan and a well-formed (empty)
AnalysisResult as JSON, and exits 0. It does not fetch or render anything yet.
"""

from __future__ import annotations

import argparse
import sys

from .orchestrator import Orchestrator


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="agent.run",
        description="Realtime market-data analysis agent (P0 scaffolding).",
    )
    parser.add_argument("task", help="Natural-language research task.")
    parser.add_argument("--ticker", default="NVDA", help="Ticker symbol (default: NVDA).")
    parser.add_argument("--start", default="", help="Start date YYYY-MM-DD.")
    parser.add_argument("--end", default="", help="End date YYYY-MM-DD.")
    parser.add_argument(
        "--outputs", default="html",
        help="Comma-separated deliverables: html,xlsx,pptx,docx (P4).",
    )
    args = parser.parse_args(argv)

    orch = Orchestrator()

    print(f"TASK: {args.task}\n")
    print("PLAN:")
    for i, step in enumerate(orch.plan(args.task), 1):
        print(f"  {i}. {step}")
    print()

    result = orch.run(
        ticker=args.ticker,
        start=args.start,
        end=args.end,
        outputs=[o.strip() for o in args.outputs.split(",") if o.strip()],
    )

    print("RESULT (P0 stub — empty until P1+):")
    print(result.to_json())
    return 0


if __name__ == "__main__":
    sys.exit(main())
