"""The source register, config/sources.yaml: what each source is, whether we may use it, and whether it is on.

The rights rule (decision 0009, the owner's rule): a source is used only if its terms allow commercial use or say
nothing about it. A source marked `prohibited` cannot run, and validate_all() fails CI if one is enabled.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, HttpUrl, model_validator

from .settings import REPO_ROOT

SOURCES_FILE = REPO_ROOT / "config" / "sources.yaml"


class Rights(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["allowed", "silent", "prohibited"]
    evidence: str
    url: HttpUrl
    checked: dt.date
    attribution: str | None = None


class Source(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    homepage: HttpUrl
    enabled: bool
    rights: Rights
    datasets: list[str]
    calendar: str | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def _prohibited_cannot_be_enabled(self):
        if self.enabled and self.rights.status == "prohibited":
            raise ValueError("a source whose terms prohibit commercial use cannot be enabled (decision 0009)")
        return self


class SourceNotRunnable(RuntimeError):
    pass


def load(path: Path = SOURCES_FILE) -> dict[str, Source]:
    raw = yaml.safe_load(path.read_text()) or {}
    return {sid: Source.model_validate(cfg) for sid, cfg in raw.items()}


def require_runnable(source_id: str, path: Path = SOURCES_FILE) -> Source:
    sources = load(path)
    if source_id not in sources:
        raise SourceNotRunnable(f"{source_id!r} is not in {path.name}; add it (with its rights evidence) first")
    src = sources[source_id]
    if not src.enabled:
        raise SourceNotRunnable(f"{source_id} is switched off in {path.name} (enabled: false)")
    return src


def stale_rights_checks(today: dt.date, max_age_days: int = 183, path: Path = SOURCES_FILE) -> list[str]:
    """Sources whose terms were last checked more than ~6 months ago (decision 0009)."""
    return [sid for sid, s in load(path).items()
            if s.enabled and (today - s.rights.checked).days > max_age_days]
