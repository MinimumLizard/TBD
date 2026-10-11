"""Every setting comes from an environment variable; nothing secret is ever written in code or config files.

The full list, with no values, is in `.env.example`. Locally, copy it to `.env` (gitignored) and fill it in.
In GitHub Actions the values come from repository secrets; on Vercel from its environment settings.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_dotenv(path: Path) -> None:
    """Minimal .env reader (KEY=value lines), so local runs need no extra tooling. Real env vars win."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass(frozen=True)
class Settings:
    database_url: str | None
    raw_store: str                     # "local:<path>" or "s3"
    s3_endpoint_url: str | None        # Cloudflare R2: https://<account>.r2.cloudflarestorage.com
    s3_bucket: str | None
    s3_access_key_id: str | None
    s3_secret_access_key: str | None
    healthchecks_base_url: str | None  # e.g. https://hc-ping.com/<project ping key>
    environment: str                   # local | staging | production
    secondary_store: str | None        # second copy of the archive: "local:<path>" or "s3" (Backblaze B2)
    secondary_s3_endpoint_url: str | None
    secondary_s3_bucket: str | None
    secondary_s3_access_key_id: str | None
    secondary_s3_secret_access_key: str | None


def load(dotenv: Path | None = None) -> Settings:
    _load_dotenv(dotenv or REPO_ROOT / ".env")
    env = os.environ.get
    return Settings(
        database_url=env("DATABASE_URL"),
        raw_store=env("RAW_STORE", f"local:{REPO_ROOT / '.local' / 'raw'}"),
        s3_endpoint_url=env("S3_ENDPOINT_URL"),
        s3_bucket=env("S3_BUCKET"),
        s3_access_key_id=env("S3_ACCESS_KEY_ID"),
        s3_secret_access_key=env("S3_SECRET_ACCESS_KEY"),
        healthchecks_base_url=env("HEALTHCHECKS_BASE_URL"),
        environment=env("APP_ENV", "local"),
        secondary_store=env("SECONDARY_STORE"),
        secondary_s3_endpoint_url=env("SECONDARY_S3_ENDPOINT_URL"),
        secondary_s3_bucket=env("SECONDARY_S3_BUCKET"),
        secondary_s3_access_key_id=env("SECONDARY_S3_ACCESS_KEY_ID"),
        secondary_s3_secret_access_key=env("SECONDARY_S3_SECRET_ACCESS_KEY"),
    )
