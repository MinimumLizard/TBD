"""Repository-wide rules, checked on every change: compliance copy lint, no data in git, no secrets in git."""
from __future__ import annotations

import re
import subprocess

from data_platform import compliance
from data_platform.core.settings import REPO_ROOT

# --- copy lint ------------------------------------------------------------------------------------------------------

def test_user_facing_text_has_no_banned_phrases():
    hits = compliance.scan()
    assert not hits, "\n".join(f"{h.file}:{h.line_no}: {h.phrase!r}: {h.line}" for h in hits)


def test_copy_lint_catches_advice_and_allows_only_listed_context():
    banned, _ = compliance.load_rules()
    allow = [{"file": "x.json", "phrase": "bought", "context": "directors bought", "reason": "fact"}]
    assert compliance.scan_text("x.json", '"label": "Buy the cheap, sell the rich"', banned, allow)
    assert compliance.scan_text("x.json", "Switch candidates", banned, allow)
    assert compliance.scan_text("x.json", "We recommend this bond", banned, allow)
    assert not compliance.scan_text("x.json", "Yield above the fitted curve by 7 bp", banned, allow)
    assert not compliance.scan_text("x.json", "Household income", banned, allow)       # whole words only
    assert compliance.scan_text("y.json", "hold", banned, allow)                          # allow is per file


# --- no data and no secrets in git (the repo is public for now: decision 0012) -------------------------------------

def tracked_files() -> list[str]:
    out = subprocess.run(["git", "-C", str(REPO_ROOT), "ls-files"], capture_output=True, text=True, check=True)
    return out.stdout.splitlines()


DATA_SUFFIXES = (".sqlite", ".db", ".parquet", ".bundle", ".dump", ".tar", ".xz", ".zip")
FIXTURE_DIR = "tests/fixtures/"


def test_no_data_files_in_git():
    bad = [f for f in tracked_files() if f.endswith(DATA_SUFFIXES)]
    assert not bad, f"data files must not be committed (decision 0003/0012): {bad}"


def test_no_large_files_outside_fixtures():
    big = []
    for f in tracked_files():
        p = REPO_ROOT / f
        limit = 2_000_000 if f.startswith(FIXTURE_DIR) else 500_000
        if p.exists() and p.stat().st_size > limit and f != "uv.lock":
            big.append((f, p.stat().st_size))
    assert not big, f"unexpectedly large tracked files: {big}"


SECRET_PATTERNS = [
    re.compile(r"AKIA[0-9A-Z]{16}"),                                     # AWS access key id
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9\.[A-Za-z0-9_-]{20,}"),   # a JWT, e.g. a Supabase key
    re.compile(r"postgres(?:ql)?://[^:\s/]+:[^@\s]{6,}@"),               # a database URL with a password
    re.compile(r"(?i)(secret|token|api[_-]?key|password)\s*[:=]\s*['\"][A-Za-z0-9/+_\-]{20,}['\"]"),
]


def test_no_secrets_in_git():
    hits = []
    for f in tracked_files():
        p = REPO_ROOT / f
        if not p.exists() or f.startswith(FIXTURE_DIR) or p.stat().st_size > 2_000_000:
            continue
        try:
            text = p.read_text()
        except UnicodeDecodeError:
            continue
        for pat in SECRET_PATTERNS:
            if pat.search(text):
                hits.append((f, pat.pattern[:30]))
    assert not hits, f"possible secrets committed: {hits}"


def test_env_example_lists_every_setting():
    example = (REPO_ROOT / ".env.example").read_text()
    settings_src = (REPO_ROOT / "data_platform" / "core" / "settings.py").read_text()
    for var in re.findall(r'env\("([A-Z_]+)"', settings_src):
        assert re.search(rf"^{var}=", example, re.M), f"{var} is read in settings.py but missing from .env.example"
