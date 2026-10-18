"""The contract between the platform and a model plug-in.

A plug-in never connects to the database, the network or the file system. The framework:
  1. gives it an Inputs object that can read only the datasets its manifest declares (and only the pinned version
     of another model's outputs), fingerprinting every row read;
  2. calls compute(inputs, as_of) and receives plain rows, one list per output table the manifest declares;
  3. writes those rows (write_table): new rows are inserted, identical rows are left alone, and a row whose value
     changed, or which disappeared, is first copied to models.revisions. Nothing a model once published is lost.

Floating-point values count as unchanged when they agree to 1e-9 (relative) — the same tolerance the parity tests
use — so a recompute on a different machine does not churn revisions over the last few bits.
"""
from __future__ import annotations

import datetime as dt
import decimal
import hashlib
import importlib
import json
import logging
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import psycopg
import yaml
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

log = logging.getLogger(__name__)

MODELS_DIR = Path(__file__).parent
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
REL_TOL = 1e-9
ABS_TOL = 1e-12


# --- manifest -------------------------------------------------------------------------------------------------

class Parity(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reference: str                       # what the old outputs are, e.g. "Nelson-Siegel@1c33084 curves/fit.py"
    tolerance: float = 1e-9
    notes: str | None = None


class Version(BaseModel):
    model_config = ConfigDict(extra="forbid")
    method_version: str
    # current: what the site shows. reference: kept running beside it for comparison (e.g. the version that
    # reproduces the old tool). retired: no longer computed; its rows stay.
    status: Literal["current", "reference", "retired"]
    requires_models: dict[str, str] = Field(default_factory=dict)   # model name -> its method_version
    parameters: dict[str, Any] = Field(default_factory=dict)
    parity: Parity | None = None
    changes: str | None = None            # one line: how it differs from the previous version

    @field_validator("method_version")
    @classmethod
    def _semver(cls, v: str) -> str:
        if not SEMVER.match(v):
            raise ValueError(f"method_version {v!r} is not MAJOR.MINOR.PATCH")
        return v


class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    market: Literal["lk_bonds", "cse", "lk_savings"]
    title_key: str                        # text lives in web/messages/*.json, never here
    summary_key: str
    disclaimer_key: str                   # compliance/disclaimers.yaml
    requires_datasets: list[str] = Field(default_factory=list)    # fact tables / views, schema-qualified
    outputs: list[str]                    # models.* tables this model writes
    versions: list[Version]

    @model_validator(mode="after")
    def _versions(self) -> "Manifest":
        seen = [v.method_version for v in self.versions]
        if len(seen) != len(set(seen)):
            raise ValueError(f"{self.name}: duplicate method_version")
        if sum(v.status == "current" for v in self.versions) != 1:
            raise ValueError(f"{self.name}: exactly one version must be 'current'")
        for out in self.outputs:
            if not out.startswith("models."):
                raise ValueError(f"{self.name}: output {out} is not in the models schema")
        return self

    @property
    def current(self) -> Version:
        return next(v for v in self.versions if v.status == "current")

    def version(self, method_version: str) -> Version:
        for v in self.versions:
            if v.method_version == method_version:
                return v
        raise KeyError(f"{self.name} has no version {method_version}")

    @property
    def active_versions(self) -> list[Version]:
        return [v for v in self.versions if v.status != "retired"]


def load_manifest(name: str, root: Path = MODELS_DIR) -> Manifest:
    path = root / name / "manifest.yaml"
    manifest = Manifest.model_validate(yaml.safe_load(path.read_text()))
    if manifest.name != name:
        raise ValueError(f"{path}: name {manifest.name!r} does not match its folder")
    return manifest


def model_names(root: Path = MODELS_DIR) -> list[str]:
    return sorted(p.parent.name for p in root.glob("*/manifest.yaml") if not p.parent.name.startswith("_"))


def output_owners(root: Path = MODELS_DIR) -> dict[str, str]:
    """{output table: the model that writes it}."""
    owners: dict[str, str] = {}
    for name in model_names(root):
        for table in load_manifest(name, root).outputs:
            if table != "models.model_stats":
                owners[table] = name
    return owners


# --- inputs ---------------------------------------------------------------------------------------------------

class UndeclaredInput(RuntimeError):
    """A model asked for a dataset its manifest does not declare."""


class Inputs:
    """What a model may read. Every read is fingerprinted, so a run records exactly which data it saw."""

    def __init__(self, conn: psycopg.Connection, manifest: Manifest, version: Version,
                 owners: dict[str, str] | None = None, relations: dict[str, str] | None = None):
        self._conn = conn
        self._relations = relations or {}      # dataset -> relation to read instead (parity runs: temp tables)
        self.manifest = manifest
        self.version = version
        self.params = dict(version.parameters)
        self._owners = owners if owners is not None else output_owners()
        self._row_hashes: list[str] = []

    def rows(self, dataset: str, columns: str = "*", where: str = "", params: tuple | list = (),
             order_by: str = "", group_by: str = "") -> list[dict]:
        """select <columns> from <dataset> [where ...] [order by ...]. For another model's outputs, only the
        version this model pins is visible."""
        clauses, args = [], []
        if dataset in self.manifest.requires_datasets:
            pass
        elif dataset in self._owners and self._owners[dataset] in self.version.requires_models:
            clauses.append("method_version = %s")
            args.append(self.version.requires_models[self._owners[dataset]])
        else:
            raise UndeclaredInput(f"{self.manifest.name} {self.version.method_version} does not declare {dataset}")
        if where:
            clauses.append(f"({where})")
            args.extend(params)
        sql = f"select {columns} from {self._relations.get(dataset, dataset)}"
        if clauses:
            sql += " where " + " and ".join(clauses)
        if group_by:
            sql += f" group by {group_by}"
        if order_by:
            sql += f" order by {order_by}"
        out = [dict(r) for r in self._conn.execute(sql, args)]
        for r in out:
            self._row_hashes.append(hashlib.sha256((dataset + "\x1f" + _canonical(r)).encode()).hexdigest())
        return out

    @property
    def fingerprint(self) -> str:
        """Order-independent SHA-256 over every row read so far."""
        h = hashlib.sha256()
        for item in sorted(self._row_hashes):
            h.update(item.encode())
        return h.hexdigest()


def _canonical(row: dict) -> str:
    return json.dumps({k: _plain(v) for k, v in sorted(row.items())}, sort_keys=True, default=str)


def _plain(v):
    if isinstance(v, decimal.Decimal):
        return float(v)
    if isinstance(v, (dt.date, dt.datetime)):
        return v.isoformat()
    return v


# --- writing outputs ------------------------------------------------------------------------------------------

@dataclass
class TableInfo:
    name: str
    columns: dict[str, str]          # column -> data_type
    key: list[str]


def table_info(conn: psycopg.Connection, table: str) -> TableInfo:
    schema, name = table.split(".", 1)
    cols = {r["column_name"]: r["data_type"] for r in conn.execute(
        """select column_name, data_type from information_schema.columns
           where table_schema = %s and table_name = %s order by ordinal_position""", (schema, name))}
    if not cols:
        raise KeyError(f"no such table {table}")
    key = [r["attname"] for r in conn.execute(
        """select a.attname from pg_index i
           join pg_attribute a on a.attrelid = i.indrelid and a.attnum = any(i.indkey)
           where i.indrelid = %s::regclass and i.indisprimary
           order by array_position(i.indkey, a.attnum)""", (table,))]
    return TableInfo(table, cols, key)


def _coerce(value, data_type: str):
    """Plug-ins may hand back numpy / pandas scalars or ISO strings; store plain Python values of the column type."""
    if value is None:
        return None
    if hasattr(value, "item") and not isinstance(value, (str, bytes)):     # numpy scalar
        value = value.item()
    if isinstance(value, float) and math.isnan(value):
        return None
    if data_type == "date":
        if isinstance(value, dt.datetime):
            return value.date()
        if isinstance(value, dt.date):
            return value
        if hasattr(value, "date"):                                         # pandas Timestamp
            return value.date()
        return dt.date.fromisoformat(str(value)[:10])
    if data_type in ("double precision", "real", "numeric"):
        value = float(value)
        return None if math.isnan(value) else value
    if data_type in ("integer", "bigint", "smallint"):
        if isinstance(value, float) and not value.is_integer():
            raise ValueError(f"non-integer {value} for an integer column")
        return int(value)
    if data_type == "boolean":
        return bool(value)
    return value if isinstance(value, str) else str(value)


def same_value(a, b) -> bool:
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, float) or isinstance(b, float):
        a, b = float(a), float(b)
        return a == b or abs(a - b) <= max(REL_TOL * max(abs(a), abs(b)), ABS_TOL)
    return a == b


