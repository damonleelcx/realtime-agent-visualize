"""Live dashboard server (docs/phases/P6).

A thin FastAPI app that runs the real Harness and **streams its
Plan→Act→Observe→Validate→Retry events over SSE** while the pipeline executes,
then serves the produced interactive HTML inline plus the Office files as
downloads. The heavy lifting is unchanged — this only wires the orchestrator's
`on_event` hook to a browser.

- Same-origin only; the produced HTML stays self-contained (no CORS/CDN).
- With `ANTHROPIC_API_KEY` set it runs full LLM curation; without a key it falls
  back to a `NullLLM` so the K-line + inflections still render (graceful).
"""

from __future__ import annotations

import asyncio
import json
import os
import queue
import threading
import uuid
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from ..backend import default_client
from ..orchestrator import TerminationError, ValidationError, _default_range, run

HERE = Path(__file__).parent
RUNS = Path("artifacts/web")


class NullLLM:
    """No-key fallback: proposes nothing, so the run degrades to K-line only."""

    def complete(self, system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]:
        return {"events": [], "alignments": []}


def _load_dotenv() -> None:
    """Best-effort: populate ANTHROPIC_API_KEY from .env if not already set."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        return
    env = Path(".env")
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


def create_app() -> FastAPI:
    _load_dotenv()
    RUNS.mkdir(parents=True, exist_ok=True)
    app = FastAPI(title="realtime-agent-visualize")
    app.mount("/runs", StaticFiles(directory=str(RUNS)), name="runs")

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return (HERE / "index.html").read_text(encoding="utf-8")

    @app.get("/api/run")
    def api_run(
        ticker: str = "NVDA",
        start: str = "",
        end: str = "",
        outputs: str = "html,xlsx,pptx,docx",
    ) -> StreamingResponse:
        run_id = uuid.uuid4().hex[:12]
        out_dir = RUNS / run_id
        s, e = _default_range(start, end)
        have_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
        client: Any = default_client() if have_key else NullLLM()
        q: queue.Queue[Any] = queue.Queue()

        def worker() -> None:
            q.put({"type": "mode", "llm": have_key, "ticker": ticker, "range": [s, e]})
            try:
                rr = run(
                    ticker or "NVDA", s, e,
                    [o.strip() for o in outputs.split(",") if o.strip()],
                    client=client, out_dir=str(out_dir), on_event=q.put,
                )
                items = [
                    {"name": Path(p).name, "url": f"/runs/{run_id}/{Path(p).name}"}
                    for p in rr.artifacts
                ]
                html = next((it["url"] for it in items if it["name"].endswith(".html")), None)
                q.put({"type": "artifacts", "items": items, "html": html})
                q.put({"type": "done"})
            except (TerminationError, ValidationError) as exc:
                q.put({"type": "error", "message": str(exc)})
            except Exception as exc:  # noqa: BLE001 — surface any failure to the UI
                q.put({"type": "error", "message": f"{type(exc).__name__}: {exc}"})
            finally:
                q.put(None)

        threading.Thread(target=worker, daemon=True).start()

        async def gen() -> AsyncGenerator[str, None]:
            loop = asyncio.get_event_loop()
            while True:
                item = await loop.run_in_executor(None, q.get)
                if item is None:
                    break
                yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"

        return StreamingResponse(gen(), media_type="text/event-stream")

    return app


app = create_app()


def main() -> None:
    import uvicorn  # noqa: PLC0415

    port = int(os.environ.get("PORT", "8000"))
    print(f"\n  realtime-agent-visualize dashboard → http://127.0.0.1:{port}\n")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
