"""Parity: prove that each ported model reproduces the old tool (docs/architecture.md §15).

    python -m data_platform.migration.parity bonds \\
        --old-db <Nelson-Siegel clone>/data/sgcp.sqlite --old-code <Nelson-Siegel clone> \\
        --report docs/migration/parity-bonds.json

How. The models run in memory on the migrated facts (nothing is written to the model tables: each model's outputs
go to a temporary table its dependants read instead), restricted to exactly the files the old database had read.
Then, table by table, the outputs are compared with what the old tool stored. For the three old calculations that
were never stored (liquidity, execution gap, carry: the old dashboard computed them for the latest day only), the
OLD code is imported from a read-only clone and run on the old database, read-only, for every curve day.

Tolerance: text, counts and dates exact; floating point within 1e-9 (absolute or relative), as the architecture
states. The report lists counts and the first differences for each table.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import importlib
import json
import math
import sqlite3
import sys
from pathlib import Path

from ..core import db, settings as settings_mod
from ..models import registry
from ..models.framework import Inputs, _coerce, compute_function, output_owners, table_info

TOL = 1e-9


def close(a, b, tol: float = TOL) -> bool:
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, bool) or isinstance(b, bool):
        return bool(a) == bool(b)
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        a, b = float(a), float(b)
        if math.isnan(a) or math.isnan(b):
            return math.isnan(a) and math.isnan(b)
        return abs(a - b) <= tol or abs(a - b) <= tol * max(abs(a), abs(b))
    return _text(a) == _text(b)


def _text(v):
    return v.isoformat() if isinstance(v, (dt.date, dt.datetime)) else v


def compare(name: str, old: dict, new: dict, columns: list[str], tol: float = TOL) -> dict:
    """old/new: {key: {column: value}}. Every key and every value must agree."""
    missing = [k for k in old if k not in new]
    extra = [k for k in new if k not in old]
    differ, worst = [], 0.0
    for k in old:
        if k not in new:
            continue
        for c in columns:
            a, b = old[k].get(c), new[k].get(c)
            if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
                worst = max(worst, abs(float(a) - float(b)))
            if not close(a, b, tol):
                differ.append((k, c, a, b))
    return {"table": name, "old_rows": len(old), "new_rows": len(new), "missing_in_new": len(missing),
            "extra_in_new": len(extra), "values_differ": len(differ), "max_abs_difference": worst,
            "examples": {"missing": [list(map(str, k)) for k in missing[:3]],
                         "extra": [list(map(str, k)) for k in extra[:3]],
                         "differ": [[list(map(str, k)), c, str(a), str(b)] for k, c, a, b in differ[:5]]},
            "ok": not missing and not extra and not differ}


# --- running the models in memory -----------------------------------------------------------------------------

def run_chain(conn, names: list[str], parameter_overrides: dict[str, dict] | None = None, *,
              as_of=None, pick=None) -> dict[str, list[dict]]:
    """Run models in dependency order, in memory: nothing is written; each model's outputs go to a temporary table
    its dependants read instead. By default each model's parity version (the one with a `parity` block); `pick`
    chooses another (e.g. the current one), `as_of` limits every input to that date."""
    manifests = registry.load_all()
    owners = output_owners()
    relations: dict[str, str] = {}
    results: dict[str, list[dict]] = {}
    for name in registry.order(manifests):
        if name not in names:
            continue
        m = manifests[name]
        version = pick(m) if pick else next(v for v in m.versions if v.parity is not None)
        params = {**version.parameters, **(parameter_overrides or {}).get(name, {})}
        version = version.model_copy(update={"parameters": params})
        outputs = compute_function(name)(Inputs(conn, m, version, owners, relations), as_of)
        for table, rows in outputs.items():
            results[table] = rows
            if table == "models.model_stats":
                continue
            temp = "parity_" + table.split(".", 1)[1]
            conn.execute(f"create temp table if not exists {temp} (like {table})")
            conn.execute(f"alter table {temp} alter column run_id drop not null")
            conn.execute(f"truncate {temp}")
            info = table_info(conn, table)
            cols = [c for c in info.columns if c != "run_id"]
            with conn.cursor() as cur, cur.copy(f"copy {temp} ({', '.join(cols)}) from stdin") as cp:
                for r in rows:
                    full = {**r, "method_version": version.method_version}
                    cp.write_row([_coerce(full.get(c), info.columns[c]) for c in cols])
            relations[table] = temp
    return results


# --- the old side ---------------------------------------------------------------------------------------------

def open_old(old_db: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{old_db}?mode=ro", uri=True)        # read-only: the old data is never touched
    conn.row_factory = sqlite3.Row
    return conn


@contextlib.contextmanager
def old_code(path: Path):
    """Import the old tool's modules from a clone, without writing bytecode into it."""
    saved_path, saved_flag = list(sys.path), sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(path))
    try:
        yield lambda module: importlib.import_module(module)
    finally:
        sys.path[:] = saved_path
        sys.dont_write_bytecode = saved_flag
        for mod in [m for m in sys.modules if m.split(".")[0] in ("pipeline", "curves", "signals", "dashboard")]:
            del sys.modules[mod]