@dataclass
class WriteCounts:
    inserted: int = 0
    updated: int = 0
    deleted: int = 0
    unchanged: int = 0

    def __iadd__(self, other: "WriteCounts") -> "WriteCounts":
        self.inserted += other.inserted
        self.updated += other.updated
        self.deleted += other.deleted
        self.unchanged += other.unchanged
        return self


class DuplicateOutputKey(ValueError):
    pass


def write_table(conn: psycopg.Connection, table: str, rows: list[dict], *, method_version: str, run_id: int,
                model: str | None = None, record_revisions: bool = True) -> WriteCounts:
    """Make the table's rows for this (model,) method_version equal `rows`, recording every revision.

    record_revisions=False is for reference versions only: series shown to nobody, kept to compare with the old
    tools, which rewrote their own tables in full every day."""
    info = table_info(conn, table)
    scope = {"method_version": method_version}
    if "model" in info.columns:
        scope["model"] = model
    data_cols = [c for c in info.columns if c != "run_id"]

    new: dict[tuple, dict] = {}
    for raw in rows:
        unknown = set(raw) - set(data_cols)
        if unknown:
            raise KeyError(f"{table}: unknown column(s) {sorted(unknown)}")
        row = {c: _coerce({**raw, **scope}.get(c), info.columns[c]) for c in data_cols}
        k = tuple(row[c] for c in info.key)
        if k in new:
            raise DuplicateOutputKey(f"{table}: two rows for key {dict(zip(info.key, k))}")
        new[k] = row

    where = " and ".join(f"{c} = %s" for c in scope)
    existing = {tuple(r[c] for c in info.key): r for r in conn.execute(
        f"select {', '.join(data_cols)} from {table} where {where}", tuple(scope.values()))}

    counts = WriteCounts()
    to_insert, revisions, to_delete = [], [], []
    for k, row in new.items():
        old = existing.get(k)
        if old is None:
            to_insert.append(row)
        elif all(same_value(old[c], row[c]) for c in data_cols):
            counts.unchanged += 1
        else:
            revisions.append((k, old, row))
            to_delete.append(k)
            to_insert.append(row)
            counts.updated += 1
    for k, old in existing.items():
        if k not in new:
            revisions.append((k, old, None))
            to_delete.append(k)
            counts.deleted += 1
    counts.inserted = len(to_insert) - counts.updated

    if revisions and record_revisions:
        with conn.cursor() as cur:
            cur.executemany(
                """insert into models.revisions (run_id, table_name, method_version, row_key, old_row, new_row)
                   values (%s, %s, %s, %s, %s, %s)""",
                [(run_id, table, method_version, Jsonb({c: _plain(v) for c, v in zip(info.key, k)}),
                  Jsonb({c: _plain(v) for c, v in old.items()}),
                  Jsonb({c: _plain(v) for c, v in row.items()}) if row is not None else None)
                 for k, old, row in revisions])
    if to_delete:   # in one statement through a temporary table: a row-by-row delete is far too slow at scale
        keys = ", ".join(info.key)
        with conn.cursor() as cur:
            cur.execute(f"create temp table _deleted on commit drop as select {keys} from {table} with no data")
            with cur.copy(f"copy _deleted ({keys}) from stdin") as cp:
                for k in to_delete:
                    cp.write_row(k)
            cur.execute(f"delete from {table} t using _deleted d where "
                        + " and ".join(f"t.{c} = d.{c}" for c in info.key))
            cur.execute("drop table _deleted")
    if to_insert:
        cols = data_cols + ["run_id"]
        with conn.cursor() as cur, cur.copy(f"copy {table} ({', '.join(cols)}) from stdin") as cp:
            for row in to_insert:
                cp.write_row([row[c] for c in data_cols] + [run_id])
    return counts


