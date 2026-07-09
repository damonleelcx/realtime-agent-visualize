"""CLI entrypoint for the multi-asset comparison + backtest (docs/phases/P7).

    python -m agent.compare_run --tickers GC=F,BTC-USD --rebalance monthly

Defaults to **Gold (GC=F) vs Bitcoin (BTC-USD)** — the brief's "这类任务" example —
producing one interactive HTML plus the local Office trio (xlsx/pptx/docx). The
pipeline is deterministic and LLM-free, so `--plan-only` needs no network/key and
a full run needs no API key.
"""

from __future__ import annotations

import argparse
import sys

from .comparison import default_weights, run_comparison
from .orchestrator import RunCancelled, TerminationError, ValidationError, _default_range
from .run import _force_utf8_stdio

# The brief's example: gold vs bitcoin. Yahoo symbols, both keyless.
_DEFAULT_TICKERS = "GC=F,BTC-USD"
_LABELS = {"GC=F": "Gold", "BTC-USD": "Bitcoin"}


def _parse_weights(spec: str, tickers: list[str]) -> dict[str, float] | None:
    if not spec:
        return None
    parts = [float(x) for x in spec.split(",") if x.strip()]
    if len(parts) != len(tickers):
        raise SystemExit(f"--weights has {len(parts)} values but {len(tickers)} tickers")
    total = sum(parts)
    if total <= 0:
        raise SystemExit("--weights must sum to a positive number")
    return {t: p / total for t, p in zip(tickers, parts, strict=True)}


def _title(tickers: list[str]) -> str:
    return " vs ".join(_LABELS.get(t, t) for t in tickers)


def main(argv: list[str] | None = None) -> int:
    _force_utf8_stdio()
    parser = argparse.ArgumentParser(
        prog="agent.compare_run",
        description="Deterministic multi-asset comparison + strategy backtest.",
    )
    parser.add_argument("--tickers", default=_DEFAULT_TICKERS,
                        help="Comma-separated symbols (default: GC=F,BTC-USD = gold vs bitcoin).")
    parser.add_argument("--title", default="", help="Report title (default: inferred).")
    parser.add_argument("--weights", default="",
                        help="Comma-separated weights, aligned to --tickers (default: equal).")
    parser.add_argument("--rebalance", default="monthly",
                        choices=["none", "monthly", "quarterly"], help="Rebalance schedule.")
    parser.add_argument("--cost-bps", type=float, default=10.0,
                        help="Round-trip transaction cost per unit turnover (bps).")
    parser.add_argument("--capital", type=float, default=10_000.0, help="Initial capital.")
    parser.add_argument("--rolling-window", type=int, default=60,
                        help="Trailing window (trading days) for rolling correlation.")
    parser.add_argument("--start", default="", help="Start date YYYY-MM-DD (default: 5y ago).")
    parser.add_argument("--end", default="", help="End date YYYY-MM-DD (default: today).")
    parser.add_argument("--outputs", default="html,xlsx,pptx,docx",
                        help="Comma-separated deliverables: html,xlsx,pptx,docx.")
    parser.add_argument("--out-dir", default="artifacts", help="Output directory.")
    parser.add_argument("--plan-only", action="store_true",
                        help="Print the plan and exit (no network).")
    args = parser.parse_args(argv)

    tickers = [t.strip() for t in args.tickers.split(",") if t.strip()]
    if len(tickers) < 2:
        raise SystemExit("need at least two tickers to compare")
    title = args.title or _title(tickers)
    weights = _parse_weights(args.weights, tickers)
    outputs = [o.strip() for o in args.outputs.split(",") if o.strip()]

    print(f"COMPARISON: {title}  ({', '.join(tickers)})\n")
    print("PLAN:")
    from .comparison import _PLAN_STEPS  # noqa: PLC0415
    for i, step in enumerate(_PLAN_STEPS, 1):
        print(f"  {i}. {step}")
    w = weights or default_weights(tickers)
    print("\nWEIGHTS: " + ", ".join(f"{t} {v:.0%}" for t, v in w.items()))
    print(f"REBALANCE: {args.rebalance}  ·  COST: {args.cost_bps:.0f} bps\n")

    if args.plan_only:
        print("(--plan-only: not executing the pipeline)")
        return 0

    start, end = _default_range(args.start, args.end)
    try:
        run_result = run_comparison(
            tickers, start, end, outputs,
            title=title, weights=weights, rebalance=args.rebalance,
            cost_bps=args.cost_bps, initial_capital=args.capital,
            rolling_window=args.rolling_window, out_dir=args.out_dir,
        )
    except (TerminationError, ValidationError, RunCancelled) as exc:
        print(f"RUN FAILED: {exc}", file=sys.stderr)
        return 2

    r = run_result.result
    print("RESULT:")
    print(f"  {r.title}  {r.range[0]}..{r.range[1]}  ·  {len(r.aligned_dates)} common days")
    for m in r.metrics:
        print(f"  {m.ticker:8} total {m.total_return:+.1%}  CAGR {m.cagr:+.1%}  "
              f"vol {m.annual_vol:.1%}  Sharpe {m.sharpe:.2f}  maxDD {m.max_drawdown:.1%}")
    for b in r.backtests:
        print(f"  [{b.config.name}] total {b.total_return:+.1%}  maxDD {b.max_drawdown:.1%}  "
              f"rebalances {b.n_rebalances}  cost drag {b.cost_drag:.2%}")
    print("ARTIFACTS:")
    for p in run_result.artifacts:
        print(f"  {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
