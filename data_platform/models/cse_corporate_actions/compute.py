"""cse_corporate_actions: the CSE's dividends, sub-divisions, scrip and rights issues, read from its structured
announcement records (audit C6, the old terminal's data/history/corporate_actions.csv).

Version 1 ports MinimumLizard/CSE@f263830 cse/corpactions.py (load_records, parse, superseded, effective) line for
line; only names and comments are reworded. The rules it keeps:
  * amounts and ratios come only from the CSE's numeric fields, or from text that states them explicitly; nothing
    is inferred. A row whose figure was read from free text, or whose fields are incomplete or contradictory, is
    `needs_review` and is not used until the owner confirms it (config/corporate_actions_review.yaml, loaded into
    cse.corporate_action_reviews before each run);
  * a rights issue is always `needs_review` (its ratio is text);
  * one event per (share, type, ex-date): a repeated or amended announcement replaces the earlier one.
Numbers are stored as the old CSV stored them: rounded to 8 decimal places (old cse/storage.py fmt()).

Outputs: models.cse_corporate_action (every row, and what became of it) and models.cse_corporate_action_used (the
actions total returns use, with the owner's corrections applied). See METHOD.md.
"""
from __future__ import annotations

import datetime as dt
import math
import re
from dataclasses import dataclass
from urllib.parse import quote

CDN = "https://cdn.cse.lk/"
EQUITY_SUFFIXES = (".N0000", ".X0000")
SLT = dt.timezone(dt.timedelta(hours=5, minutes=30))
CA_COLS = ["id", "symbol", "type", "ex_date", "amount_per_share", "ratio_new", "ratio_held", "factor",
           "subscription_price", "status", "note", "source_url"]
NUMERIC = ("amount_per_share", "ratio_new", "ratio_held", "factor", "subscription_price")
CA_KEYWORDS = ("DIVIDEND", "SUB-DIVISION", "SUBDIVISION", "SUB DIVISION", "RIGHTS", "SCRIP", "CAPITALI",
               "CONSOLIDATION", "BONUS")
TYPED, GENERAL = "getAnnouncementById", "getGeneralAnnouncementById"


def is_ca_category(category: str) -> bool:
    c = (category or "").upper()
    return any(k in c for k in CA_KEYWORDS) and "DEBENTURE" not in c


# --- reading the CSE's fields (old cse/corpactions.py, unchanged arithmetic) -------------------------------------

_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
          "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20}


def ms_to_date(ms: int) -> dt.date:
    return dt.datetime.fromtimestamp(ms / 1000, SLT).date()


