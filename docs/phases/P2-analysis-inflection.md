# P2 · Analysis (Inflection Detection)

> **Timeline:** 1–1.5 h · **Depends on:** [P1](./P1-data-tools.md) · **Blocks:** [P3](./P3-event-curation.md), [P4](./P4-visualization-artifacts.md)
> **Anchors:** [00-overview](../00-overview.md) · [01-conventions](../01-conventions.md)

---

## Spec — what & why

Implement the **deterministic, non-LLM inflection detector** — the auditability backbone of the
whole system. `detect_inflections(series: PriceSeries, top_n=25, sensitivity=1.0) -> list[Inflection]`
takes daily bars and returns the ranked price turning points that P3 will hang events on and P4 will
mark on the K-line. A reader must be able to **re-run the math and get identical results**; that
non-negotiable is why this is an algorithm and not a model call ([overview §11 item 1](../00-overview.md#11-key-trade-offs-system-design-step-24-summary)).

**Goals**
- G2.1 Implement `detect_inflections` matching the tool contract in [conventions §3](../01-conventions.md#3-tool-signature-contracts-deterministic-no-llm-inside) — pure w.r.t. its args, no LLM, no network, raises typed errors.
- G2.2 Emit `Inflection` records exactly per [conventions §2](../01-conventions.md#2-core-data-records-passed-between-layers): `date`, `kind` (one of the five `InflectionKind`s), `significance` (0..1), `price`, `window`, `evidence_bars`, `detector`.
- G2.3 **Change-point detection** via `ruptures` (PELT + `rbf` cost) over log-returns, plus a **slope-based classifier** that labels each detected point as one of `TURNING_UP` / `TURNING_DOWN` / `ACCELERATE` / `BREAKOUT_UP` / `BREAKDOWN`.
- G2.4 `sensitivity` → PELT penalty mapping (higher sensitivity → lower penalty → more points), documented and monotone; `significance` = normalized magnitude of the regime change, used to surface **top-N**.
- G2.5 **Traceability:** every `Inflection.evidence_bars` names the exact bar dates behind the signal, all within its `window` — this feeds P4 drill-down.
- G2.6 **Determinism:** same bars → byte-identical inflections. No wall-clock, no RNG, no unseeded library state. This is what golden-value tests pin.

**Key decision (recorded here, from [overview §11](../00-overview.md#11-key-trade-offs-system-design-step-24-summary)):** a deterministic algorithm is chosen over an LLM for inflection detection. A reader re-runs the math; they cannot re-run a model's intuition. The trade-off is less "semantic" nuance in labeling, bought back by a transparent, testable slope classifier whose parameters live in `detector`.

**Non-goals:** aligning inflections to events (P3), any rendering (P4), fetching bars (P1). No LLM anywhere in this phase.

---

## Plan — how

1. **Prepare the signal.** From `series.bars` (ascending), build the close vector and the **log-return** vector `r_t = ln(close_t / close_{t-1})`. Detection runs on log-returns (scale-free, stationary-ish); classification reads the raw close/slope. Guard length: series shorter than `MIN_BARS` (e.g. 5) → return `[]` (graceful, no raise) per [conventions §6](../01-conventions.md#6-error-handling--degradation).
2. **Change-point detection.** `ruptures.Pelt(model="rbf").fit(signal).predict(pen=penalty)`. PELT is exact + O(n) here and, crucially, **deterministic** — no random init. Each returned index is a regime boundary → a candidate inflection bar.
3. **Sensitivity → penalty.** Map `penalty = BASE_PEN / sensitivity` (higher sensitivity ⇒ smaller penalty ⇒ more change points), monotone by construction. Record the resolved value in `detector`, e.g. `"pelt:rbf:pen=8"`, so the exact run is reproducible from the field alone.
4. **Classify each change point** by comparing the mean slope of the window **before** vs **after** the boundary (fit on close):
   - trough (neg→pos slope) → `TURNING_UP`; peak (pos→neg) → `TURNING_DOWN`.
   - same sign but |slope| increases materially → `ACCELERATE`.
   - single-bar return jump beyond a gap threshold (e.g. |r_t| > k·σ) → `BREAKOUT_UP` (up) / `BREAKDOWN` (down); the gap rule takes precedence over the slope rule.
   Thresholds are constants recorded in `detector`.
5. **Significance = normalized magnitude.** Raw magnitude = |Δ mean-return across the boundary| (with a gap bonus for breakout/breakdown). Normalize across all candidates to 0..1 (`raw / max_raw`) so ranking is comparable within a run. Populate `Inflection.significance`.
6. **evidence_bars + window.** `window = (start_date, end_date)` of the pre/post segments the classifier used; `evidence_bars` = the concrete bar dates within that window that produced the signal (segment endpoints + the trigger bar). Always non-empty, always ⊆ window — this is the P4 traceability link.
7. **Rank & truncate.** Sort by `significance` desc (tie-break: date asc, for stable golden output); return the first `top_n`.
8. **Purity & determinism.** No `datetime.now()`, no unseeded state; sorting fully specified so ties are deterministic. Function depends only on `(series, top_n, sensitivity)`.

**Files produced:** `agent/tools/detect_inflections.py` (implementation + the classifier + constants), `tests/test_detect_inflections.py`, and a small committed synthetic fixture under `tests/fixtures/` with hand-labeled peaks/troughs for golden assertions.

---

## Test — how we know it's done

This phase carries the **highest-coverage** tests in the repo — the deterministic core underwrites the
reproducibility NFR ([overview §3](../00-overview.md#3-non-functional-requirements-system-design-step-2)).

| ID | Type | Assertion |
|----|------|-----------|
| T2.1 | Unit (golden) | On a hand-crafted synthetic series with known peaks/troughs, the returned inflections match **exact** expected `date`s **and** `kind`s. |
| T2.2 | Unit | **Determinism:** two calls with identical args return byte-identical lists (dates, kinds, significance, evidence_bars). |
| T2.3 | Unit | A strictly monotonic ramp yields **no** `TURNING_UP`/`TURNING_DOWN` (no false turning points). |
| T2.4 | Unit | A sharp single-bar gap-up is classified `BREAKOUT_UP` (and a gap-down `BREAKDOWN`), gap rule beating the slope rule. |
| T2.5 | Unit | **Ranking/top-N:** results are sorted by `significance` desc; `len(result) <= top_n`; lowering `top_n` returns a prefix of the larger run. |
| T2.6 | Unit | **Sensitivity monotonicity:** higher `sensitivity` yields ≥ as many detected points as lower (count non-decreasing). |
| T2.7 | Contract | **Traceability:** every `Inflection.evidence_bars` is non-empty and every date lies within `[window[0], window[1]]`; `detector` string encodes the resolved penalty/params. |
| T2.8 | Unit | Empty series and a too-short series (`< MIN_BARS`) return `[]` gracefully — no exception, no crash. |
| T2.9 | Contract | Every returned `Inflection` satisfies the schema: `kind ∈ InflectionKind`, `0.0 <= significance <= 1.0`, `price` equals the close of `date`. |

**Exit criteria:** all of T2.1–T2.9 green; `detect_inflections` matches the [conventions §3](../01-conventions.md#3-tool-signature-contracts-deterministic-no-llm-inside) signature; golden fixture committed; `ruff` + `mypy --strict` clean on `agent/tools/detect_inflections.py`.

**Risks / mitigations**
- *`ruptures` version drift changes segmentation* → pin the version in `pyproject.toml`; golden test T2.1 catches any silent change; `detector` records the exact params so a re-run is reproducible.
- *Penalty tuning over-/under-detects on real data* → `sensitivity` knob + top-N truncation give the orchestrator control without touching code; monotonicity pinned by T2.6.
- *Classifier mislabels near ambiguous boundaries* → gap-rule precedence and explicit constants (in `detector`) keep labeling transparent and re-checkable, not a black box.
