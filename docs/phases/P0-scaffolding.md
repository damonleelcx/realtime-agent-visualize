# P0 · Scaffolding & SDK Selection

> **Timeline:** 0.5–1 h · **Depends on:** — · **Blocks:** all phases
> **Anchors:** [00-overview](../00-overview.md) · [01-conventions](../01-conventions.md)

---

## Spec — what & why

Stand up the skeleton every later phase drops into, and lock the decisions that are expensive to
change later: the SDK, the module boundaries, the shared data contract, and the secret-isolation
posture. **No feature logic** here — this phase is done when an empty end-to-end skeleton imports,
runs, and prints a plan without doing real work.

**Goals**
- G0.1 Repo structure per [overview §9](../00-overview.md#9-repository-layout-target) exists and imports cleanly.
- G0.2 `agent/models.py` holds the frozen dataclasses from [conventions §2](../01-conventions.md#2-core-data-records-passed-between-layers) — the shared contract every phase codes against.
- G0.3 Claude Agent SDK chosen and wired as a dependency; a stub `run_analysis()` façade + `python -m agent.run "<task>"` CLI exist and return a well-formed empty `AnalysisResult`.
- G0.4 Secret isolation in place: `.gitignore` excludes `.env`, caches, `artifacts/`; only `.env.example` committed.
- G0.5 Tooling: `pyproject.toml`, `ruff`, `mypy`, `pytest` runnable; CI config drafted.

**Non-goals:** any real fetch, math, LLM call, or rendering (those are P1–P4).

**Key decision (recorded here, detailed in [overview §6](../00-overview.md#6-agent-sdk-selection)):** Claude Agent SDK (Python), because tools/subagents/skills are first-class primitives — the exact axis being graded — and Python owns the data/reporting library ecosystem. A bare-API fallback behind the same `run_analysis()` façade is kept viable so the architecture survives a backend swap.

---

## Plan — how

1. **Init project metadata.** `pyproject.toml` (name, py≥3.11, deps: `claude-agent-sdk` or fallback `anthropic`, `pandas`, `yfinance`, `ruptures`, `openpyxl`, `python-pptx`, `python-docx`, `pytest`, `ruff`, `mypy`). Entry point `agent.run:main`.
2. **Create package tree** exactly as overview §9: `agent/{tools,subagents,skills}/`, `docs/`, `artifacts/`, `samples/`, `tests/`. Add `__init__.py`s.
3. **Write `agent/models.py`** — paste the dataclasses from conventions §2 verbatim (the load-bearing contract). This is the one substantive artifact of P0.
4. **Write `agent/cache.py`** stub — `get(key)/set(key,val)` over `.cache/`, key = `sha256(source|args)` per conventions §5. No logic beyond read/write JSON.
5. **Write `agent/orchestrator.py`** stub — a `plan(task) -> list[str]` returning a hard-coded checklist, and `run(task) -> AnalysisResult` returning an empty result. No tools called yet.
6. **Write `agent/run.py`** — argparse CLI: `python -m agent.run "<task>"` → calls orchestrator, prints the plan + a JSON summary of the (empty) result.
7. **Secret posture.** `.gitignore` (`.env`, `.cache/`, `artifacts/`, `__pycache__/`, `*.pyc`); `.env.example` documenting the keyless default and any optional keys.
8. **CI draft.** `.github/workflows/ci.yml` (or a `Makefile` target): `ruff check`, `mypy agent`, `pytest`.
9. **README skeleton** — one-command run section + placeholder for the AI-development log (filled in P5).

**Files produced:** `pyproject.toml`, `.gitignore`, `.env.example`, `agent/{__init__,run,orchestrator,cache,models}.py`, `agent/{tools,subagents,skills}/__init__.py`, `README.md` (skeleton), CI config.

---

## Test — how we know it's done

| ID | Type | Assertion |
|----|------|-----------|
| T0.1 | Unit | `import agent.models` succeeds; each dataclass is `frozen` and instantiable with sample args. |
| T0.2 | Contract | A hand-built `AnalysisResult` round-trips through a serialize→deserialize helper without loss (guards the shared contract early). |
| T0.3 | Integration | `python -m agent.run "test"` exits 0 and prints a plan + empty-but-well-formed `AnalysisResult` JSON. |
| T0.4 | Security | Repo contains **no** `.env`; `git check-ignore .env` returns true; `.env.example` exists and contains no real secret (**P-INV-4**). |
| T0.5 | Tooling | `ruff check` and `mypy agent` pass on the skeleton; `pytest` collects and runs (green). |

**Exit criteria:** all of T0.1–T0.5 green; the package tree matches overview §9; SDK dependency resolves (or the fallback path is wired and documented).

**Risks / mitigations**
- *SDK unavailable in grader env* → façade + bare-API fallback (documented in [P5](./P5-orchestration-testing.md)); nothing above the façade knows which backend runs.
- *Contract churn later* → keep `models.py` the single source; any change is one PR touching this file + conventions §2.
