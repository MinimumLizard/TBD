"""Who owns the CSE's listed companies, as at one session (audit C13-C16). Shared by cse_ownership and
cse_fundamentals.

A port of MinimumLizard/CSE@e05c6f3 cse/ownership/analyse.py (build, choose_tables, entity_for, analyse, control),
groups.py (chains, group_of) and parents.py (load: the owner's confirmed parents of unlisted holders). The
arithmetic and every rule are unchanged; the plumbing differs:

  * the old code read its raw session folders, its report index and text files, and two YAML files; here the same
    facts arrive as rows (MarketData, Report), read from the database by the models, and the owner's confirmations
    arrive as data (cse.ownership_confirmations, loaded by data_platform/jobs/reviews.py);
  * the old code ran once a day, as at its latest session. `as_of_session` runs it as at any session, using only
    the facts known by then, so a model can keep one row per session that later sessions never change;
  * parsing a report's text does not depend on the session, so it is done once per report (TableCache) and each
    session works on a fresh copy of the parsed tables, exactly as the old code worked on freshly parsed ones.
"""
from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field

import numpy as np

from . import cse_names as names
from . import cse_tables as parse

EQUITY_SUFFIXES = (".N0000", ".X0000")
HOLDING_COLS = ["report_id", "period_date", "code", "symbol", "class", "rank", "name_as_filed", "shares", "pct",
                "fraction", "owner_key", "owner_name", "owner_type", "owner_symbol", "via", "rule", "table_status",
                "source_url"]
COMPANY_COLS = ["code", "name", "report_id", "kind", "period_date", "report_status", "status_N", "note_N",
                "status_X", "note_X", "rows", "top_holders_pct_voting", "market_cap", "controller_key",
                "controller_name", "controller_type", "control_pct", "control_level", "chain", "source_url"]
OWNER_COLS = ["key", "name", "type", "symbol", "holdings", "direct_value", "lookthrough_value",
              "companies_controlled", "controlled_market_cap", "companies_influenced", "names_as_filed"]
CONTROL, INFLUENCE = 50.0, 20.0
USABLE = {"verified", "verified_total"}
NOT_HEADS = {"institution", "nominee"}          # old groups.py: funds and unidentified nominees head no group


class LookThroughLoop(RuntimeError):
    """Cross-holdings form a closed loop (spectral radius of W >= 1): the old code stopped here too."""


# --- the market as at a session (old load_market) ---------------------------------------------------------------

@dataclass
class Market:
    session: str
    names: dict[str, str]                       # code -> company name
    issued: dict[str, float]                    # symbol -> shares issued
    mcap: dict[str, float]                      # symbol -> market capitalisation (LKR)
    listed: dict[str, str] = field(default_factory=dict)   # name key -> code

    def value(self, symbol: str, shares: float) -> float | None:
        if self.issued.get(symbol) and self.mcap.get(symbol) is not None:
            return shares * self.mcap[symbol] / self.issued[symbol]
        return None

    def company_cap(self, code: str) -> float:
        return sum(self.mcap.get(code + s, 0.0) or 0.0 for s in EQUITY_SUFFIXES)


