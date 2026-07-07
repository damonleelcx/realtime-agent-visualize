# P1 · Data Layer (Tools)

> **Timeline:** 1–1.5 h · **Depends on:** [P0](./P0-scaffolding.md) · **Blocks:** [P2](./P2-analysis-inflection.md), [P3](./P3-event-curation.md)
> **Anchors:** [00-overview](../00-overview.md) · [01-conventions](../01-conventions.md)

---

## Spec — what & why

Implement the two **deterministic data tools** — `market_data` and `news_fetch` — that feed every later
phase. These are the backbone of traceability ([overview §5](../00-overview.md#5-architecture-system-design-steps-45-mapped-to-the-harness-model)):
each **has no LLM inside**, is pure w.r.t. its args + cache, and stamps a clickable `Provenance` on
**every** record at fetch time. This phase is done when both tools return schema-valid,
provenance-complete records from a fixture cache, fall back cleanly when a primary source fails, and
never touch the live network in tests.

**Goals**
- G1.1 `market_data(ticker, start, end) -> PriceSeries` per [conventions §3](../01-conventions.md#3-tool-signature-contracts-deterministic-no-llm-inside): **yfinance** primary, **Stooq CSV** fallback (both keyless — satisfies the no-secret constraint by construction, [overview §7](../00-overview.md#7-data-sources--2-categories-market--news)). Each `Bar` carries a `Provenance` (`source`, clickable `source_url`, `fetched_at`, `query`).
- G1.2 `news_fetch(query, start, end, limit) -> list[NewsItem]` per [conventions §3](../01-conventions.md#3-tool-signature-contracts-deterministic-no-llm-inside): **Hacker News Algolia** (`hn.algolia.com`) primary, **Yahoo Finance RSS** fallback, **curated seed file** as last resort. Each `NewsItem.url` is mirrored into `prov.source_url`.
- G1.3 On-disk cache per [conventions §5](../01-conventions.md#5-caching--determinism): key = `sha256(source + "|" + args)` under `.cache/`; `--no-cache` / `--refresh` bypass; a committed **fixture cache** backs all tests (no live network).
- G1.4 Error handling & degradation per [conventions §6](../01-conventions.md#6-error-handling--degradation): typed `DataSourceError` / `EmptyResultError`; primary→fallback records the *actual* source in `Provenance.source`; **never fabricate data** to fill a gap.
- G1.5 **Provenance completeness is the point of this phase** — every `Bar` and `NewsItem` has a non-empty, clickable `source_url` (**P-INV-1**, [conventions §7](../01-conventions.md#7-test-strategy-applies-to-every-phase)).

**Non-goals:** inflection math (P2), event curation / rating (P3), any rendering (P4). Tools decide **no policy** (how many events, which rating) — that is subagent judgement ([conventions §3](../01-conventions.md#3-tool-signature-contracts-deterministic-no-llm-inside)).

**Key decision:** keyless sources are the *default* path so the no-secrets requirement ([overview §8](../00-overview.md#8-security-model-system-design-step-20--prompts-explicit-asks)) holds by construction. `source_url` is chosen at fetch time as the *most specific* URL that reproduces the datum (per-article where available, else the query/landing URL) so it is always human-clickable.

---

## Plan — how

1. **`agent/tools/market_data.py`.** `market_data(ticker, start, end)`: try yfinance daily bars → `list[Bar]`; on `DataSourceError` or empty frame, fall back to the Stooq CSV endpoint (`stooq.com/q/d/l/?s=<ticker>&d1=&d2=&i=d`). Parse OHLCV rows, coerce types, sort ascending by date. Stamp each `Bar` with `Provenance(source=..., source_url=<Yahoo chart or Stooq query URL>, fetched_at=<clock>, query="<ticker>|<start>|<end>")`; stamp the `PriceSeries.prov` with the series-level fetch.
2. **`agent/tools/news_fetch.py`.** `news_fetch(query, start, end, limit=200)`: query HN Algolia `search_by_date` with `numericFilters` on `created_at_i` → `list[NewsItem]`; on failure fall back to Yahoo Finance RSS, then to a committed `agent/tools/data/news_seed.json`. Each item's article URL becomes both `NewsItem.url` **and** `prov.source_url` (HN → the story URL, or the HN item permalink when the story has no URL).
3. **Date-range filtering.** Both tools filter to `[start, end]` inclusive *after* parse, so a fallback source with a coarser query still yields a correctly bounded result.
4. **Cache wiring.** Route both tools through `agent/cache.py` (from P0): compute `sha256(source|args)`, read-through on hit, write-through on miss. Honor `--no-cache` / `--refresh` (bypass read; still write). Fixture cache lives under `tests/fixtures/cache/`.
5. **Typed errors & fallback ladder.** Wrap each source call; raise `DataSourceError` on transport/parse failure and `EmptyResultError` when a source returns zero in-range rows. The ladder catches these and steps to the next source; only an exhausted ladder propagates. News exhaustion returns `[]` (graceful — [conventions §6](../01-conventions.md#6-error-handling--degradation)); market exhaustion raises (a K-line needs bars).
6. **Frozen clock.** `fetched_at` reads an injectable clock (default `utcnow`) so golden fixtures compare stably ([conventions §5](../01-conventions.md#5-caching--determinism)).
7. **Fixtures.** Commit one golden yfinance OHLCV response, one Stooq CSV, one HN Algolia JSON, and `news_seed.json`, plus the derived fixture cache, so every test is offline and deterministic.

**Files produced:** `agent/tools/market_data.py`, `agent/tools/news_fetch.py`, `agent/tools/errors.py` (`DataSourceError`, `EmptyResultError`), `agent/tools/data/news_seed.json`, `tests/fixtures/{yfinance_nvda.json,stooq_nvda.csv,hn_algolia.json}`, `tests/fixtures/cache/`, `tests/test_market_data.py`, `tests/test_news_fetch.py`.

---

## Test — how we know it's done

| ID | Type | Assertion |
|----|------|-----------|
| T1.1 | Unit | Golden-value parse: feeding the committed `yfinance_nvda.json` fixture yields a `PriceSeries` whose first/last `Bar` OHLCV + dates equal known golden values; bars are ascending. |
| T1.2 | Unit | Fallback path: with yfinance mocked to raise `DataSourceError`, `market_data` transparently returns Stooq-sourced bars and stamps `prov.source == "stooq"`. |
| T1.3 | Unit | News fallback ladder: HN mocked to raise → RSS mocked empty (`EmptyResultError`) → seed file used; `prov.source == "seed"` and items are non-empty. |
| T1.4 | Contract | **P-INV-1** provenance completeness: every `Bar` and every `NewsItem` has non-empty `source_url`, `source`, and `fetched_at`. |
| T1.5 | Contract | Citation URL validity: every stamped `source_url` (and `NewsItem.url`) is a syntactically valid `http(s)://` URL and equals `prov.source_url` for news items. |
| T1.6 | Unit | Cache hit avoids network: second call with identical args serves from cache — the network mock is asserted **not called** on the 2nd invocation; `--refresh` re-invokes it. |
| T1.7 | Unit | Date-range filtering: bars/items outside `[start, end]` are excluded; boundary dates are inclusive. |
| T1.8 | Unit | Empty-result handling: a source returning zero in-range rows raises `EmptyResultError`; an exhausted news ladder returns `[]` (graceful), an exhausted market ladder raises `DataSourceError`. |
| T1.9 | Security | **P-INV-4** no-secret: tool source + committed fixtures/seed contain no key-shaped string (`grep` gate); all sources are keyless. |

**Exit criteria:** all of T1.1–T1.9 green; both tools return schema-valid, provenance-complete records from the fixture cache with **no live network**; fallback ladders exercised; `ruff` + `mypy agent` clean.

**Risks / mitigations**
- *Upstream schema drift (yfinance/HN JSON shape changes)* → parse behind a thin adapter + golden fixtures; a real break surfaces as a fixture-refresh PR, not silent bad data.
- *A source lacks a per-item URL* → fall back to the most specific query/landing URL (never empty) so **P-INV-1** always holds.
- *Live-network flakiness leaking into CI* → tests bind to the fixture cache and mock all transports; a live call in a test is itself a failure.
- *Fallback masks a real outage* → `Provenance.source` records the *actual* source used, so degraded runs are visible downstream, not hidden.
