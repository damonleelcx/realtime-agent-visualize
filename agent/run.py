"""CLI entrypoint — the Loop (docs/00-overview.md §2, §5).

    python -m agent.run "Analyze NVDA over the last 5 years, mark AI events ..."

The Loop is thin: sense the task, hand exactly one goal to the Harness
(orchestrator), observe the returned summary, terminate on success or the
Harness's turn/budget cap. `--plan-only` prints the plan without running the
pipeline (offline; no network, no LLM).
"""

from __future__ import annotations

import argparse
import re
import sys

from .orchestrator import (
    Orchestrator,
    TerminationError,
    ValidationError,
    _default_range,  # noqa: PLC2701 — internal helper, intentional reuse
    run,
)


def _infer_ticker(task: str, default: str = "NVDA") -> str:
    """Best-effort ticker from the task; --ticker overrides this."""
    m = re.search(r"\b([A-Z]{1,5})\b", task)
    return m.group(1) if m else default


def _force_utf8_stdio() -> None:
    """Keep non-ASCII step labels (→, ↔) printable on a legacy Windows console.

    A cp936/GBK console raises UnicodeEncodeError on those glyphs; reconfigure to
    UTF-8 with replacement so the Loop never crashes on its own progress output.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    _force_utf8_stdio()
    parser = argparse.ArgumentParser(
        prog="agent.run",
        description="Autonomous market-data + AI-event analysis agent.",
    )
    parser.add_argument("task", help="Natural-language research task.")
    parser.add_argument("--ticker", default="", help="Ticker symbol (default: inferred/NVDA).")
    parser.add_argument("--start", default="", help="Start date YYYY-MM-DD (default: 5y ago).")
    parser.add_argument("--end", default="", help="End date YYYY-MM-DD (default: today).")
    parser.add_argument("--outputs", default="html,xlsx,pptx,docx",
                        help="Comma-separated deliverables: html,xlsx,pptx,docx.")
    parser.add_argument("--out-dir", default="artifacts", help="Output directory.")
    parser.add_argument("--plan-only", action="store_true",
                        help="Print the plan and exit (no network, no LLM).")
    args = parser.parse_args(argv)

    orch = Orchestrator()
    ticker = args.ticker or _infer_ticker(args.task)
    outputs = [o.strip() for o in args.outputs.split(",") if o.strip()]

    print(f"TASK: {args.task}\n")
    print("PLAN:")
    for i, step in enumerate(orch.plan(args.task), 1):
        print(f"  {i}. {step}")
    print()

    if args.plan_only:
        print("(--plan-only: not executing the pipeline)")
        return 0

    start, end = _default_range(args.start, args.end)
    from .backend import default_client  # noqa: PLC0415 — only needed for a real run

    try:
        run_result = run(
            ticker, start, end, outputs,
            client=default_client(), out_dir=args.out_dir,
        )
    except (TerminationError, ValidationError) as exc:
        print(f"RUN FAILED: {exc}", file=sys.stderr)
        return 2

    r = run_result.result
    print("RESULT:")
    print(f"  {r.ticker}  {r.range[0]}..{r.range[1]}")
    print(f"  bars={len(r.series.bars)}  inflections={len(r.inflections)}  "
          f"events={len(r.events)}  alignments={len(r.alignments)}")
    print("ARTIFACTS:")
    for p in run_result.artifacts:
        print(f"  {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
