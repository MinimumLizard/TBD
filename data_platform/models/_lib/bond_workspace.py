"""The old bond tool's database, rebuilt in memory, so its methods can be ported line for line (method version 1).

Ported from MinimumLizard/Nelson-Siegel at commit 1c33084: pipeline/db.py (schema and upserts) and
pipeline/ingest.py (the order files are read in, and how a quote is tied to a bond). The old tool ran its methods as
SQL against SQLite; running the ported methods against the same schema, in SQLite, is what lets version 1 reproduce
its numbers exactly. Nothing here touches the network or the platform database: the workspace is filled from rows
the framework hands over and is thrown away after the run.

Comments describe what the old code did and why; behaviour changes belong in a later method version.
"""
from __future__ import annotations

import datetime as dt
import sqlite3
from string import ascii_uppercase

from ...collectors.pdmo import isin as isin_mod, series

SCHEMA = """
CREATE TABLE bonds (
    isin TEXT PRIMARY KEY, coupon_pct REAL, maturity_date TEXT, tenor_years INTEGER, series_label TEXT,
    issue_date TEXT, coupon_dates TEXT, first_seen_date TEXT, notes TEXT);
CREATE TABLE auctions (
    auction_date TEXT NOT NULL, isin TEXT NOT NULL, kind TEXT, accrued_per_100 REAL, settlement_date TEXT,
    way_pct REAL, offered_lkr INTEGER, bids_lkr INTEGER, accepted_lkr INTEGER, raw_ref TEXT,
    PRIMARY KEY (auction_date, isin, kind));
CREATE TABLE observations (
    obs_date TEXT NOT NULL, isin TEXT NOT NULL, source TEXT NOT NULL, bid_yield REAL, offer_yield REAL,
    mid_yield REAL, bid_price REAL, offer_price REAL, volume_lkr INTEGER, executable INTEGER NOT NULL DEFAULT 0,
    raw_ref TEXT, PRIMARY KEY (obs_date, isin, source));
CREATE TABLE trade_summary (
    obs_date TEXT NOT NULL, isin TEXT NOT NULL, security_type TEXT, open_yield REAL, high_yield REAL,
    low_yield REAL, close_yield REAL, wavg_yield REAL, volume_lkr INTEGER, n_trades INTEGER, raw_ref TEXT,
    PRIMARY KEY (obs_date, isin));
CREATE TABLE curve_fits (
    obs_date TEXT PRIMARY KEY, beta0 REAL, beta1 REAL, beta2 REAL, lambda_years REAL, n_quotes INTEGER,
    rmse_bp REAL, n_trades INTEGER, trade_rmse_bp REAL, trade_bias_bp REAL, fitted_at TEXT);
CREATE TABLE curve_residuals (
    obs_date TEXT NOT NULL, isin TEXT NOT NULL, source TEXT NOT NULL, tau_years REAL, observed_yield REAL,
    fitted_yield REAL, residual_bp REAL, weight REAL, PRIMARY KEY (obs_date, isin, source));
CREATE INDEX bonds_series ON bonds(series_label);
CREATE INDEX observations_isin ON observations(isin, source);
CREATE INDEX trade_summary_date ON trade_summary(obs_date);
CREATE INDEX curve_residuals_isin ON curve_residuals(isin, source);
"""

KIND_ORDER = {"bond_issuance": 0, "bond_auction": 1, "volumes": 2, "trade_summary": 3, "daily_summary": 4}


def open_workspace() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def iso(value) -> str | None:
    return value.isoformat() if isinstance(value, (dt.date, dt.datetime)) else value


# --- pipeline/db.py, ported -----------------------------------------------------------------------------------

