"""Copy lint: fail the build on banned phrases in user-facing text (decision 0010).

    python -m data_platform.compliance        # exit 1 and list every hit

User-facing text is defined by USER_FACING below. It grows as the product does: the web app's message files, every
model's manifest and METHOD page, the models' own code (their labels end up on the page) and the web app's code are
scanned automatically once they exist. Tests are not scanned: they may need to name a banned phrase to test it.
"""
from __future__ import annotations

import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import yaml

from .core.settings import REPO_ROOT

RULES = REPO_ROOT / "compliance" / "banned_phrases.yaml"
USER_FACING = [
    "web/messages/*.json",
    "data_platform/models/*/manifest.yaml",
    "data_platform/models/*/METHOD.md",
    "compliance/disclaimers.yaml",
    # Code that produces or presents model outputs (hard rule 4 covers code and output labels, not only copy):
    "data_platform/models/*.py",
    "data_platform/models/*/*.py",
    "web/app/**/*.ts",
    "web/app/**/*.tsx",
    "web/lib/**/*.ts",
    "web/components/**/*.tsx",
]


@dataclass(frozen=True)
class Hit:
    file: str
    line_no: int
    phrase: str
    line: str


def load_rules(path: Path = RULES) -> tuple[list[str], list[dict]]:
    raw = yaml.safe_load(path.read_text())
    return [p.lower() for p in raw["banned"]], raw.get("allow") or []


ZERO_WIDTH = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u2060\ufeff\u00ad"))


def normalise(text: str) -> str:
    """Fold look-alike characters (full-width letters, ligatures) to plain ones and drop invisible ones, so a banned
    word cannot be disguised. Case is folded too."""
    return unicodedata.normalize("NFKC", text).translate(ZERO_WIDTH).casefold()


def _pattern(phrase: str) -> re.Pattern:
    # Whole words: a letter, digit or underscore on either side means it is part of a longer word or identifier.
    # A hyphen does NOT protect a word ("buy-and-hold" is caught). Words in a phrase may be split by any whitespace,
    # including a line break, or by hyphens ("top-pick").
    words = [re.escape(w) for w in phrase.split()]
    return re.compile(r"(?<!\w)" + r"[\s-]+".join(words) + r"(?!\w)")


def scan_text(rel: str, text: str, banned: list[str], allow: list[dict]) -> list[Hit]:
    hits = []
    lines = text.splitlines()
    folded = normalise(text)
    starts = [m.start() for m in re.finditer(r"^", folded, re.M)]
    folded_lines = folded.splitlines()
    for phrase in banned:
        for m in _pattern(normalise(phrase)).finditer(folded):
            n = max(i for i, s in enumerate(starts) if s <= m.start()) + 1
            context = " ".join(folded_lines[n - 1:n + 1]) if "\n" in m.group(0) else folded_lines[n - 1]
            allowed = any(a["file"] == rel and normalise(a["phrase"]) == normalise(phrase)
                          and normalise(a["context"]) in context for a in allow)
            if not allowed:
                hits.append(Hit(rel, n, phrase, lines[n - 1].strip()[:160] if n - 1 < len(lines) else ""))
    return hits


def scan(root: Path = REPO_ROOT, patterns: list[str] = USER_FACING, rules: Path = RULES) -> list[Hit]:
    banned, allow = load_rules(rules)
    hits = []
    for pattern in patterns:
        for path in sorted(root.glob(pattern)):
            hits += scan_text(str(path.relative_to(root)), path.read_text(), banned, allow)
    return hits


def main() -> int:
    hits = scan()
    for h in hits:
        print(f"{h.file}:{h.line_no}: banned phrase {h.phrase!r}: {h.line}")
    print(f"copy lint: {len(hits)} banned phrase(s) in user-facing text")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
