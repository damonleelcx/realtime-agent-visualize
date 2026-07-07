# 01 · Conventions & Shared Contracts

> Shared vocabulary for all phases. If a phase doc and this doc disagree, **this doc wins** —
> update it in the same PR. Defined here: the provenance model, the data records every layer
> passes around, tool signature contracts, error/caching conventions, and the test strategy.

---

## 1. Traceability model (the spine of the whole system)

Every datum and every derived claim carries a **`Provenance`**. This is what makes the
deliverable "可溯源": a marker in the HTML can name the exact source URL and the exact bar it came from.

```python
# agent/models.py  (contract — exact field names are load-bearing; UI + tests depend on them)

@dataclass(frozen=True)
class Provenance:
    source: str          # "yfinance" | "stooq" | "hackernews" | "yahoo_rss" | "seed"
    source_url: str      # canonical URL a human can click to verify (never empty)
    fetched_at: str      # ISO-8601 UTC, e.g. "2025-07-07T05:00:00Z"
    query: str = ""      # the exact query/ticker/range used, for reproducibility
    note: str = ""       # optional: transform applied, page, row id, etc.
```

**Rules**
- `source_url` is **mandatory and clickable**. If a source has no per-item URL, use the most specific landing/query URL that reproduces the datum. Empty `source_url` is a test failure.
- `fetched_at` is set by the fetching **tool**, never guessed downstream.
- Provenance is **immutable** and **propagates**: a derived object references the provenance of every input it depends on (by holding the source objects or their ids), so a rating can be traced back to (a) the bars that formed the inflection and (b) the event's source URL.

---

## 2. Core data records (passed between layers)

```python
@dataclass(frozen=True)
class Bar:                      # one daily OHLCV bar
    date: str                   # "YYYY-MM-DD"
    open: float
    high: float
    low: float
    close: float
    volume: int
    prov: Provenance

@dataclass(frozen=True)
class PriceSeries:
    ticker: str
    bars: list[Bar]             # ascending by date
    prov: Provenance            # provenance of the series-level fetch

@dataclass(frozen=True)
class NewsItem:
    title: str
    url: str                    # the article/source URL (also mirrored in prov.source_url)
    published_at: str           # "YYYY-MM-DD"
    summary: str
    prov: Provenance

class InflectionKind(str, Enum):
    TURNING_UP = "turning_up"       # local trough → reversal upward
    TURNING_DOWN = "turning_down"   # local peak → reversal downward
    ACCELERATE = "accelerate"       # trend slope steepens
    BREAKOUT_UP = "breakout_up"     # sustained up move / gap up
    BREAKDOWN = "breakdown"         # sustained down move / gap down

@dataclass(frozen=True)
class Inflection:
    date: str                   # bar date where it triggers
    kind: InflectionKind
    significance: float         # 0..1 normalized magnitude (for top-N ranking)
    price: float                # close at trigger
    window: tuple[str, str]     # (start_date, end_date) the detector used
    evidence_bars: list[str]    # dates of the bars that produced this signal (traceability)
    detector: str               # algorithm id + params, e.g. "pelt:rbf:pen=8"

class Impact(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

@dataclass(frozen=True)
class CuratedEvent:             # produced by event-curator subagent
    title: str
    date: str
    category: str               # "model_release" | "chip" | "policy" | "earnings" | ...
    impact: Impact
    rationale: str              # WHY this rating — grounded, quotes/paraphrases the source
    news_refs: list[str]        # NewsItem urls backing this event (>=1, mandatory)
    prov: Provenance

@dataclass(frozen=True)
class Alignment:                # produced by signal-analyst subagent
    inflection: Inflection
    events: list[CuratedEvent]  # events within the match window, ranked by plausibility
    lag_days: int               # event_date → inflection_date lag (signed)
    confidence: float           # 0..1 model-assigned link strength
    explanation: str            # human-readable causal note, cites event.news_refs

@dataclass(frozen=True)
class AnalysisResult:           # the single payload every exporter consumes
    ticker: str
    range: tuple[str, str]
    series: PriceSeries
    inflections: list[Inflection]
    events: list[CuratedEvent]
    alignments: list[Alignment]
    generated_at: str
```

> **One payload, many renderers.** HTML / XLSX / PPTX / DOCX are all pure functions of
> `AnalysisResult`. No exporter fetches or re-computes anything — this guarantees the four
> deliverables tell the *same* story from the *same* provenance.