def _rows(conn, sql) -> list[dict]:
    return [dict(r) for r in conn.execute(sql)]


def _keyed(rows, key_cols) -> dict:
    return {tuple(_text(r[c]) for c in key_cols): {c: _text(v) for c, v in r.items()} for r in rows}


def bonds_parity(conn, old_db: Path, old_code_dir: Path | None) -> dict:
    old = open_old(old_db)
    urls = {r["url"] for r in old.execute("select url from files")}
    names = ["bond_identity", "bond_ns_curve", "bond_rv_zscores", "bond_liquidity", "bond_execution_gap",
             "bond_carry"]
    new = run_chain(conn, names, {"bond_identity": {"only_urls": urls}})
    out = []

    ref_cols = ["coupon_pct", "maturity_date", "tenor_years", "series_label", "issue_date", "coupon_dates",
                "first_seen_date", "notes"]
    out.append(compare("bond_identity: bonds", _keyed(_rows(old, "select * from bonds"), ["isin"]),
                       _keyed(new["models.bond_reference"], ["isin"]), ref_cols, tol=0))
    quote_cols = ["bid_yield", "offer_yield", "mid_yield", "bid_price", "offer_price"]
    out.append(compare("bond_identity: quotes",
                       _keyed(_rows(old, "select * from observations where source='pdmo_daily' "
                                         "and raw_ref is not null"), ["obs_date", "isin"]),
                       _keyed(new["models.bond_quotes"], ["obs_date", "isin"]), quote_cols, tol=0))

    fit_cols = ["beta0", "beta1", "beta2", "lambda_years", "n_quotes", "rmse_bp", "n_trades", "trade_rmse_bp",
                "trade_bias_bp"]
    out.append(compare("bond_ns_curve: curve_fits", _keyed(_rows(old, "select * from curve_fits"), ["obs_date"]),
                       _keyed(new["models.bond_curve_fit"], ["obs_date"]), fit_cols))
    point_cols = ["tau_years", "observed_yield", "fitted_yield", "residual_bp", "weight"]
    out.append(compare("bond_ns_curve: curve_residuals",
                       _keyed(_rows(old, "select * from curve_residuals"), ["obs_date", "isin", "source"]),
                       _keyed(new["models.bond_curve_point"], ["obs_date", "isin", "source"]), point_cols))

    z_old = [{**r, "deviation_bp": r["dislocation_bp"]} for r in _rows(old, "select * from bond_signals")]
    out.append(compare("bond_rv_zscores: bond_signals", _keyed(z_old, ["obs_date", "isin"]),
                       _keyed(new["models.bond_residual_zscore"], ["obs_date", "isin"]),
                       ["residual_bp", "mean_bp", "sd_bp", "deviation_bp", "zscore", "n_window"]))
    p_old = [{**r, "deviation_bp": r["dislocation_bp"]} for r in _rows(old, "select * from switch_signals")]
    out.append(compare("bond_rv_zscores: switch_signals", _keyed(p_old, ["obs_date", "isin_a", "isin_b"]),
                       _keyed(new["models.bond_pair_zscore"], ["obs_date", "isin_a", "isin_b"]),
                       ["tau_a", "tau_b", "spread_bp", "mean_bp", "sd_bp", "deviation_bp", "zscore", "n_window"]))
    s_old = {(r["key"].replace("switch_", "pair_"),): {"value": r["value"], "n": r["n"]}
             for r in _rows(old, "select * from signal_stats")}
    s_new = {(r["stat_key"],): r for r in new["models.model_stats"]}
    out.append(compare("bond_rv_zscores: signal_stats", s_old, s_new, ["value", "n"]))

    if old_code_dir:
        dates = [r["obs_date"] for r in _rows(old, "select obs_date from curve_fits order by obs_date")]
        with old_code(old_code_dir) as load:
            liquidity, execution, carry = (load("signals.liquidity"), load("signals.execution"),
                                           load("signals.carry"))
            liq_old, gap_old, fund_old, carry_old = {}, {}, {}, {}
            for d in dates:
                for isin, facts in liquidity.profile(old, d).items():
                    liq_old[(d, isin)] = facts
                g = execution.gap(old, d)
                if g:
                    gap_old[(d,)] = g
                f = carry.funding_rate(old, d)
                if f:
                    fund_old[(d,)] = {**f, "bill_as_of": f["as_of"]}
                for isin, facts in carry.profile(old, d, entry_gap_bp=g["gap_bp"] if g else 0.0).items():
                    carry_old[(d, isin)] = {**facts, "entry_gap_bp": g["gap_bp"] if g else 0.0}
        liq_cols = ["turnover_lkr", "n_trades", "days_traded", "is_benchmark", "last_auction", "days_since_auction",
                    "post_auction", "bid_to_cover", "tier", "last_trade_date", "last_trade_yield",
                    "days_since_trade", "trades_through", "trade_data_lag_days"]
        out.append(compare("bond_liquidity: liquidity.profile()", liq_old,
                           _keyed(new["models.bond_liquidity"], ["obs_date", "isin"]), liq_cols))
        out.append(compare("bond_execution_gap: execution.gap()", gap_old,
                           _keyed(new["models.bond_execution_gap"], ["obs_date"]), ["gap_bp", "n", "window_days"]))
        out.append(compare("bond_carry: carry.funding_rate()", fund_old,
                           _keyed(new["models.bond_funding"], ["obs_date"]),
                           ["bill_pct", "rate_pct", "spread_bp", "bill_as_of", "stale_days", "n_bills",
                            "window_days"]))
        out.append(compare("bond_carry: carry.profile()", carry_old,
                           _keyed(new["models.bond_carry"], ["obs_date", "isin"]),
                           ["entry_gap_bp", "entry_yield", "price", "duration", "carry_bp", "roll_bp", "total_bp",
                            "per_duration_bp"]))
    return {"checks": out, "ok": all(c["ok"] for c in out),
            "old_code_compared": bool(old_code_dir)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("market", choices=["bonds", "cse"])
    ap.add_argument("--old-db", type=Path, help="bonds: the old sgcp.sqlite")
    ap.add_argument("--old-code", type=Path, help="a read-only clone of the old repo at the audited commit")
    ap.add_argument("--report", type=Path, required=True)
    args = ap.parse_args(argv)
    conn = db.connect(settings_mod.load().database_url)
    if args.market == "bonds":
        report = bonds_parity(conn, args.old_db, args.old_code)
    else:
        from .parity_cse import cse_parity
        report = cse_parity(conn, args.old_code)
    conn.rollback()
    report["generated_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, default=str) + "\n")
    for c in report["checks"]:
        print(f"{'ok  ' if c['ok'] else 'FAIL'} {c['table']}: old {c['old_rows']}, new {c['new_rows']}, "
              f"missing {c['missing_in_new']}, extra {c['extra_in_new']}, differ {c['values_differ']}, "
              f"max |diff| {c['max_abs_difference']:.3g}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
