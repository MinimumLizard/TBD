"""cse_ownership: who owns the CSE's listed companies, read from the top-20 shareholder tables in their interim reports
(audit C13-C16; the old terminal's data/ownership/{holdings,companies,owners}.csv).

Version 1 runs the old code (ported line for line into data_platform/models/_lib: cse_tables, cse_names,
cse_ownership) as at every session the old daily job could have run (a session with a trade summary), each time with
only the facts known by then: the security list, share counts and market caps up to that session, the reports
uploaded by then (and whose period is not after it), and the owner's confirmations. So the row for a session never
changes when later sessions arrive; it changes only if a fact dated on or before it arrives late (a report collected
after its upload date) or the owner corrects a confirmation.

Outputs (see METHOD.md):
  models.cse_holding             every parsed table row of every report, as checked at the latest session
                                 (the old holdings.csv). Names private individuals: unpublished.
  models.cse_ownership_detail    per company and session, the old companies.csv plus the ownership group (names
                                 controllers, possibly individuals: unpublished).
  models.cse_company_ownership   per company and session, what the site may show: no individual is ever named.
"""
from __future__ import annotations

import datetime as dt
import re
from collections import defaultdict

from .._lib import cse_names as names
from .._lib import cse_ownership as own
from .._lib.cse_reads import known_on, market_data, reports, texts

TYPES = ("listed", "company", "institution", "individual", "joint", "estate", "trust", "nominee")
FLOAT_BLOCK = 10.0              # % of the voting shares: a block this large is not part of the free float
PERSONAL_TITLE = re.compile(r"^\s*(?:MR|MRS|MS|MISS|DR|PROF|REV|VEN|HON|SIR|LATE)\b\.?", re.I)


# --- reading the facts ------------------------------------------------------------------------------------------

def confirmations(inputs, as_of) -> tuple[dict, dict[str, own.Link]]:
    """(aliases, parents): the latest version stored (on or before as_of); public entries first, then private."""
    sub = "(select max(version_id) from cse.ownership_confirmations" + (
        " where loaded_at < (%s::date + 1))" if as_of else ")")
    rows = inputs.rows("cse.ownership_confirmations", "public, private", where=f"version_id = {sub}",
                       params=(as_of,) if as_of else ())
    if not rows:
        return {}, {}
    pub, priv = rows[0]["public"] or {}, rows[0]["private"] or {}
    merged = {"aliases": {**(pub.get("aliases") or {}), **(priv.get("aliases") or {})},
              "parents": {**(pub.get("parents") or {}), **(priv.get("parents") or {})}}
    return names.load_aliases(merged), own.load_links(merged)


# --- what may be published --------------------------------------------------------------------------------------

def public_name(name: str | None, typ: str | None, symbol: str | None, market: own.Market) -> str | None:
    """A holder's name only when it is a company, a fund or the state: a listed company (by its CSE name), or an
    unlisted company or institution whose name reads as one (a legal suffix or a fund word, and no personal title).
    Everything else (individuals, joint holders, estates, trusts, nominees) is never named."""
    if not name or not typ:
        return None
    if typ == "listed":
        return market.names.get(symbol or "", name)
    if typ in ("company", "institution") and not PERSONAL_TITLE.match(name):
        c = names.clean(name)
        if names.COMPANY_WORDS.search(c) or names.FUND_WORDS.search(c):
            return name
    return None


def _num(v):
    return None if v in ("", None) else v