# --- running a model ------------------------------------------------------------------------------------------

class OutputMismatch(RuntimeError):
    """compute() returned tables other than exactly those its manifest declares."""


@dataclass
class RunResult:
    model: str
    method_version: str
    run_id: int
    counts: WriteCounts = field(default_factory=WriteCounts)
    inputs_sha256: str = ""
    message: str | None = None


def compute_function(name: str):
    return importlib.import_module(f"data_platform.models.{name}.compute").compute


def run_version(conn: psycopg.Connection, manifest: Manifest, version: Version, *, code_version: str,
                as_of: dt.date | None = None, owners: dict[str, str] | None = None) -> RunResult:
    """Compute one version of one model and write its outputs, all in one transaction.

    as_of is refused here: a model computed "as of" a past date returns only rows up to it, and writing that would
    delete every later row. Use data_platform.jobs.models --as-of, which computes without writing."""
    if as_of is not None:
        raise ValueError("as_of runs are compute-only; they never write (python -m data_platform.jobs.models --as-of)")
    run_id = conn.execute(
        """insert into models.runs (model, method_version, code_version, as_of) values (%s, %s, %s, %s)
           returning run_id""", (manifest.name, version.method_version, code_version, as_of)).fetchone()["run_id"]
    conn.commit()
    result = RunResult(manifest.name, version.method_version, run_id)
    try:
        inputs = Inputs(conn, manifest, version, owners)
        outputs = compute_function(manifest.name)(inputs, as_of)
        if set(outputs) != set(manifest.outputs):
            raise OutputMismatch(f"{manifest.name}: compute returned {sorted(outputs)}, manifest declares "
                                 f"{sorted(manifest.outputs)}")
        for table in manifest.outputs:
            result.counts += write_table(conn, table, outputs[table], method_version=version.method_version,
                                         run_id=run_id, model=manifest.name,
                                         record_revisions=version.status != "reference")
        result.inputs_sha256 = inputs.fingerprint
        c = result.counts
        # Same inputs as the last good run, yet different outputs: the model is not deterministic. That is a bug
        # to fix (it would make published history wobble), so it is recorded on the run for the daily check.
        previous = conn.execute(
            """select inputs_sha256, code_version from models.runs
               where model = %s and method_version = %s and status = 'ok'
               order by run_id desc limit 1""", (manifest.name, version.method_version)).fetchone()
        message = None
        if (previous and previous["inputs_sha256"] == result.inputs_sha256 and previous["code_version"] == code_version
                and code_version != "unknown" and (c.updated or c.deleted)):
            message = f"NONDETERMINISTIC: same inputs as the previous run, {c.updated + c.deleted} rows changed"
            log.error("%s %s: %s", manifest.name, version.method_version, message)
        result.message = message
        conn.execute(
            """update models.runs set finished_at = now(), status = 'ok', inputs_sha256 = %s, rows_inserted = %s,
               rows_updated = %s, rows_deleted = %s, rows_unchanged = %s, message = %s where run_id = %s""",
            (result.inputs_sha256, c.inserted, c.updated, c.deleted, c.unchanged, message, run_id))
        conn.commit()
        log.info("%s %s: %s", manifest.name, version.method_version, c)
        return result
    except BaseException as exc:
        conn.rollback()
        conn.execute("update models.runs set finished_at = now(), status = 'failed', message = %s where run_id = %s",
                     (f"{type(exc).__name__}: {exc}"[:4000], run_id))
        conn.commit()
        raise