def upsert_bond(conn, isin, coupon_pct, maturity_date, tenor_years, first_seen_date,
                notes=None, series_label=None, issue_date=None, coupon_dates=None):
    """Insert a bond, or fill in blanks on an existing row: COALESCE(old, new); first_seen_date only moves earlier."""
    conn.execute(
        """INSERT INTO bonds (isin, coupon_pct, maturity_date, tenor_years, first_seen_date, notes, series_label,
                              issue_date, coupon_dates)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(isin) DO UPDATE SET
               coupon_pct      = COALESCE(bonds.coupon_pct, excluded.coupon_pct),
               maturity_date   = COALESCE(bonds.maturity_date, excluded.maturity_date),
               tenor_years     = COALESCE(bonds.tenor_years, excluded.tenor_years),
               notes           = COALESCE(bonds.notes, excluded.notes),
               series_label    = COALESCE(bonds.series_label, excluded.series_label),
               issue_date      = COALESCE(bonds.issue_date, excluded.issue_date),
               coupon_dates    = COALESCE(bonds.coupon_dates, excluded.coupon_dates),
               first_seen_date = MIN(COALESCE(bonds.first_seen_date, excluded.first_seen_date),
                                     COALESCE(excluded.first_seen_date, bonds.first_seen_date))""",
        (isin, coupon_pct, maturity_date, tenor_years, first_seen_date, notes, series_label, issue_date,
         coupon_dates))


def upsert_quote(conn, obs_date, isin, bid_yield, offer_yield, bid_price, offer_price, raw_ref):
    mid = (bid_yield + offer_yield) / 2 if bid_yield is not None and offer_yield is not None else None
    conn.execute(
        """INSERT INTO observations (obs_date, isin, source, bid_yield, offer_yield, mid_yield, bid_price,
                                     offer_price, raw_ref)
           VALUES (?, ?, 'pdmo_daily', ?, ?, ?, ?, ?, ?)
           ON CONFLICT(obs_date, isin, source) DO UPDATE SET
               bid_yield = excluded.bid_yield, offer_yield = excluded.offer_yield, mid_yield = excluded.mid_yield,
               bid_price = excluded.bid_price, offer_price = excluded.offer_price, raw_ref = excluded.raw_ref""",
        (obs_date, isin, bid_yield, offer_yield, mid, bid_price, offer_price, raw_ref))


def upsert_volume(conn, obs_date, isin, volume_lkr):
    conn.execute(
        """INSERT INTO observations (obs_date, isin, source, volume_lkr) VALUES (?, ?, 'pdmo_daily', ?)
           ON CONFLICT(obs_date, isin, source) DO UPDATE SET volume_lkr = excluded.volume_lkr""",
        (obs_date, isin, volume_lkr))


def upsert_trade_summary(conn, obs_date, isin, security_type, open_yield, high_yield, low_yield, close_yield,
                         wavg_yield, volume_lkr, n_trades, raw_ref):
    conn.execute(
        """INSERT INTO trade_summary (obs_date, isin, security_type, open_yield, high_yield, low_yield,
                                      close_yield, wavg_yield, volume_lkr, n_trades, raw_ref)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(obs_date, isin) DO UPDATE SET
               security_type = excluded.security_type, open_yield = excluded.open_yield,
               high_yield = excluded.high_yield, low_yield = excluded.low_yield,
               close_yield = excluded.close_yield, wavg_yield = excluded.wavg_yield,
               volume_lkr = excluded.volume_lkr, n_trades = excluded.n_trades, raw_ref = excluded.raw_ref""",
        (obs_date, isin, security_type, open_yield, high_yield, low_yield, close_yield, wavg_yield, volume_lkr,
         n_trades, raw_ref))


def _drop_empty_observations(conn):
    conn.execute("""DELETE FROM observations
                    WHERE bid_yield IS NULL AND offer_yield IS NULL AND bid_price IS NULL
                      AND offer_price IS NULL AND volume_lkr IS NULL""")


def clear_quotes(conn, raw_ref):
    conn.execute("""UPDATE observations SET bid_yield = NULL, offer_yield = NULL, mid_yield = NULL,
                           bid_price = NULL, offer_price = NULL, raw_ref = NULL WHERE raw_ref = ?""", (raw_ref,))
    _drop_empty_observations(conn)


def clear_volumes(conn, obs_date):
    conn.execute("UPDATE observations SET volume_lkr = NULL WHERE obs_date = ? AND source = 'pdmo_daily'",
                 (obs_date,))
    _drop_empty_observations(conn)