class MarketData:
    """The CSE facts the old load_market read from its session folders, by session:
    security_lists: session -> [{symbol, name}]; info: session -> [(symbol, quantity_issued, market_cap)] (the
    company summaries); trades: session -> [(symbol, market_cap, close)] (the trade summary's rows)."""

    def __init__(self, security_lists: dict[dt.date, list[dict]], info: dict[dt.date, list[tuple]],
                 trades: dict[dt.date, list[tuple]]):
        self.security_lists, self.info, self.trades = security_lists, info, trades
        self.dates = sorted(set(security_lists) | set(info) | set(trades))

    @property
    def sessions(self) -> list[dt.date]:
        """Sessions with a trade summary: the days the old daily job could have run."""
        return sorted(self.trades)

    def market(self, session: dt.date) -> Market:
        """As the old load_market saw its folders on that day: every session up to it, later sessions overwrite
        earlier ones, and within a session the trade summary overwrites the company summaries."""
        issued: dict[str, float] = {}
        mcap: dict[str, float] = {}
        for d in self.dates:
            if d > session:
                break
            for symbol, quantity, cap in self.info.get(d, []):
                if quantity:
                    issued[symbol] = float(quantity)
                if cap is not None:
                    mcap[symbol] = float(cap)
            for symbol, cap, close in self.trades.get(d, []):
                if cap:
                    mcap[symbol] = float(cap)
                    # the CSE's market cap is shares issued x close, so the trade summary keeps the share count
                    # current for companies whose company summary was fetched only once
                    if close:
                        issued[symbol] = float(round(cap / close))
        lists = [d for d in self.security_lists if d <= session]
        secs = self.security_lists[max(lists)] if lists else []
        equities = [s for s in secs if s["symbol"].endswith(EQUITY_SUFFIXES)]
        m = Market(max(d for d in self.trades if d <= session).isoformat(),
                   {s["symbol"].split(".")[0]: s["name"] for s in sorted(equities, key=lambda s: s["symbol"])},
                   issued, mcap)
        m.listed = names.listed_index(equities)
        return m


# --- reports and their parsed tables ----------------------------------------------------------------------------

@dataclass(frozen=True)
class Report:
    """One row of the report index, as the old reports.csv held it (text: '' for a date it lacked)."""
    id: str
    code: str
    symbol: str
    kind: str
    title: str
    period_date: str
    uploaded_utc: str
    url: str
    status: str
    text_sha256: str | None


class TableCache:
    """find_tables() once per report; each use gets a deep copy, because validation changes a table in place."""

    def __init__(self, text_of):
        self._text_of = text_of            # text_sha256 -> the report's text
        self._tables: dict[str, list[parse.Table]] = {}
        self._chosen: dict[tuple, dict[str, parse.Table]] = {}

    def tables(self, rep: Report) -> list[parse.Table]:
        if rep.id not in self._tables:
            self._tables[rep.id] = parse.find_tables(self._text_of(rep.text_sha256))
        return copy.deepcopy(self._tables[rep.id])

    def choose(self, rep: Report, market: Market) -> dict[str, parse.Table]:
        """choose_tables for this report with the session's share counts. The result depends only on the report
        and the two counts, so it is kept for the next session with the same counts (callers must not change it)."""
        key = (rep.id, market.issued.get(rep.code + ".N0000"), market.issued.get(rep.code + ".X0000"))
        if key not in self._chosen:
            self._chosen[key] = choose_tables(self.tables(rep), rep.code, market)
        return self._chosen[key]


def choose_tables(tables: list[parse.Table], code: str, market: Market) -> dict[str, parse.Table]:
    """Best table per class. A table whose heading names the wrong class is relabelled when its implied share total
    matches the other class's share count (and not its own). Old choose_tables, given the parsed tables."""
    issued = {"N": market.issued.get(code + ".N0000"), "X": market.issued.get(code + ".X0000")}
    for t in tables:
        other = "X" if t.share_class == "N" else "N"
        if issued.get(other):
            parse.validate_table(t, issued.get(t.share_class))
            if t.status != "verified":
                probe = parse.validate_table(parse.Table(other, t.heading, t.line, t.rows,
                                                         stated_total_pct=t.stated_total_pct), issued[other])
                if probe.status == "verified":
                    t.share_class = other
            t.status, t.note = "unverified", ""
    return parse.best_tables(tables, issued)


def latest_reports(reports: list[Report], asof: str | None = None) -> dict[str, Report]:
    """code -> the newest report (by period, then upload time). Periods after `asof` (the session) are CSE typos,
    e.g. a 2030-09-30, and never count as the newest."""
    out: dict[str, Report] = {}
    for r in reports:
        if asof and r.period_date > asof:
            continue
        cur = out.get(r.code)
        if cur is None or (r.period_date, r.uploaded_utc) > (cur.period_date, cur.uploaded_utc):
            out[r.code] = r
    return out