def parse_date(v) -> str | None:
    """API dates come as '01 Jul 2026' strings or epoch-ms numbers (midnight Sri Lanka time)."""
    if v in (None, ""):
        return None
    if isinstance(v, (int, float)):
        return ms_to_date(int(v)).isoformat()
    for fmt in ("%d %b %Y", "%d-%b-%Y", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(str(v).strip(), fmt).date().isoformat()
        except ValueError:
            continue
    return None


def parse_rights_text(text: str | None) -> tuple[float, float] | None:
    """'Three (3) new Ordinary Voting Shares for every Fifty (50) existing ...' -> (3, 50).

    Uses the numerals in parentheses when present (they are unambiguous), else number words. Returns (new, existing)
    or None when the text does not state both."""
    if not text:
        return None
    t = text.lower()
    m = re.search(r"\((\d+(?:\.\d+)?)\)[^()]*?new.*?every[^()]*?\((\d+(?:\.\d+)?)\)", t)
    if m:
        return float(m.group(1)), float(m.group(2))
    if ":" in t or "every" not in t:
        return None
    head, _, tail = t.partition("every")
    if "preference" in head:                       # preference shares are not an ordinary rights issue
        return None
    a = re.findall(r"\d+(?:\.\d+)?", head)        # '06 new ordinary shares for every 01 existing'
    b = re.findall(r"\d+(?:\.\d+)?", tail)
    if len(a) == 1 and b:
        return float(a[0]), float(b[0])
    m = re.search(r"(\w+)\s+(?:\(\w+\)\s+)?new.*?every\s+(\w+)", t)
    if m and m.group(1) in _WORDS and m.group(2) in _WORDS:
        return float(_WORDS[m.group(1)]), float(_WORDS[m.group(2)])
    return None


def _num(v) -> float | None:
    try:
        f = float(v)
        return f if f == f else None
    except (TypeError, ValueError):
        return None


def parse_proportion(v) -> tuple[float | None, str]:
    """Scrip proportion = existing shares per 1 new share. Returns (existing_per_new, how).

    The field is sometimes a number and sometimes text: '1 for 136.0022997317', '1 share for every 115.38 shares',
    'one scrip issue for every 80.41807', '1for115.25'. Text is accepted only in the form "1 new for N" with exactly
    one other number N; anything else returns (None, 'unparsed')."""
    n = _num(v)
    if n is not None:
        return (n, "numeric") if n > 0 else (None, "unparsed")
    text = str(v or "").strip()
    if ":" in text:                       # "1:5" does not say which side is new; never guessed
        return None, "unparsed"
    if not re.match(r"^(1\b|1for|one\b)", text, re.I):
        return None, "unparsed"
    others = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", text) if float(x) != 1.0]
    return (others[0], "text") if len(others) == 1 and others[0] > 1 else (None, "unparsed")


def scrip_check(issued, existing_per_new: float, shares_now: float | None) -> bool | None:
    """Shares issued x proportion should be about the shares outstanding before the issue. `shares_now` (the latest
    quantity issued) includes the scrip shares, so the expected ratio is about 1 / (1 + 1/N). None: nothing to check
    against."""
    issued = _num(issued)
    if not issued or not shares_now:
        return None
    ratio = issued * existing_per_new / shares_now
    return 0.85 <= ratio <= 1.05


@dataclass
class Record:
    """One announcement: list row + detail (typed or general)."""
    aid: int
    company_symbol: str          # the symbol the list was asked for (voting line)
    category: str
    date: str                    # ISO, or '' when the CSE's date could not be read
    detail: dict | None          # reqBaseAnnouncement
    docs: list
    source: str                  # "typed" | "general" | "none"

    @property
    def code(self) -> str:
        return self.company_symbol.split(".")[0]

    @property
    def url(self) -> str:
        if not self.docs:
            return ""
        d = self.docs[0]
        base = d.get("baseUrl") if str(d.get("baseUrl") or "").startswith("https://") else CDN
        return base.rstrip("/") + "/" + quote(str(d.get("fileUrl", "")).lstrip("/"), safe="/")


def parse(records: list[Record], share_classes: dict[str, list[str]],
          shares_out: dict[str, float] | None = None) -> list[dict]:
    """Records -> corporate-action rows. `share_classes`: code -> symbols; `shares_out`: symbol -> latest quantity
    issued (for the scrip share-count check). Old cse/corpactions.parse."""
    rows: list[dict] = []
    by_code: dict[str, list[Record]] = {}
    for r in records:
        by_code.setdefault(r.code, []).append(r)

    def row(rec, symbol, typ, **kw):
        base = {"id": f"{rec.aid}:{symbol}", "symbol": symbol, "type": typ, "ex_date": None,
                "amount_per_share": None, "ratio_new": None, "ratio_held": None, "factor": None,
                "subscription_price": None, "status": "confirmed", "note": "", "source_url": rec.url,
                "announcement_id": rec.aid, "announced_date": rec.date or None}
        base.update(kw)
        return base

    for code, recs in by_code.items():
        classes = share_classes.get(code, [])
        voting = next((s for s in classes if s.endswith(".N0000")), None)
        nonvoting = next((s for s in classes if s.endswith(".X0000")), None)
        for rec in recs:
            d = rec.detail or {}
            dtype = d.get("dType") or ""
            cat = rec.category.upper()

            # Cash dividend with dates (typed). One row per share class.
            if dtype == "CashDividendWithDates":
                xd = parse_date(d.get("xd"))
                for sym, key, flag in ((voting, "votingDivPerShare", "votingShare"),
                                       (nonvoting, "nonVotingDivPerShare", "noneVotingShare")):
                    amt = _num(d.get(key))
                    if amt is None and sym == voting:
                        amt = _num(d.get("divPerShare"))
                    if not sym or not d.get(flag, sym == voting) or not amt:
                        continue
                    status, note = ("confirmed", "") if xd else ("needs_review", "no XD date in record")
                    rows.append(row(rec, sym, "cash_dividend", ex_date=xd, amount_per_share=amt,
                                    status=status, note=note))
                continue

            # Scrip dividend with dates (typed). Proportion = existing shares per 1 new share.
            if dtype == "ScripDividendWithDates":
                xd = parse_date(d.get("xd"))
                for sym, pkey, ikey in ((voting, "votingPropotion", "votingNumSharesIssued"),
                                        (nonvoting, "nonVotingPropotion", "nonVotingNumSharesIssued")):
                    if not sym or d.get(pkey) in (None, ""):
                        continue
                    prop, how = parse_proportion(d.get(pkey))
                    check = scrip_check(d.get(ikey), prop, (shares_out or {}).get(sym)) if prop else None
                    ok = bool(xd and prop and check is not False and (how == "numeric" or check))
                    note = "" if how == "numeric" else f"proportion from field text {str(d.get(pkey)).strip()[:60]!r}"
                    if check is not None:
                        note += ("; " if note else "") + f"share-count check {'passed' if check else 'FAILED'}"
                    if not xd:
                        note += "; no XD date"
                    rows.append(row(rec, sym, "scrip", ex_date=xd, ratio_new=1.0 if prop else None, ratio_held=prop,
                                    factor=(prop + 1) / prop if prop else None,
                                    status="confirmed" if ok else "needs_review", note=note.strip("; ")))
                continue

            # Announced without dates: if no dated record exists within 120 days either side (the undated one can
            # precede it, or follow it), list it for review (amount or proportion known, ex-date missing).
            if dtype in ("ScripDividendToBeNotified", "CashDividendDatesToBeNotified"):
                want = "ScripDividendWithDates" if dtype.startswith("Scrip") else "CashDividendWithDates"
                if rec.date:
                    d0 = dt.date.fromisoformat(rec.date)
                    lo, hi = (d0 - dt.timedelta(days=120)).isoformat(), (d0 + dt.timedelta(days=120)).isoformat()
                else:
                    lo, hi = "", "9999"
                if any((x.detail or {}).get("dType") == want and lo <= x.date <= hi for x in recs):
                    continue
                if dtype.startswith("Scrip"):
                    for sym, pkey in ((voting, "votingPropotion"), (nonvoting, "nonVotingPropotion")):
                        prop, _ = parse_proportion(d.get(pkey))
                        if sym and prop:
                            rows.append(row(rec, sym, "scrip", ratio_new=1.0, ratio_held=prop, factor=(prop + 1) / prop,
                                            status="needs_review",
                                            note="no dated scrip record found: add ex_date when confirming"))
                else:
                    amt = _num(d.get("votingDivPerShare")) or _num(d.get("divPerShare"))
                    if voting and amt:
                        rows.append(row(rec, voting, "cash_dividend", amount_per_share=amt, status="needs_review",
                                        note="no dated dividend record found: add ex_date when confirming"))
                continue

            # Share sub-division: ratio from share counts (typed); ex-date from the (DATES) record.
            if dtype == "ShareSplits":
                dates = next((x for x in recs if x.source == "general" and "SUB" in x.category.upper()
                              and "DIVISION" in x.category.upper() and x.date >= rec.date), None)
                ex = parse_date((dates.detail or {}).get("tradingCommencement")) if dates else None
                for sym, ek, rk in ((voting, "votingExistingNumOfShares", "votingResultingNumOfShares"),
                                    (nonvoting, "nonVotingExistingNumOfShares", "nonVotingResultingNumOfShares")):
                    e, r_ = _num(d.get(ek)), _num(d.get(rk))
                    if not sym or not e or not r_:
                        continue
                    f = r_ / e
                    ok = ex is not None
                    # The dates record's id is part of the row id, so when the dates arrive later a new, complete
                    # row appears (the earlier needs_review row is then superseded).
                    rid = f"{rec.aid}+{dates.aid}:{sym}" if dates else f"{rec.aid}:{sym}"
                    rows.append(row(rec, sym, "subdivision", id=rid, ex_date=ex, ratio_new=f - 1, ratio_held=1.0,
                                    factor=f, status="confirmed" if ok else "needs_review",
                                    note="ex-date = trading commencement after the split" if ok
                                    else "split dates not yet announced"))
                continue

            # Rights: price from the typed record, XR from the (DATES) record; the ratio is text.
            if rec.source == "general" and "RIGHTS" in cat and d.get("xr"):
                xr = parse_date(d.get("xr"))
                typed = [x for x in recs if (x.detail or {}).get("dType") == "RightsIssue"
                         and x.date <= rec.date and _num(x.detail.get("votingShareConsideration"))]
                price_rec = typed[-1] if typed else None
                for sym, pkey, ckey in ((voting, "votingProportion", "votingShareConsideration"),
                                        (nonvoting, "nonVotingProportion", "nonVotingShareConsideration")):
                    text = d.get(pkey) or ((price_rec.detail or {}).get(
                        "votingShrsPropToBeIssued" if sym == voting else "nonVotingShrsPropToBeIssued") if price_rec else None)
                    if not sym or not text:
                        continue
                    ratio = parse_rights_text(text)
                    s_price = _num((price_rec.detail or {}).get(ckey)) if price_rec else None
                    rows.append(row(rec, sym, "rights", ex_date=xr,
                                    ratio_new=ratio[0] if ratio else None, ratio_held=ratio[1] if ratio else None,
                                    subscription_price=s_price, status="needs_review",
                                    note=f"ratio read from text: {text.strip()[:90]!r}"
                                         + ("" if s_price else "; subscription price not found")
                                         + (f"; terms in announcement {price_rec.aid}" if price_rec else "")))
                continue

            if dtype and dtype not in ("RightsIssue",) and voting:
                rows.append(row(rec, voting, "scrip", status="needs_review",
                                note=f"unrecognised record type {dtype!r} ({rec.category}): check the PDF"))
                continue

            # Anything else that looks like a corporate action, without a structured parser: listed, no numbers.
            if any(k in cat for k in ("CAPITALI", "CONSOLIDATION", "BONUS")) and voting:
                rows.append(row(rec, voting, "scrip" if "CONSOLIDATION" not in cat else "subdivision",
                                status="needs_review", note=f"unstructured: {rec.category}"))
    return rows


# --- the owner's confirmations (old cse/corpactions.py load_reviews, superseded, effective) ----------------------

def check_reviews(confirm: dict, reject: list) -> tuple[dict[str, dict], set[str]]:
    confirm = {str(k): (v or {}) for k, v in (confirm or {}).items()}
    unknown = {k for v in confirm.values() for k in v} - set(CA_COLS)
    if unknown:
        raise ValueError(f"corporate_actions_review: unknown fields {sorted(unknown)}")
    return confirm, {str(x) for x in (reject or [])}


def _base(row_id: str) -> str:
    """'32457+33380:CIC.N0000' -> '32457:CIC.N0000' (first announcement id + symbol)."""
    head, _, sym = row_id.partition(":")
    return head.split("+")[0] + ":" + sym


def superseded(rows: list[dict]) -> set[str]:
    """Ids of needs_review rows replaced by a different, complete row for the same announcement and symbol (e.g. a
    split first seen without dates, later completed by its dates record)."""
    complete: dict[str, set[str]] = {}
    for r in rows:
        if r["status"] != "needs_review" and r["ex_date"]:
            complete.setdefault(_base(r["id"]), set()).add(r["id"])
    return {r["id"] for r in rows
            if r["status"] == "needs_review" and complete.get(_base(r["id"]), set()) - {r["id"]}}


def effective(rows: list[dict], reviews: tuple[dict[str, dict], set[str]]) -> list[dict]:
    """Rows usable for returns: confirmed rows, plus needs_review rows the owner confirmed (with any corrections
    applied). Rejected ids are dropped. Old cse/corpactions.effective."""
    confirm, reject = reviews
    gone = superseded(rows)
    out = []
    for r in rows:
        r = dict(r)
        if r["id"] in reject or r["id"] in gone:
            continue
        if r["status"] == "needs_review":
            if r["id"] not in confirm:
                continue
            r.update({k: v for k, v in confirm[r["id"]].items()})
            r["status"] = "confirmed (reviewed)"
        out.append(r)
    # One event per (symbol, type, ex-date): an amended or repeated announcement replaces the earlier one instead of
    # being counted twice. The latest announcement id wins.
    latest: dict[tuple, dict] = {}
    for r in sorted(out, key=lambda r: int(r["id"].split(":")[0].split("+")[0])):
        latest[(r["symbol"], r["type"], r["ex_date"])] = r
    out = list(latest.values())
    for r in out:
        for k in NUMERIC:
            r[k] = _num(r[k]) if r[k] not in (None, "") else None
        if r["type"] in ("subdivision", "scrip") and r["factor"] is None and r["ratio_new"] and r["ratio_held"]:
            r["factor"] = (r["ratio_held"] + r["ratio_new"]) / r["ratio_held"]
        if isinstance(r["ex_date"], (dt.date, dt.datetime)):   # YAML reads 2026-04-02 as a date
            r["ex_date"] = r["ex_date"].isoformat()[:10]
        if r["ex_date"] in ("", None):
            raise ValueError(f"corporate action {r['id']} is usable but has no ex_date")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(r["ex_date"])):
            raise ValueError(f"corporate action {r['id']}: ex_date {r['ex_date']!r} is not YYYY-MM-DD")
        need = {"cash_dividend": ("amount_per_share",), "subdivision": ("factor",), "scrip": ("factor",),
                "rights": ("ratio_new", "ratio_held", "subscription_price")}.get(r["type"], ())
        missing = [k for k in need if not r[k]]
        if missing:
            raise ValueError(f"corporate action {r['id']} ({r['type']}) is usable but has no {', '.join(missing)}: "
                             "add it in config/corporate_actions_review.yaml")
    return out