def clear_trade_summary(conn, raw_ref):
    conn.execute("DELETE FROM trade_summary WHERE raw_ref = ?", (raw_ref,))


def upsert_auction(conn, auction_date, isin, kind, settlement_date, way_pct, offered_lkr, bids_lkr, accepted_lkr,
                   raw_ref, accrued_per_100=None):
    conn.execute(
        """INSERT INTO auctions (auction_date, isin, kind, settlement_date, way_pct, offered_lkr, bids_lkr,
                                 accepted_lkr, raw_ref, accrued_per_100)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(auction_date, isin, kind) DO UPDATE SET
               settlement_date = excluded.settlement_date, way_pct = excluded.way_pct,
               offered_lkr = excluded.offered_lkr, bids_lkr = excluded.bids_lkr,
               accepted_lkr = excluded.accepted_lkr, accrued_per_100 = excluded.accrued_per_100,
               raw_ref = excluded.raw_ref""",
        (auction_date, isin, kind, settlement_date, way_pct, offered_lkr, bids_lkr, accepted_lkr, raw_ref,
         accrued_per_100))


def upsert_auction_observation(conn, obs_date, isin, way_pct, volume_lkr, raw_ref):
    conn.execute(
        """INSERT INTO observations (obs_date, isin, source, mid_yield, volume_lkr, executable, raw_ref)
           VALUES (?, ?, 'auction', ?, ?, 1, ?)
           ON CONFLICT(obs_date, isin, source) DO UPDATE SET
               mid_yield = excluded.mid_yield, volume_lkr = excluded.volume_lkr, executable = 1,
               raw_ref = excluded.raw_ref""",
        (obs_date, isin, way_pct, volume_lkr, raw_ref))


def clear_auction(conn, raw_ref):
    conn.execute("DELETE FROM auctions WHERE raw_ref = ?", (raw_ref,))
    conn.execute("DELETE FROM observations WHERE source='auction' AND raw_ref = ?", (raw_ref,))


def repair(conn) -> None:
    """Clear a step-coupon `notes` stamped on a bond whose own label has one coupon (old db._repair).

    It ran on every connect, so it ran once more after the last ingest before any model read the table."""
    for row in conn.execute("SELECT isin, series_label, notes FROM bonds WHERE notes IS NOT NULL").fetchall():
        note_is_stepped = len(series.coupon_steps(row["notes"])) > 1
        bond_is_stepped = len(series.coupon_steps(row["series_label"])) > 1
        if note_is_stepped and not bond_is_stepped:
            conn.execute("UPDATE bonds SET notes = NULL WHERE isin = ?", (row["isin"],))


# --- pipeline/ingest.py, ported: one function per file kind, fed with the stored fact rows of that file ---------

def bond_lookup(conn):
    """(exact {label: isin}, letter-insensitive {label: {isins}}, {maturity: [bond rows]}), real ISINs only."""
    by_label: dict[str, str] = {}
    stripped: dict[str, set] = {}
    by_maturity: dict[str, list] = {}
    for row in conn.execute("SELECT * FROM bonds WHERE isin LIKE 'LKB%'"):
        if row["series_label"]:
            by_label[row["series_label"]] = row["isin"]
            stripped.setdefault(row["series_label"].rstrip(ascii_uppercase), set()).add(row["isin"])
        by_maturity.setdefault(row["maturity_date"], []).append(row)
    return by_label, stripped, by_maturity


def resolve_isin(lookup, quote, strict: bool = False) -> tuple[str | None, str]:
    """Series label first; then the label without its series letter, if that names exactly one bond; then maturity
    plus an agreeing coupon (tolerance 0.005), if exactly one bond. Otherwise unresolved, never guessed."""
    by_label, stripped, by_maturity = lookup
    label = quote["series_label"]
    if label and label in by_label:
        return by_label[label], "label"
    if label:
        same = stripped.get(label.rstrip(ascii_uppercase), set())
        if len(same) == 1:
            candidate = next(iter(same))
            # Version 1 trusted the letter-free label alone. strict (version 2) also requires the bond's maturity, and
            # its coupon where known, to agree: otherwise the 13.00%2029A quote is filed under 2029B on any day the
            # 2029B row is missing from the file (2026-10-11 audit).
            if not strict or _agrees(lookup, candidate, quote):
                return candidate, "label-no-letter"
    coupon = quote["coupon_pct"]
    candidates = by_maturity.get(iso(quote["maturity_date"]), [])
    agreeing = [bond for bond in candidates
                if bond["coupon_pct"] is None or coupon is None or abs(bond["coupon_pct"] - coupon) < 0.005]
    if len(agreeing) == 1:
        return agreeing[0]["isin"], "maturity+coupon"
    return None, "unresolved"