# --- the owner's confirmed parents of unlisted holders (old parents.load) ---------------------------------------

@dataclass(frozen=True)
class Link:
    holder: str          # the unlisted holder, as the tracker names it
    owner: str           # who owns or controls it
    owner_type: str
    pct: float | None    # % of the holder owned; None = control stated without a percentage
    source: str
    quote: str


def load_links(data: dict | None) -> dict[str, Link]:
    """holder key -> confirmed link, from the confirmations' `parents` section. The old checks: every link needs an
    owner, its source and the quote; a percentage must be in (0, 100]."""
    out = {}
    for holder, spec in ((data or {}).get("parents") or {}).items():
        spec = spec or {}
        for req in ("owner", "source", "quote"):
            if not spec.get(req):
                raise ValueError(f"ownership parents: '{holder}' needs '{req}'")
        pct = spec.get("pct")
        if pct is not None and not 0 < float(pct) <= 100:
            raise ValueError(f"ownership parents: '{holder}' pct must be in (0, 100]")
        out[names.key_of(holder)] = Link(holder, spec["owner"], spec.get("owner_type") or "",
                                         None if pct is None else float(pct), spec["source"], spec["quote"])
    return out


# --- one session: the old build() -------------------------------------------------------------------------------

class Resolver:
    """entity_for() with a memory: the same name, listed index and aliases always resolve the same way."""

    def __init__(self, aliases: dict):
        self.aliases = aliases
        self._memo: dict[str, dict] = {}

    def entity(self, name_as_filed: str, market: Market) -> names.Entity:
        sig = getattr(market, "_names_sig", None)
        if sig is None:
            sig = hashlib.sha256(json.dumps([sorted(market.listed.items()),
                                             sorted(market.names.items())]).encode()).hexdigest()
            market._names_sig = sig
        memo = self._memo.setdefault(sig, {})
        if name_as_filed not in memo:
            memo[name_as_filed] = entity_for(name_as_filed, market, self.aliases)
        return memo[name_as_filed]


def entity_for(name_as_filed: str, market: Market, aliases: dict) -> names.Entity:
    e = names.resolve(name_as_filed, market.listed, aliases)
    if e.type == "listed" and e.symbol:
        return names.Entity("LISTED:" + e.symbol, market.names.get(e.symbol, e.name), "listed", e.symbol, e.via, e.rule)
    return e