def use_status(row: dict, reviews: tuple[dict[str, dict], set[str]], gone: set[str], used: set[str]) -> str:
    confirm, reject = reviews
    if row["id"] in reject:
        return "rejected"
    if row["id"] in gone:
        return "superseded"
    if row["status"] == "needs_review" and row["id"] not in confirm:
        return "awaiting_confirmation"
    return "used" if row["id"] in used else "replaced"     # replaced: a later announcement for the same event


def as_stored(v):
    """Numbers as the old CSV stored them (cse/storage.py fmt): whole numbers exactly, others to 8 decimals."""
    if isinstance(v, float) and not math.isnan(v) and not (v.is_integer() and abs(v) < 1e15):
        return round(v, 8)
    return v


# --- the inputs, as the old load_records, share_classes and shares_outstanding read them -------------------------

def records(inputs, as_of) -> list[Record]:
    """Announcements in a corporate-action category, each with its detail: typed if there is one, else general.
    First every company list (old data/raw/announcements/byCompany), then the CSE's daily announcement list for
    announcements no company list has (old announcements.csv)."""
    date_where = "(announced_date is null or announced_date <= %s)" if as_of else ""
    params = (as_of,) if as_of else ()
    details: dict[tuple[int, str], dict] = {}
    for r in inputs.rows("cse.announcement_details", "announcement_id, endpoint, base, docs",
                         where="has_detail", order_by="fetched_at, fetch_id"):
        details[(r["announcement_id"], r["endpoint"])] = r    # the latest response with a detail, per endpoint

    def detail(aid: int) -> tuple[dict | None, list, str]:
        for endpoint, name in ((TYPED, "typed"), (GENERAL, "general")):
            d = details.get((aid, endpoint))
            if d is not None:
                return d["base"], d["docs"] or [], name
        return None, [], "none"

    out: dict[int, Record] = {}
    for a in inputs.rows("cse.company_announcements", "symbol, announcement_id, announced_date, category",
                         where=date_where, params=params, order_by="symbol, announcement_id"):
        if not is_ca_category(a["category"]):
            continue
        aid = int(a["announcement_id"])
        base, docs, source = detail(aid)
        date = a["announced_date"].isoformat() if a["announced_date"] else ""
        out[aid] = Record(aid, a["symbol"], a["category"], date, base, docs, source)

    classes = share_classes(inputs, as_of)
    numeric_ids = "announcement_id ~ '^[0-9]+$'"            # not the financial reports ('F' ids)
    for a in inputs.rows("cse.announcements", "announcement_id, announced_date, symbol, category",
                         where=f"{numeric_ids} and announced_date <= %s" if as_of else numeric_ids,
                         params=params, order_by="announcement_id"):
        aid = int(a["announcement_id"])
        if aid in out or not is_ca_category(a["category"]):
            continue
        base, docs, source = detail(aid)
        syms = classes.get(a["symbol"] or "", [])
        voting = next((x for x in syms if x.endswith(".N0000")), syms[0] if syms else None)
        if voting:
            out[aid] = Record(aid, voting, a["category"], a["announced_date"].isoformat(), base, docs, source)
    return sorted(out.values(), key=lambda r: (r.date, r.aid))


