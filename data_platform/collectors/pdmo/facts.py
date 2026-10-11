"""Turn one PDMO file into database rows, exactly as published. Pure: bytes in, rows out.

The old pipeline did two things while ingesting that this layer deliberately does not:
  * it resolved each quote's series label to an ISIN, and dropped quotes it could not resolve (about 38 a day,
    the administered restructuring bonds). Here every quote row is kept, keyed by its series label as printed.
    Resolution is a versioned model step (Phase 3, parity item B1).
  * it updated rows in place when a parser changed. Here a parser change bumps PARSER_VERSION and the new rows
    are added beside the old ones.

Bump PARSER_VERSION whenever a change to any parser in this package could change any output row.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from . import parse_auction, parse_daily, parse_trades, series
from .errors import ParseError

PARSER_VERSION = 1

TABLE_FOR_KIND = {
    "daily_summary": "bonds.quotes",
    "volumes": "bonds.volumes",
    "trade_summary": "bonds.trades",
    "bond_auction": "bonds.auction_results",
    "bond_issuance": "bonds.auction_announcements",
}


@dataclass
class ParsedFile:
    kind: str
    report_date: date
    trading_date: date | None = None
    rows: list[dict] = field(default_factory=list)
    note: str = ""

    @property
    def table(self) -> str:
        return TABLE_FOR_KIND[self.kind]


def parse_file(kind: str, body: bytes, label_date: date | None = None) -> ParsedFile:
    """Dispatch on the file kind the index page gave it. Raises ParseError for anything unusable."""
    if kind == "daily_summary":
        parsed = parse_daily.parse_daily_summary(body)
        rows = [{
            "row_no": i,
            "report_date": parsed.reporting_date,
            "trading_date": parsed.trading_date,
            "series_label": q["series_label"],
            "printed_label": q["printed_label"],
            "coupon_pct": q["coupon_pct"],
            "n_coupon_steps": len(series.coupon_steps(q["series_label"])),
            "maturity_date": q["maturity_date"],
            "bid_price": q["bid_price"],
            "offer_price": q["offer_price"],
            "bid_yield": q["bid_yield"],
            "offer_yield": q["offer_yield"],
        } for i, q in enumerate(parsed.quotes)]
        return ParsedFile(kind, parsed.reporting_date, parsed.trading_date, rows,
                          f"{len(rows)} quote rows; {parsed.skipped_rows} all-zero rows (matured bonds) skipped")

    if kind == "volumes":
        parsed = parse_daily.parse_volumes(body)
        # The derived date is arithmetic on the data itself; the index label is the fallback. Titles lie.
        obs_date = parsed.derived_date or label_date
        if obs_date is None:
            raise ParseError(f"no usable observation date (title {parsed.title!r})")
        note = f"{len(parsed.rows)} volume rows"
        if label_date and obs_date != label_date:
            note += f"; derived date {obs_date} differs from index label {label_date} (data trusted)"
        rows = [{"row_no": i, "obs_date": obs_date, "isin": r["isin"], "maturity_date": r["maturity_date"],
                 "volume_lkr": r["volume_lkr"]} for i, r in enumerate(parsed.rows)]
        return ParsedFile(kind, obs_date, None, rows, note)

    if kind == "trade_summary":
        parsed = parse_trades.parse(body, label_date=label_date)
        rows = [{"row_no": i, "obs_date": parsed.obs_date, **r} for i, r in enumerate(parsed.rows)]
        return ParsedFile(kind, parsed.obs_date, None, rows, f"{len(rows)} trade rows")

    if kind == "bond_auction":
        parsed = parse_auction.parse(body)
        rows = [{"row_no": i, "auction_date": parsed.auction_date, "kind": parsed.kind,
                 "settlement_date": parsed.settlement_date, **b} for i, b in enumerate(parsed.bonds)]
        labelled = sum(1 for b in parsed.bonds if b["series_label"])
        return ParsedFile(kind, parsed.auction_date, None, rows,
                          f"{parsed.kind}: {len(rows)} bonds ({labelled} with a series label)")

    if kind == "bond_issuance":
        parsed = parse_auction.parse_announcement(body)
        rows = [{"row_no": i, "auction_date": parsed.auction_date, "settlement_date": parsed.settlement_date, **b}
                for i, b in enumerate(parsed.bonds)]
        return ParsedFile(kind, parsed.auction_date, None, rows, f"announcement: {len(rows)} bonds offered")

    raise ValueError(f"unknown PDMO file kind {kind!r}")