def build(market: Market, reports: list[Report], cache: TableCache, resolver: Resolver,
          parents: dict[str, Link], *, all_holdings: bool = True) -> dict:
    """The old build() at this market's session. `reports` are those known on that day. all_holdings=False parses
    only each company's latest report (enough for the company view; the old code parsed every report so that its
    holdings file covered every period)."""
    latest = latest_reports(reports, market.session)
    all_reports = [r for r in reports if r.period_date <= market.session]

    holdings: list[dict] = []
    companies: dict[str, dict] = {}
    for code in sorted(market.names):
        rep = latest.get(code)
        companies[code] = c = {k: "" for k in COMPANY_COLS}
        c.update(code=code, name=market.names[code], market_cap=market.company_cap(code),
                 report_status="no_report" if rep is None else rep.status)
        if rep:
            c.update(report_id=rep.id, kind=rep.kind, period_date=rep.period_date, source_url=rep.url)
    latest_ids = {r.id for r in latest.values()}
    for rep in sorted(all_reports, key=lambda r: (r.code, r.period_date, r.id)):
        if rep.status != "ok" or rep.code not in market.names:
            continue
        if not all_holdings and rep.id not in latest_ids:
            continue
        best = cache.choose(rep, market)
        if latest[rep.code].id == rep.id:
            c = companies[rep.code]
            c["report_status"] = "no_table" if not best else "ok"
            for cls in ("N", "X"):
                if cls in best:
                    c[f"status_{cls}"], c[f"note_{cls}"] = best[cls].status, best[cls].note
            c["rows"] = sum(len(t.rows) for t in best.values())
        for cls, t in best.items():
            sym = f"{rep.code}.{cls}0000"
            for r in t.rows:
                e = resolver.entity(r["name"], market)
                holdings.append({"report_id": rep.id, "period_date": rep.period_date, "code": rep.code,
                                 "symbol": sym, "class": cls, "rank": r["rank"], "name_as_filed": r["name"],
                                 "shares": r["shares"], "pct": r["pct"],
                                 "fraction": r["shares"] / t.period_total if t.period_total else None,
                                 "owner_key": e.key, "owner_name": e.name,
                                 "owner_type": e.type, "owner_symbol": e.symbol, "via": e.via, "rule": e.rule,
                                 "table_status": t.status, "source_url": rep.url})
    current = [h for h in holdings if h["report_id"] in latest_ids and h["table_status"] in USABLE]
    links = {}
    for hk, link in parents.items():
        e = resolver.entity(link.owner, market)
        links[hk] = {"owner_key": e.key, "owner_name": e.name, "owner_type": link.owner_type or e.type,
                     "owner_symbol": e.symbol, "pct": link.pct, "source": link.source, "quote": link.quote,
                     "holder": link.holder}
    owners, graph = analyse(current, market, companies, links)
    return {"market": market, "holdings": holdings, "companies": companies, "owners": owners, "graph": graph,
            "current": current, "links": links}