---

## 3. Tool signature contracts (deterministic, no LLM inside)

```python
# tools return provenance-carrying records; they never print prose, never call an LLM.
market_data(ticker: str, start: str, end: str) -> PriceSeries
news_fetch(query: str, start: str, end: str, limit: int = 200) -> list[NewsItem]
detect_inflections(series: PriceSeries, top_n: int = 25, sensitivity: float = 1.0) -> list[Inflection]
artifact_io.write(path: str, data: bytes | str) -> str      # returns abs path
artifact_io.read(path: str) -> bytes
```

- Tools are **pure w.r.t. their args + cache**: same args → same output (network mocked in tests).
- Tools **raise typed errors** (`DataSourceError`, `EmptyResultError`) — they never return `None` silently.
- Tools **never** decide policy (how many events, which rating) — that's subagent judgement.

## 4. Subagent contracts (isolated context, structured output)

Each subagent takes a typed input, returns a **schema-validated** typed output, and is the *only*
place an LLM runs. They receive **data**, never live network access to arbitrary URLs.

```
event_curator(news: list[NewsItem], ticker: str, window) -> list[CuratedEvent]
signal_analyst(inflections: list[Inflection], events: list[CuratedEvent]) -> list[Alignment]
report_builder(result: AnalysisResult, outputs: list[str]) -> list[str]   # artifact paths
```

Boundary rules:
- A subagent's output must be **traceable**: `CuratedEvent.news_refs` and `Alignment.explanation`
  must cite real `NewsItem.url`s that exist in the input. A citation to a non-input URL is a test failure.
- Subagents return **structured objects**, not free text, so the orchestrator can validate them.
- The orchestrator only sees the **returned objects** (a summary), never the subagent's scratch context.

---

## 5. Caching & determinism

- On-disk cache under `.cache/`, key = `sha256(source + "|" + args)`; value = serialized records.
- `--no-cache` / `--refresh` flags bypass. Tests always run with a **fixture cache**, never live network.
- `generated_at` / `fetched_at` are the only wall-clock fields; tests inject a frozen clock so
  golden-file comparisons are stable.

## 6. Error handling & degradation

- Primary source fails → **fall back** to the secondary (yfinance→stooq, HN→RSS→seed) and record
  the actual source in `Provenance.source`. Never fabricate data to fill a gap.
- If news is entirely unavailable, the run still produces the K-line + inflections, with events empty
  and a visible "no events sourced" note — **graceful degradation**, not a hard fail.

---

## 7. Test strategy (applies to every phase)

Three layers; each phase doc lists its own concrete cases against this taxonomy.

| Layer | What | Network | Determinism |
|---|---|---|---|
| **Unit** | one tool / one function (esp. `detect_inflections` math) | mocked / none | strict, golden values |
| **Contract** | records satisfy the schema; provenance non-empty; citations resolve to inputs | none | strict |
| **Integration** | `run_analysis()` end-to-end on a **committed fixture** dataset → artifacts exist | mocked (fixture cache) | golden HTML structure / file presence |

Cross-cutting invariants asserted everywhere:
- **P-INV-1 Provenance completeness:** every `Bar`, `NewsItem`, `CuratedEvent` has non-empty `source_url`.
- **P-INV-2 Citation integrity:** every `CuratedEvent.news_refs` / `Alignment` citation URL exists among fetched `NewsItem`s.
- **P-INV-3 Temporal sanity:** `Alignment.lag_days` within the configured match window; event date ≤ inflection date + window.
- **P-INV-4 No-secret:** no artifact under `artifacts/` or `samples/` contains a key-shaped string (`grep` gate).
- **P-INV-5 Self-contained HTML:** produced HTML has **no** external `http(s)://` `src`/`href` in `<script>`/`<link>` (offline-openable).

Tooling: `pytest`; `ruff` + `mypy` in CI. Coverage focus on the deterministic core (P2) and the invariants above.

---

## 8. Coding conventions

- Python 3.11+, `dataclasses`, full type hints, `mypy --strict` on `agent/`.
- No network in module import paths; all I/O behind tools.
- Every produced HTML string goes through `html.escape` for any interpolated data field.
- Commit messages: `Pn: <what>`; one phase per PR where practical.
- Secrets: read via `os.environ`, documented in `.env.example`, asserted absent from artifacts by tests.