def _agrees(lookup, isin: str, quote) -> bool:
    for bond in lookup[2].get(iso(quote["maturity_date"]), []):
        if bond["isin"] == isin:
            return bond["coupon_pct"] is None or quote["coupon_pct"] is None or abs(bond["coupon_pct"] - quote["coupon_pct"]) < 0.005
    return False


MAX_SYNTHETIC_SPREAD_BP = 50.0


def admissible_without_isin(quote) -> bool:
    """An unresolved quote still counts if it is a single-coupon bond with a two-way price 0-50 bp wide; the
    2023 restructuring block (step coupons, administered 13.00/12.00, 100 bp wide) does not."""
    if len(series.coupon_steps(quote["series_label"])) != 1:
        return False
    if quote["coupon_pct"] is None:
        return False
    bid, offer = quote["bid_yield"], quote["offer_yield"]
    if bid is None or offer is None:
        return False
    return 0.0 < (bid - offer) * 100.0 <= MAX_SYNTHETIC_SPREAD_BP


def ingest_volumes(conn, obs_date: str, rows: list[dict]) -> None:
    clear_volumes(conn, obs_date)
    for row in rows:
        tenor, maturity = isin_mod.decode(row["isin"])
        upsert_bond(conn, row["isin"], None, maturity.isoformat(), tenor, obs_date)
        upsert_volume(conn, obs_date, row["isin"], row["volume_lkr"])


def ingest_daily_summary(conn, obs_date: str, rows: list[dict], raw_ref: str, resolved: dict | None = None) -> dict:
    """Returns {method: count}. `resolved`, if given, collects {(obs_date, isin): method} for each stored quote."""
    clear_quotes(conn, raw_ref)
    lookup = bond_lookup(conn)
    how = {"label": 0, "label-no-letter": 0, "maturity+coupon": 0, "synthetic": 0, "unresolved": 0}
    for quote in rows:
        matched, method = resolve_isin(lookup, quote)
        if matched is None and admissible_without_isin(quote):
            matched, method = isin_mod.synthetic_key(quote["coupon_pct"], quote["maturity_date"]), "synthetic"
        how[method] += 1
        if matched is None:
            continue
        upsert_bond(conn, matched, quote["coupon_pct"], iso(quote["maturity_date"]), None, obs_date,
                    notes=quote["printed_label"], series_label=quote["series_label"])
        upsert_quote(conn, obs_date, matched, quote["bid_yield"], quote["offer_yield"], quote["bid_price"],
                     quote["offer_price"], raw_ref)
        if resolved is not None:
            resolved[(obs_date, matched)] = method
    return how


# --- version 2 of bond_identity (decision 0014): every quote row is kept --------------------------------------

PRECEDENCE = {"label": 0, "label-no-letter": 1, "maturity+coupon": 2}


def cash_flow_key(quote, taken: set) -> str:
    """A key for a quote no release ties to an ISIN, built from its own cash flows: maturity and every coupon step
    (step-coupon bonds keep all their rates, so two bonds differing only in a later step stay distinct)."""
    steps = series.coupon_steps(quote["series_label"])
    if len(steps) == 1 and quote["coupon_pct"] is not None:
        key = isin_mod.synthetic_key(quote["coupon_pct"], quote["maturity_date"])
    elif steps:
        key = f"{isin_mod.SYNTHETIC_PREFIX}{iso(quote['maturity_date'])}:{'%'.join(f'{c:.3f}' for c in steps)}"
    else:
        key = f"{isin_mod.SYNTHETIC_PREFIX}{iso(quote['maturity_date'])}:{quote['printed_label']}"
    base, n = key, 2
    while key in taken:                    # never two rows under one key on one day
        key, n = f"{base}#{n}", n + 1
    return key