def company_rows(session: dt.date, res: dict) -> tuple[list[dict], list[dict]]:
    """(detail rows, published rows) for one session's build."""
    market, companies, graph, links = res["market"], res["companies"], res["graph"], res["links"]
    votes, info, ctrl = graph["votes"], graph["info"], graph["control"]
    groups, labels, paths = own.group_of(companies)
    members: dict[str, list[str]] = defaultdict(list)
    for code, key in groups.items():
        members[key].append(code)
    own_shares: dict[str, float] = defaultdict(float)
    for r in res["current"]:
        if r["class"] == "N" and r["owner_symbol"] == r["code"]:
            own_shares[r["code"]] += float(r["pct"])
    detail, public = [], []
    for code, c in companies.items():
        key = groups[code]
        path = paths[code]
        head = path[-1]
        if head in companies:
            head_type, head_name = "listed", public_name(companies[head]["name"], "listed", head, market)
        else:
            prev = companies[path[-2]]
            head_type = prev["controller_type"] or None
            head_name = public_name(prev["controller_name"], head_type, info.get(head, {}).get("symbol"), market)
        detail.append({
            "session_date": session, "code": code, "name": c["name"], "report_id": _num(c["report_id"]),
            "kind": _num(c["kind"]), "period_date": _num(c["period_date"]), "report_status": c["report_status"],
            "status_n": _num(c["status_N"]), "note_n": _num(c["note_N"]), "status_x": _num(c["status_X"]),
            "note_x": _num(c["note_X"]), "rows": _num(c["rows"]),
            "top_holders_pct_voting": _num(c["top_holders_pct_voting"]), "market_cap": c["market_cap"],
            "controller_key": _num(c["controller_key"]), "controller_name": _num(c["controller_name"]),
            "controller_type": _num(c["controller_type"]), "control_pct": _num(c["control_pct"]),
            "control_level": _num(c["control_level"]), "chain": _num(c["chain"]), "group_key": key,
            "group_name": labels.get(key), "source_url": _num(c["source_url"])})
        usable = c["top_holders_pct_voting"] != ""
        by_type = defaultdict(float)
        for k, p in (votes.get(code) or {}).items():
            by_type[info.get(k, {}).get("type", "")] += p
        x = ctrl.get(code)
        public.append({
            "session_date": session, "code": code, "report_id": _num(c["report_id"]),
            "period_date": _num(c["period_date"]), "report_status": c["report_status"],
            "table_status": _num(c["status_N"]) or _num(c["status_X"]),
            "top20_pct": _num(c["top_holders_pct_voting"]),
            **{f"pct_{t}": round(by_type.get(t, 0.0), 4) if usable else None for t in TYPES},
            "pct_own_shares": round(own_shares.get(code, 0.0), 4) if usable else None,
            "controller_type": _num(c["controller_type"]),
            "controller_name": public_name(c["controller_name"], c["controller_type"],
                                           info.get(x["root"], {}).get("symbol") if x else None, market) if x else None,
            "control_pct": _num(c["control_pct"]), "control_level": _num(c["control_level"]),
            "group_id": head if head in companies else "G:" + min(members[key]),
            "group_head_type": head_type, "group_head_name": head_name, "group_size": len(members[key]),
            "free_float_pct": free_float(code, votes, info, ctrl, links, own_shares.get(code, 0.0)) if usable else None,
            "market_cap": c["market_cap"], "source_url": _num(c["source_url"])})
    return detail, public


def free_float(code: str, votes: dict, info: dict, ctrl: dict, links: dict, own_pct: float) -> float:
    """An estimate of the voting shares in free float, in %: 100, less the company's own shares, less the shares of
    holders it controls, less every block of FLOAT_BLOCK % or more (a holder's accounts and the listed companies it
    controls counted together, as for control). Directors' and their families' smaller holdings, which the CSE's
    public-holding rule also leaves out, cannot be told apart in a top-20 list, so this is an upper bound."""
    blocks: dict[str, float] = defaultdict(float)
    out = 100.0 - own_pct
    for h, p in (votes.get(code) or {}).items():
        r = own.block_root(h, ctrl, links, frozenset({"LISTED:" + code}))
        if r == "LISTED:" + code:
            out -= p
        else:
            blocks[r] += p
    out -= sum(p for p in blocks.values() if p >= FLOAT_BLOCK)
    return round(max(out, 0.0), 4)


def holding_rows(res: dict, session: dt.date) -> list[dict]:
    out, counter = [], defaultdict(int)
    for h in res["holdings"]:
        k = (h["report_id"], h["class"])
        counter[k] += 1
        out.append({"report_id": int(h["report_id"]), "share_class": h["class"], "row_no": counter[k],
                    "rank": h["rank"], "period_date": h["period_date"] or None, "code": h["code"],
                    "symbol": h["symbol"], "name_as_filed": h["name_as_filed"], "shares": h["shares"], "pct": h["pct"],
                    "fraction": h["fraction"], "owner_key": h["owner_key"], "owner_name": h["owner_name"],
                    "owner_type": h["owner_type"], "owner_symbol": h["owner_symbol"], "via": h["via"],
                    "rule": h["rule"], "table_status": h["table_status"], "source_url": h["source_url"],
                    "as_of": session})
    return out


# --- the model --------------------------------------------------------------------------------------------------

def run(inputs, as_of, sessions_wanted=None) -> dict:
    """{session: build result} for every session (or those wanted), plus the shared state. Used by compute() and by
    the parity check, which compares a session's build with the old code's."""
    data = market_data(inputs, as_of)
    reps, known_from = reports(inputs)
    cache = own.TableCache(texts(inputs, reps))
    aliases, links = confirmations(inputs, as_of)
    resolver = own.Resolver(aliases)
    sessions = [d for d in data.sessions if not as_of or d <= as_of]
    out = {}
    for i, d in enumerate(sessions):
        if sessions_wanted is not None and d not in sessions_wanted:
            continue
        last = i == len(sessions) - 1
        out[d] = own.build(data.market(d), known_on(reps, known_from, d), cache, resolver, links,
                           all_holdings=last or sessions_wanted is not None)
    return out


def compute(inputs, as_of):
    results = run(inputs, as_of)
    detail, public, holdings = [], [], []
    for d, res in results.items():
        a, b = company_rows(d, res)
        detail += a
        public += b
    if results:
        last = max(results)
        holdings = holding_rows(results[last], last)
    return {"models.cse_holding": holdings, "models.cse_ownership_detail": detail,
            "models.cse_company_ownership": public}
