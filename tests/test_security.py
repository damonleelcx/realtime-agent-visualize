"""P0 test T0.4 (P-INV-4 posture): secrets are isolated, none committed."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Key-shaped strings we must never commit (P-INV-4). Matches provider prefixes
# and assigned API-key env lines with a real value.
_SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9]{16,}"),          # OpenAI / Anthropic style
    re.compile(r"AKIA[0-9A-Z]{16}"),             # AWS access key id
    re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),      # Google API key
    re.compile(r"(?i)api[_-]?key\s*[:=]\s*['\"]?[A-Za-z0-9]{16,}"),
]

# Files that legitimately contain the *word* "key" or example placeholders.
_SCAN_ROOTS = [REPO / "agent", REPO / "tests" / "fixtures"]


def test_env_example_exists() -> None:
    assert (REPO / ".env.example").is_file()


def test_dotenv_is_not_tracked_by_git() -> None:
    # A local .env is expected (it holds the user's key); it must never be *tracked*.
    proc = subprocess.run(
        ["git", "ls-files", "--error-unmatch", ".env"],
        cwd=REPO, capture_output=True, text=True,
    )
    assert proc.returncode != 0, ".env must not be tracked by git"


def test_env_is_gitignored() -> None:
    # git check-ignore exits 0 when the path IS ignored.
    proc = subprocess.run(
        ["git", "check-ignore", ".env"], cwd=REPO, capture_output=True, text=True
    )
    assert proc.returncode == 0, ".env must be listed in .gitignore"


def test_env_example_has_no_real_secret() -> None:
    text = (REPO / ".env.example").read_text(encoding="utf-8")
    # Placeholder lines are commented or have empty values — no assigned secret.
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        assert stripped.endswith("="), f"template must not assign a value: {line!r}"


def test_no_secret_shaped_strings_in_tools_and_fixtures() -> None:
    """P-INV-4: tool source, seed data, and fixtures contain no key-shaped string."""
    offenders: list[str] = []
    for root in _SCAN_ROOTS:
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix not in {".py", ".json", ".csv", ".txt"}:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for pat in _SECRET_PATTERNS:
                if pat.search(text):
                    offenders.append(f"{path.relative_to(REPO)} :: {pat.pattern}")
    assert not offenders, f"key-shaped strings found: {offenders}"