def share_classes(inputs, as_of) -> dict[str, list[str]]:
    """code -> its ordinary share symbols, from the latest security list (on or before as_of; for a date before the
    first list stored, the first list)."""
    sub = ("(select coalesce(max(session_date) filter (where session_date <= %s), min(session_date)) "
           "from cse.security_list)" if as_of else "(select max(session_date) from cse.security_list)")
    out: dict[str, list[str]] = {}
    for s in inputs.rows("cse.security_list", "symbol", where=f"session_date = {sub}",
                         params=(as_of,) if as_of else (), order_by="symbol"):
        if s["symbol"].endswith(EQUITY_SUFFIXES):
            out.setdefault(s["symbol"].split(".")[0], []).append(s["symbol"])
    return out


def shares_outstanding(inputs, as_of) -> dict[str, float]:
    """Latest shares issued per symbol (old cse/ownership/analyse.load_market): session by session, the company
    summary's quantity issued, then the trade summary's market cap / close, which the CSE computes as shares issued
    x close."""
    where, params = ("session_date <= %s", (as_of,)) if as_of else ("", ())
    by_session: dict[dt.date, list[tuple[str, float]]] = {}
    for r in inputs.rows("cse.company_info_daily", "session_date, symbol, quantity_issued", where=where,
                         params=params, order_by="session_date, symbol"):
        if r["quantity_issued"]:
            by_session.setdefault(r["session_date"], []).append((r["symbol"], float(r["quantity_issued"])))
    from_trades: dict[dt.date, list[tuple[str, float]]] = {}
    for r in inputs.rows("cse.prices_daily_current", "session_date, symbol, market_cap, close",
                         where=" and ".join(filter(None, ["source = 'daily'", where])), params=params,
                         order_by="session_date, symbol"):
        if r["market_cap"] and r["close"]:
            from_trades.setdefault(r["session_date"], []).append((r["symbol"], float(round(r["market_cap"] / r["close"]))))
    issued: dict[str, float] = {}
    for session in sorted(set(by_session) | set(from_trades)):
        issued.update(by_session.get(session, []))
        issued.update(from_trades.get(session, []))
    return issued


