"""bond_identity: tie every dealer quote to a bond (audit B1).

Version 1 reproduces the old tool exactly: starting from the old tool's own bond list (bonds.legacy_reference),
every stored PDMO file is replayed, in the old tool's order, through its ported ingest logic
(models/_lib/bond_workspace.py), and the resulting bond list and resolved quotes are the outputs. Quotes the old logic could not tie to a bond (the administered restructuring block, one-way quotes) are
left out, as they were. See METHOD.md.
"""
from __future__ import annotations

from .._lib import bond_workspace as ws

FACT_TABLES = {
    "daily_summary": "bonds.quotes",
    "volumes": "bonds.volumes",
    "trade_summary": "bonds.trades",
    "bond_auction": "bonds.auction_results",
    "bond_issuance": "bonds.auction_announcements",
}


def replay(inputs, as_of):
    """Fill an old-schema workspace from the facts. Returns (workspace, {(date, isin): how resolved}, {ref: sha})."""
    only_urls = inputs.params.get("only_urls")          # parity runs: exactly the files the old database had read
    files = inputs.rows("bonds.files_latest_parse",
                        "url, raw_sha256, parser_version, kind, posted_date, label_date, report_date, fetch_id",
                        where="report_date <= %s" if as_of else "", params=(as_of,) if as_of else ())
    latest: dict[str, dict] = {}
    for f in files:                                     # one content per URL: the newest fetch
        if only_urls is not None and f["url"] not in only_urls:
            continue
        if f["url"] not in latest or f["fetch_id"] > latest[f["url"]]["fetch_id"]:
            latest[f["url"]] = f
    facts: dict[tuple, list[dict]] = {}
    for kind, table in FACT_TABLES.items():
        for row in inputs.rows(table, order_by="raw_sha256, parser_version, row_no"):
            facts.setdefault((kind, row["raw_sha256"], row["parser_version"]), []).append(row)

    conn = ws.open_workspace()
    seed = inputs.params.get("legacy_reference_sha256")
    if seed:   # start from the old tool's own bond list (decision 0015)
        rows = inputs.rows("bonds.legacy_reference", where="source_sha256 = %s", params=(seed,), order_by="isin")
        if not rows:
            raise RuntimeError(f"bonds.legacy_reference has no rows from {seed}: run the history migration first")
        ws.load_reference(conn, rows)
    resolved: dict[tuple, str] = {}
    for f in ws.ingest_order(list(latest.values())):
        rows = facts.get((f["kind"], f["raw_sha256"], f["parser_version"]), [])
        ref = ws.raw_ref(f["url"])
        day = f["report_date"].isoformat()
        if f["kind"] == "volumes":
            ws.ingest_volumes(conn, day, rows)
        elif f["kind"] == "daily_summary":
            ws.ingest_daily_summary(conn, day, rows, ref, resolved)
        elif f["kind"] == "trade_summary":
            ws.ingest_trade_summary(conn, day, rows, ref)
        elif f["kind"] == "bond_issuance":
            ws.ingest_announcement(conn, day, rows, ref)
        else:
            ws.ingest_auction(conn, day, rows, ref)
    ws.repair(conn)
    sha_of_ref = {ws.raw_ref(f["url"]): f["raw_sha256"] for f in latest.values()}
    return conn, resolved, sha_of_ref


def compute(inputs, as_of):
    conn, resolved, sha_of_ref = replay(inputs, as_of)
    reference = [dict(r) for r in conn.execute("SELECT * FROM bonds ORDER BY isin")]
    quotes = [{"obs_date": r["obs_date"], "isin": r["isin"], "bid_yield": r["bid_yield"],
               "offer_yield": r["offer_yield"], "mid_yield": r["mid_yield"], "bid_price": r["bid_price"],
               "offer_price": r["offer_price"], "resolved_by": resolved[(r["obs_date"], r["isin"])],
               "raw_sha256": sha_of_ref[r["raw_ref"]]}
              for r in conn.execute("""SELECT * FROM observations WHERE source = 'pdmo_daily'
                                       AND raw_ref IS NOT NULL ORDER BY obs_date, isin""")]
    return {"models.bond_reference": reference, "models.bond_quotes": quotes}
