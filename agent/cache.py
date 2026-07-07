"""On-disk keyed cache (docs/01-conventions.md §5).

Key = sha256(source | args). Value = JSON. Tools use this so re-runs and
tests avoid the network. P0 ships the read/write mechanism only; the data
tools (P1) build their keys on top of it.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

DEFAULT_CACHE_DIR = Path(".cache")


def cache_key(source: str, *args: Any) -> str:
    """Stable key for (source, args). Args are stringified deterministically."""
    payload = source + "|" + "|".join(json.dumps(a, sort_keys=True, default=str) for a in args)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class JsonCache:
    def __init__(self, cache_dir: Path | str = DEFAULT_CACHE_DIR) -> None:
        self.dir = Path(cache_dir)

    def _path(self, key: str) -> Path:
        return self.dir / f"{key}.json"

    def get(self, key: str) -> Any | None:
        p = self._path(key)
        if not p.exists():
            return None
        return json.loads(p.read_text(encoding="utf-8"))

    def set(self, key: str, value: Any) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        self._path(key).write_text(
            json.dumps(value, ensure_ascii=False), encoding="utf-8"
        )

    def has(self, key: str) -> bool:
        return self._path(key).exists()