def reviews(inputs, as_of) -> tuple[dict[str, dict], set[str]]:
    """The owner's confirmations: the latest version loaded (on or before as_of). None loaded: nothing confirmed."""
    sub = "(select max(version_id) from cse.corporate_action_reviews" + (
        " where loaded_at < (%s::date + 1))" if as_of else ")")
    rows = inputs.rows("cse.corporate_action_reviews", "confirm, reject", where=f"version_id = {sub}",
                       params=(as_of,) if as_of else ())
    return check_reviews(rows[0]["confirm"], rows[0]["reject"]) if rows else ({}, set())


def compute(inputs, as_of):
    rows: list[dict] = []
    seen: set[str] = set()
    for r in parse(records(inputs, as_of), share_classes(inputs, as_of), shares_outstanding(inputs, as_of)):
        if r["id"] in seen:            # the old CSV kept the first row for an id
            continue
        seen.add(r["id"])
        rows.append({k: as_stored(v) for k, v in r.items()})
    review = reviews(inputs, as_of)
    used = effective([{c: r[c] for c in CA_COLS} for r in rows], review)
    gone = superseded(rows)
    used_ids = {r["id"] for r in used}
    announced = {r["id"]: r["announced_date"] for r in rows}
    actions = [{"action_id": r["id"], "symbol": r["symbol"], "action_type": r["type"], "ex_date": r["ex_date"],
                **{k: r[k] for k in NUMERIC}, "status": r["status"], "note": r["note"],
                "source_url": r["source_url"], "announcement_id": r["announcement_id"],
                "announced_date": r["announced_date"], "use_status": use_status(r, review, gone, used_ids)}
               for r in rows]
    used_rows = [{"action_id": r["id"], "symbol": r["symbol"], "action_type": r["type"], "ex_date": r["ex_date"],
                  **{k: r[k] for k in NUMERIC}, "status": r["status"], "note": r["note"] or "",
                  "source_url": r["source_url"] or "", "announced_date": announced.get(r["id"])} for r in used]
    return {"models.cse_corporate_action": actions, "models.cse_corporate_action_used": used_rows}