def ingest_daily_summary_all(conn, obs_date: str, rows: list[dict], raw_ref: str, resolved: dict) -> dict:
    """Like ingest_daily_summary, but no quote is left out and none overwrites another.

    A bond carries one quote a day. When two rows resolve to the same bond (finding V1: the old matcher filed the
    13.00%2029A quote under the 2029B bond, overwriting one of them every day), the row identified most directly
    keeps it (exact label, then label without its letter, then maturity and coupon) and the other is keyed on its
    own cash flows. Rows that resolve to nothing (the restructuring block, one-way quotes) are keyed the same way."""
    clear_quotes(conn, raw_ref)
    lookup = bond_lookup(conn)
    matches = [(i, q, *resolve_isin(lookup, q, strict=True)) for i, q in enumerate(rows)]
    best: dict[str, tuple[int, str]] = {}
    for i, _, key, method in matches:
        if key is not None and (key not in best or PRECEDENCE[method] < PRECEDENCE[best[key][1]]):
            best[key] = (i, method)
    taken = {key for key in best}
    how = {"label": 0, "label-no-letter": 0, "maturity+coupon": 0, "synthetic": 0}
    for i, quote, key, method in matches:
        if key is None or best[key][0] != i:
            key, method = cash_flow_key(quote, taken), "synthetic"
            taken.add(key)
        how[method] += 1
        upsert_bond(conn, key, quote["coupon_pct"], iso(quote["maturity_date"]), None, obs_date,
                    notes=quote["printed_label"], series_label=quote["series_label"])
        upsert_quote(conn, obs_date, key, quote["bid_yield"], quote["offer_yield"], quote["bid_price"],
                     quote["offer_price"], raw_ref)
        resolved[(obs_date, key)] = method
    return how


def ingest_trade_summary(conn, obs_date: str, rows: list[dict], raw_ref: str) -> None:
    clear_trade_summary(conn, raw_ref)
    for row in rows:
        decoded = isin_mod.decode(row["isin"])
        if decoded:
            tenor, maturity = decoded
            upsert_bond(conn, row["isin"], None, maturity.isoformat(), tenor, obs_date)
        upsert_trade_summary(conn, obs_date, row["isin"], row["security_type"], row["open_yield"],
                             row["high_yield"], row["low_yield"], row["close_yield"], row["wavg_yield"],
                             row["volume_lkr"], row["n_trades"], raw_ref)


def ingest_announcement(conn, auction_date: str, rows: list[dict], raw_ref: str) -> None:
    clear_auction(conn, raw_ref)
    for bond in rows:
        tenor, _ = isin_mod.decode(bond["isin"])
        upsert_bond(conn, bond["isin"], bond["coupon_pct"], iso(bond["maturity_date"]), tenor, auction_date,
                    series_label=bond["series_label"], issue_date=iso(bond["issue_date"]),
                    coupon_dates=bond["coupon_dates"])
        upsert_auction(conn, auction_date, bond["isin"], "announced", iso(bond["settlement_date"]), None,
                       bond["offered_lkr"], None, None, raw_ref, accrued_per_100=bond["accrued_per_100"])


def ingest_auction(conn, auction_date: str, rows: list[dict], raw_ref: str) -> None:
    clear_auction(conn, raw_ref)
    for bond in rows:
        tenor, _ = isin_mod.decode(bond["isin"])
        upsert_bond(conn, bond["isin"], bond["coupon_pct"], iso(bond["maturity_date"]), tenor, auction_date,
                    series_label=bond["series_label"])
        upsert_auction(conn, auction_date, bond["isin"], bond["kind"], iso(bond["settlement_date"]),
                       bond["way_pct"], bond["offered_lkr"], bond["bids_lkr"], bond["accepted_lkr"], raw_ref)
        if bond["way_pct"] is not None:
            upsert_auction_observation(conn, auction_date, bond["isin"], bond["way_pct"], bond["accepted_lkr"],
                                       raw_ref)


