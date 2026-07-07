"""`detect_inflections` tool — deterministic price turning-point detection.

The auditability backbone (docs/phases/P2): NO LLM, no randomness, no wall
clock. Same bars → identical output, so a reader can re-run the math. Change
points come from ruptures PELT (exact, deterministic) on log-returns; each is
then labelled by a transparent slope/gap classifier whose constants are
recorded in `Inflection.detector`.
"""

from __future__ import annotations

import numpy as np
import ruptures as rpt

from ..models import Inflection, InflectionKind, PriceSeries

# --- Tunable constants (recorded in `detector` so a run is reproducible) ----- #
MIN_BARS = 5          # below this a change-point search is meaningless
BASE_PEN = 8.0        # PELT penalty at sensitivity=1.0 (higher pen → fewer points)
WIN = 5               # slope-fit half-window (bars) on each side of a boundary
GAP_K = 2.5           # a single-bar |log-return| > GAP_K·σ is a gap candidate...
ABS_GAP = 0.08        # ...but must also clear this absolute floor (~8% move), so a
                      #    smooth trend with tiny σ doesn't flag every bar as a gap
ACCEL_RATIO = 1.6     # |slope_after| > ACCEL_RATIO·|slope_before| ⇒ acceleration


def _slope(values: np.ndarray) -> float:
    """Least-squares slope of `values` vs its index. 0.0 if too short."""
    n = len(values)
    if n < 2:
        return 0.0
    x = np.arange(n, dtype=float)
    return float(np.polyfit(x, values, 1)[0])


def _mean(values: np.ndarray) -> float:
    """Mean, or 0.0 for an empty slice (avoids nan at series edges)."""
    return float(np.mean(values)) if len(values) else 0.0


def detect_inflections(
    series: PriceSeries,
    top_n: int = 25,
    sensitivity: float = 1.0,
) -> list[Inflection]:
    """Detect and rank price inflections in `series`.

    Deterministic. Returns the `top_n` most significant points, each labelled
    TURNING_UP / TURNING_DOWN / ACCELERATE / BREAKOUT_UP / BREAKDOWN and carrying
    the evidence bars behind it. A series shorter than MIN_BARS returns [].
    """
    bars = series.bars
    if len(bars) < MIN_BARS:
        return []

    closes = np.array([b.close for b in bars], dtype=float)
    dates = [b.date for b in bars]
    n = len(closes)
    logret = np.diff(np.log(closes))          # logret[i] = ln(close[i+1]/close[i])
    sigma = float(np.std(logret)) or 1e-9

    penalty = BASE_PEN / max(sensitivity, 1e-9)
    detector = f"pelt:rbf:pen={penalty:.4g};win={WIN};gap_k={GAP_K}"

    # Change-point detection on log-returns (rbf cost; PELT is exact/deterministic).
    algo = rpt.Pelt(model="rbf", min_size=2, jump=1).fit(logret.reshape(-1, 1))
    bkps = algo.predict(pen=penalty)          # boundary indices into logret; last == len(logret)

    # Candidate trigger bars = PELT boundaries ∪ single-bar gaps. Gaps are scanned
    # independently because rbf can absorb a lone spike PELT won't place a boundary on.
    gap_threshold = max(GAP_K * sigma, ABS_GAP)
    triggers: set[int] = {min(max(b, 1), n - 1) for b in bkps[:-1]}
    triggers |= {i + 1 for i in range(len(logret)) if abs(logret[i]) > gap_threshold}

    raw: list[tuple[int, InflectionKind, float, tuple[int, int]]] = []
    for t in sorted(triggers):
        lo, hi = max(0, t - WIN), min(n, t + WIN + 1)
        before, after = closes[lo:t + 1], closes[t:hi]
        s_before, s_after = _slope(before), _slope(after)

        gap = logret[t - 1]                    # return leading into bar t
        magnitude = abs(_mean(logret[max(0, t - WIN):t]) -
                        _mean(logret[t:min(len(logret), t + WIN)]))

        if abs(gap) > gap_threshold:
            kind = InflectionKind.BREAKOUT_UP if gap > 0 else InflectionKind.BREAKDOWN
            magnitude += abs(float(gap))       # gap bonus
        elif s_before < 0 <= s_after:
            kind = InflectionKind.TURNING_UP
        elif s_before > 0 >= s_after:
            kind = InflectionKind.TURNING_DOWN
        elif abs(s_after) > ACCEL_RATIO * abs(s_before) and s_before != 0:
            kind = InflectionKind.ACCELERATE
        else:
            continue                           # not a material inflection → skip

        raw.append((t, kind, magnitude, (lo, hi - 1)))

    if not raw:
        return []

    max_mag = max(m for _, _, m, _ in raw) or 1e-9
    inflections = [
        Inflection(
            date=dates[t],
            kind=kind,
            significance=round(mag / max_mag, 6),
            price=closes[t],
            window=(dates[lo], dates[hi]),
            evidence_bars=[dates[lo], dates[t], dates[hi]],
            detector=detector,
        )
        for t, kind, mag, (lo, hi) in raw
    ]

    # Rank by significance desc; deterministic tie-break on date asc.
    inflections.sort(key=lambda inf: (-inf.significance, inf.date))
    return inflections[:top_n]