def analyse(rows: list[dict], market: Market, companies: dict[str, dict],
            links: dict[str, dict] | None = None) -> tuple[dict[str, dict], dict]:
    """Direct value, economic look-through F = D (I - W)^-1, and control, as the old analyse().
    `links`: confirmed owners of unlisted holders, keyed by the holder's entity key. A link with a percentage passes
    that share of the holder's look-through value to its owner; any link with no percentage or > 50 % also passes
    the holder's votes (control)."""
    links = links or {}
    covered = sorted({r["code"] for r in rows})
    # Direct holdings, aggregated per (owner, company); value at the session's market price.
    direct: dict[tuple[str, str], float] = defaultdict(float)
    votes: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    info: dict[str, dict] = {}
    filed: dict[str, Counter] = defaultdict(Counter)
    treasury = []
    for r in rows:
        k = r["owner_key"]
        if r["owner_symbol"] == r["code"]:
            treasury.append((r["code"], r["name_as_filed"]))      # a company in its own register
            continue
        if r["fraction"] is not None and market.mcap.get(r["symbol"]):
            direct[(k, r["code"])] += r["fraction"] * market.mcap[r["symbol"]]
        if r["class"] == "N":
            votes[r["code"]][k] += float(r["pct"])
        info.setdefault(k, {"key": k, "name": r["owner_name"], "type": r["owner_type"], "symbol": r["owner_symbol"]})
        filed[k][r["name_as_filed"]] += 1

    # Economic look-through. Listed holders whose own register is covered pass value through.
    caps = {c: market.company_cap(c) for c in covered}
    through = [c for c in covered if caps[c] > 0]
    idx = {c: i for i, c in enumerate(through)}
    terminal = sorted({k for (k, _c) in direct if not (k.startswith("LISTED:") and k[7:] in idx)})
    tidx = {k: i for i, k in enumerate(terminal)}
    W = np.zeros((len(through), len(through)))
    D = np.zeros((len(terminal), len(through)))
    for (k, c), v in direct.items():
        if c not in idx:
            continue
        frac = v / caps[c]
        if k.startswith("LISTED:") and k[7:] in idx:
            W[idx[k[7:]], idx[c]] += frac
        else:
            D[tidx[k], idx[c]] += frac
    if len(through) and max(abs(np.linalg.eigvals(W))) >= 1:
        raise LookThroughLoop("ownership look-through: cross-holdings form a closed loop (spectral radius >= 1)")
    F = D @ np.linalg.inv(np.eye(len(through)) - W) if len(through) else D
    V = np.array([caps[c] for c in through])
    look0 = dict(zip(terminal, F @ V if len(through) else np.zeros(len(terminal))))
    # Confirmed owners of unlisted holders: pass the stated share of value up the chain.
    look: dict[str, float] = defaultdict(float)

    def push(k: str, val: float, depth: int = 0) -> None:
        link = links.get(k)
        if link and link["pct"] and depth < 20:
            share = val * link["pct"] / 100
            look[k] += val - share
            push(link["owner_key"], share, depth + 1)
        else:
            look[k] += val
    for k, v in look0.items():
        push(k, float(v))
    for link in links.values():
        info.setdefault(link["owner_key"], {"key": link["owner_key"], "name": link["owner_name"],
                                            "type": link["owner_type"], "symbol": link["owner_symbol"]})
    attributed = F.sum(axis=0) if len(through) else np.zeros(0)

    # Control: votes summed by group, iterated to a fixed point.
    ctrl = control(votes, info, links)
    for c, x in ctrl.items():
        comp = companies[c]
        comp.update(controller_key=x["root"], controller_name=info.get(x["root"], {}).get("name", x["root"]),
                    controller_type=info.get(x["root"], {}).get("type", ""), control_pct=round(x["pct"], 4),
                    control_level=x["level"], chain=" <- ".join(x["chain"]))
    for c in covered:
        companies[c]["top_holders_pct_voting"] = round(sum(votes[c].values()), 4) if c in votes else ""

    owners: dict[str, dict] = {k: {**i, "holdings": 0, "direct_value": 0.0, "lookthrough_value": 0.0,
                                   "companies_controlled": 0, "controlled_market_cap": 0.0, "companies_influenced": 0}
                               for k, i in info.items()}
    held: dict[str, set] = defaultdict(set)
    for r in rows:
        held[r["owner_key"]].add(r["code"])
    for k in info:
        owners[k]["holdings"] = len(held[k])
    for (k, c), v in direct.items():
        owners[k]["direct_value"] += v
    for k, v in look.items():
        owners[k]["lookthrough_value"] = float(v)
    for c, x in ctrl.items():
        o = owners.get(x["root"])
        if o is None:
            continue
        if x["level"] == "controlled":
            o["companies_controlled"] += 1
            o["controlled_market_cap"] += caps.get(c, 0.0)
        else:
            o["companies_influenced"] += 1
    for k, o in owners.items():
        o["names_as_filed"] = " | ".join(n for n, _ in filed[k].most_common(5))
    total_cap = sum(market.company_cap(c) for c in market.names)
    graph = {"covered": covered, "covered_cap": float(sum(caps.values())), "total_cap": float(total_cap),
             "attributed_value": float(attributed @ V) if len(through) else 0.0,
             "listed_passthrough": int((W.sum(axis=1) > 0).sum()), "treasury": treasury, "control": ctrl,
             "votes": votes, "info": info}
    return owners, graph


