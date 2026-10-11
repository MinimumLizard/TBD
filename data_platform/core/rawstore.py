"""Layer 1, the raw archive: every fetched payload saved untouched, named by its SHA-256 fingerprint.

Two implementations with the same behaviour:
    LocalRawStore  a folder on disk (development, tests, and the founders' own copies)
    S3RawStore     any S3-compatible bucket: Cloudflare R2 in production, Backblaze B2 for the second copy

Rules both enforce:
  * Content-addressed: the storage key is derived from the bytes, raw/<aa>/<sha256>.<ext>. The same content is
    stored once however many times it is fetched, and different content can never land on an existing key.
  * Write-once: an existing object is never rewritten. On R2 a bucket-lock rule enforces this as well
    (decision 0003); here the code simply never overwrites.
  * Verified reads: get() re-hashes what it returns and raises if the bytes don't match their name.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class IntegrityError(RuntimeError):
    """Stored bytes no longer match their fingerprint. Never ignore this."""


@dataclass(frozen=True)
class StoredObject:
    sha256: str
    bytes: int
    ext: str
    key: str


def sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sniff_ext(data: bytes, content_type: str | None = None) -> str:
    """Name a file by what it is, not by what its link claims (the PDMO's "PDF" links often serve .xls)."""
    head = data[:8]
    if head.startswith(b"%PDF"):
        return "pdf"
    if head.startswith(b"\xd0\xcf\x11\xe0"):
        return "xls"
    if head.startswith(b"PK\x03\x04"):
        return "zip"
    if head.startswith(b"PAR1"):
        return "parquet"
    if head.startswith(b"SQLite f"):
        return "sqlite"
    ctype = (content_type or "").lower()
    stripped = data.lstrip()[:1]
    if "json" in ctype or stripped in (b"{", b"["):
        return "json"
    if "html" in ctype or stripped == b"<":
        return "html"
    if "csv" in ctype:
        return "csv"
    if ctype.startswith("text/"):
        return "txt"
    return "bin"


def key_for(sha256: str, ext: str) -> str:
    return f"raw/{sha256[:2]}/{sha256}.{ext}"


class RawStore(Protocol):
    def put(self, data: bytes, ext: str) -> StoredObject: ...
    def get(self, sha256: str, ext: str) -> bytes: ...
    def exists(self, sha256: str, ext: str) -> bool: ...


class LocalRawStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)

    def _path(self, sha256: str, ext: str) -> Path:
        return self.root / key_for(sha256, ext)

    def put(self, data: bytes, ext: str) -> StoredObject:
        digest = sha256_of(data)
        path = self._path(digest, ext)
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(path.name + f".{os.getpid()}.part")
            tmp.write_bytes(data)
            os.replace(tmp, path)        # atomic: a crash never leaves a half-written object under its real name
        return StoredObject(digest, len(data), ext, key_for(digest, ext))

    def get(self, sha256: str, ext: str) -> bytes:
        data = self._path(sha256, ext).read_bytes()
        if sha256_of(data) != sha256:
            raise IntegrityError(f"{key_for(sha256, ext)}: stored bytes do not match their fingerprint")
        return data

    def exists(self, sha256: str, ext: str) -> bool:
        return self._path(sha256, ext).exists()


class S3RawStore:
    """Cloudflare R2 / Backblaze B2 / AWS S3 through the standard S3 API (boto3)."""

    def __init__(self, bucket: str, client):
        self.bucket = bucket
        self.client = client

    @classmethod
    def from_settings(cls, settings) -> "S3RawStore":
        import boto3

        client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key_id,
            aws_secret_access_key=settings.s3_secret_access_key,
            region_name="auto",
        )
        return cls(settings.s3_bucket, client)

    def exists(self, sha256: str, ext: str) -> bool:
        from botocore.exceptions import ClientError

        try:
            self.client.head_object(Bucket=self.bucket, Key=key_for(sha256, ext))
            return True
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
                return False
            raise

    def put(self, data: bytes, ext: str) -> StoredObject:
        digest = sha256_of(data)
        key = key_for(digest, ext)
        if not self.exists(digest, ext):
            self.client.put_object(Bucket=self.bucket, Key=key, Body=data, Metadata={"sha256": digest})
        return StoredObject(digest, len(data), ext, key)

    def get(self, sha256: str, ext: str) -> bytes:
        data = self.client.get_object(Bucket=self.bucket, Key=key_for(sha256, ext))["Body"].read()
        if sha256_of(data) != sha256:
            raise IntegrityError(f"{key_for(sha256, ext)}: stored bytes do not match their fingerprint")
        return data


def from_settings(settings) -> RawStore:
    if settings.raw_store.startswith("local:"):
        return LocalRawStore(settings.raw_store.removeprefix("local:"))
    if settings.raw_store == "s3":
        return S3RawStore.from_settings(settings)
    raise ValueError(f"RAW_STORE must be 'local:<path>' or 's3', got {settings.raw_store!r}")