def ingest_order(files: list[dict]) -> list[dict]:
    """The old backfill order: announcements, auction results, volumes, trades, then quotes (which need the labels
    the others teach); within a kind, oldest posted first, so an amended report overwrites its original."""
    return sorted(files, key=lambda f: (KIND_ORDER[f["kind"]], f["posted_date"] or f["label_date"] or dt.date.min,
                                        f["report_date"] or dt.date.min, f["fetch_id"]))


def raw_ref(url: str) -> str:
    """The old tool's file reference: the uuid at the end of the PDMO file URL."""
    return url.rstrip("/").rsplit("/", 1)[-1]


# --- filling a workspace from the platform's model outputs (for the models downstream of identity) -------------

def load_reference(conn, rows: list[dict]) -> None:
    conn.executemany(
        """INSERT INTO bonds (isin, coupon_pct, maturity_date, tenor_years, series_label, issue_date, coupon_dates,
                              first_seen_date, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [(r["isin"], r["coupon_pct"], iso(r["maturity_date"]), r["tenor_years"], r["series_label"],
          iso(r["issue_date"]), r["coupon_dates"], iso(r["first_seen_date"]), r["notes"]) for r in rows])


def load_quotes(conn, rows: list[dict]) -> None:
    conn.executemany(
        """INSERT INTO observations (obs_date, isin, source, bid_yield, offer_yield, mid_yield, bid_price,
                                     offer_price) VALUES (?, ?, 'pdmo_daily', ?, ?, ?, ?, ?)""",
        [(iso(r["obs_date"]), r["isin"], r["bid_yield"], r["offer_yield"], r["mid_yield"], r["bid_price"],
          r["offer_price"]) for r in rows])


def load_trades(conn, rows: list[dict]) -> None:
    conn.executemany(
        # OR REPLACE: as the old ingest's upsert, a repeated ISIN in one trade file keeps its last row
        """INSERT OR REPLACE INTO trade_summary (obs_date, isin, security_type, open_yield, high_yield, low_yield,
                                      close_yield, wavg_yield, volume_lkr, n_trades) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [(iso(r["obs_date"]), r["isin"], r["security_type"], r["open_yield"], r["high_yield"], r["low_yield"],
          r["close_yield"], r["wavg_yield"], r["volume_lkr"], r["n_trades"]) for r in rows])


def load_auctions(conn, results: list[dict], announcements: list[dict]) -> None:
    """Both auction tables, as the old `auctions` table held them ('announced' rows beside results)."""
    for r in announcements:
        upsert_auction(conn, iso(r["auction_date"]), r["isin"], "announced", iso(r["settlement_date"]), None,
                       r["offered_lkr"], None, None, None, accrued_per_100=r["accrued_per_100"])
    for r in results:
        upsert_auction(conn, iso(r["auction_date"]), r["isin"], r["kind"], iso(r["settlement_date"]), r["way_pct"],
                       r["offered_lkr"], r["bids_lkr"], r["accepted_lkr"], None)


def load_curve(conn, fits: list[dict], points: list[dict]) -> None:
    conn.executemany(
        """INSERT INTO curve_fits (obs_date, beta0, beta1, beta2, lambda_years, n_quotes, rmse_bp, n_trades,
                                   trade_rmse_bp, trade_bias_bp) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [(iso(r["obs_date"]), r["beta0"], r["beta1"], r["beta2"], r["lambda_years"], r["n_quotes"], r["rmse_bp"],
          r["n_trades"], r["trade_rmse_bp"], r["trade_bias_bp"]) for r in fits])
    conn.executemany(
        """INSERT INTO curve_residuals (obs_date, isin, source, tau_years, observed_yield, fitted_yield, residual_bp,
                                        weight) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        [(iso(r["obs_date"]), r["isin"], r["source"], r["tau_years"], r["observed_yield"], r["fitted_yield"],
          r["residual_bp"], r["weight"]) for r in points])