def control(votes: dict[str, dict[str, float]], info: dict[str, dict],
            links: dict[str, dict] | None = None) -> dict[str, dict]:
    """company -> {root, pct, level, chain}. A holder's votes count for the group it belongs to: a listed holder
    that is itself > 50 % controlled votes with its controller's group, and an unlisted holder with a confirmed
    controlling owner votes with it."""
    ctrl: dict[str, dict] = {}
    links = links or {}

    def root(k: str, seen: frozenset = frozenset()) -> str:
        return block_root(k, ctrl, links, seen)

    for _ in range(50):
        new = {}
        for c, hv in votes.items():
            blocks: dict[str, float] = defaultdict(float)
            members: dict[str, list] = defaultdict(list)
            for h, p in hv.items():
                if info.get(h, {}).get("type") == "nominee":
                    continue
                r = root(h, frozenset({"LISTED:" + c}))
                if r == "LISTED:" + c:
                    continue
                blocks[r] += p
                members[r].append((p, h))
            if not blocks:
                continue
            r, p = max(blocks.items(), key=lambda kv: (kv[1], kv[0]))
            if p < INFLUENCE:
                continue
            new[c] = {"root": r, "pct": p, "level": "controlled" if p > CONTROL else "influence",
                      "members": sorted(members[r], reverse=True)}
        if {c: (x["root"], x["level"]) for c, x in new.items()} == {c: (x["root"], x["level"]) for c, x in ctrl.items()}:
            ctrl = new
            break
        ctrl = new
    for c, x in ctrl.items():                  # readable chain: company <- largest member <- ... <- root
        chain, cur, seen = [c], x, {c}
        while cur:
            top = cur["members"][0][1]
            chain.append(info.get(top, {}).get("name", top) if not top.startswith("LISTED:") else top[7:])
            nxt = top[7:] if top.startswith("LISTED:") else None
            cur = ctrl.get(nxt) if nxt and nxt not in seen and ctrl.get(nxt, {}).get("level") == "controlled" else None
            if nxt:
                seen.add(nxt)
        root_name = info.get(x["root"], {}).get("name", x["root"]) if not x["root"].startswith("LISTED:") else x["root"][7:]
        if chain[-1] != root_name:
            chain.append(root_name)
        x["chain"] = chain
    return ctrl


def block_root(k: str, ctrl: dict[str, dict], links: dict[str, dict], seen: frozenset = frozenset()) -> str:
    """The holder whose block a holder's votes count in (old control()'s inner root())."""
    if not k.startswith("LISTED:"):
        link = links.get(k)
        if link and (link["pct"] is None or link["pct"] > 50) and link["owner_key"] not in seen \
                and link["owner_key"] != k:
            return block_root(link["owner_key"], ctrl, links, seen | {k})
        return k
    x = ctrl.get(k[7:])
    if x and x["level"] == "controlled" and x["root"] not in seen and x["root"] != k:
        return block_root(x["root"], ctrl, links, seen | {k})
    return k


# --- ownership groups (old groups.py, on the in-memory company rows instead of companies.csv) -------------------

def chains(rows: dict[str, dict]) -> dict[str, list[str]]:
    """company code -> [code, next holder key, ...]; the last element is the group head."""
    out: dict[str, list[str]] = {}
    for code in rows:
        path, cur = [code], code
        while True:
            r = rows.get(cur)
            if (not r or r["control_level"] not in ("controlled", "influence")
                    or r["controller_type"] in NOT_HEADS or not r["controller_key"]):
                break
            k = r["controller_key"]
            if k.startswith("LISTED:"):
                nxt = k[7:]
                if nxt in path:
                    break                      # cross-holding loop: stop at the last company reached
                path.append(nxt)
                cur = nxt
                continue
            path.append(k)
            break
        out[code] = path
    return out


def group_of(rows: dict[str, dict]) -> tuple[dict[str, str], dict[str, str], dict[str, list[str]]]:
    """(company code -> group key, group key -> display name, company code -> its chain)."""
    labels_by_key: dict[str, str] = {}
    for r in rows.values():
        if r["controller_key"]:
            labels_by_key.setdefault(r["controller_key"], r["controller_name"])
    groups, labels = {}, {}
    paths = chains(rows)
    for code, path in paths.items():
        head = path[-1]
        key = head if head not in rows else "LISTED:" + head
        groups[code] = key
        labels[key] = rows[head]["name"] if head in rows else labels_by_key.get(head, head)
    return groups, labels, paths


def owner_rows(owners: dict[str, dict]) -> list[dict]:
    """The old owners.csv: largest direct value first."""
    return sorted(owners.values(), key=lambda o: -o["direct_value"])
