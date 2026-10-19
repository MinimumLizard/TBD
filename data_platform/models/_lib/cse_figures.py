"""Company figures read from the interim reports, and the ratios built on them (audit C21, C22).

A port of MinimumLizard/CSE@e05c6f3 cse/fundamentals.py. Every rule is the old one (its docstring, kept below, is
the definition); the plumbing differs:

  * the facts arrive as rows (report index and text, share counts, prices, the financial year end, the corporate
    actions in use) instead of being read from the old repo's folders and CSV files;
  * `extract` is split in two: `scan` finds the labelled lines of a report once (that does not depend on the share
    count) and `match` reconciles them under one share count. Together they return exactly what the old extract()
    returned, without re-reading a report for every candidate count and every session;
  * the old code read the shareholder tables back from holdings.csv, whose numbers its CSV writer had rounded to 8
    decimals; `report_shares` rounds the holding fraction the same way, so the share count it gives is the old one
    to the last digit.

The old definition:

Every figure must reconcile inside its own report or it isn't used:
- EPS (basic, first column): EPS x shares must equal the profit line in the same column (profit attributable to
  owners, or profit for the period) in Rs, Rs '000 or Rs mn, within 2 % + the rounding of a 2-decimal EPS. The
  match also fixes the statement's unit.
- Net assets per share (first column): NAV/share x shares must equal equity attributable to owners (or total
  equity) the same way. Group figures are preferred over company-only ones.
- Shares are the report's own period-end count (from its verified shareholder table: shares / fraction), else each
  count the CSE has reported for the company, newest first.

Trailing-12-month EPS. Reports differ in what their first column holds: the quarter, or the year to date. It is
taken from the column headers above the EPS line ("Quarter ended", "03 months to" -> quarter; "Six months", "Nine
months", "Year ended" -> year to date; "Period ended" alone is unknown unless the report is the first quarter of the
financial year, where both agree). The financial year end comes from the company profile (finYearEnd 1 = 31 March,
2 = 31 December). Quarterly EPS is the quarter column, or year-to-date minus the previous quarter's year-to-date
within the same financial year. TTM = the last four consecutive quarters, only when all four are known. Nothing is
estimated or annualised.

Outputs per company: price (latest close), NAV/share and P/B, TTM EPS and P/E, ROE (TTM EPS / NAV per share),
trailing dividends per share (confirmed corporate actions, last 365 days) and dividend yield. Per-share figures are
the reconciled totals (TTM profit, latest equity) divided by today's issued shares, so P/E = market cap / TTM profit
and P/B = market cap / equity, the same construction as the CSE's market PER and PBV, and safe across splits and
scrip issues. The report's own EPS and NAV/share stay in the per-report rows.
"""
from __future__ import annotations

import datetime as dt
import math
import re
from collections import defaultdict
from dataclasses import dataclass

from . import cse_ownership as own

TOL = 0.02
NUMTOK = re.compile(r"\(\s*-?[\d,]*\.?\d+\s*\)|-?\d[\d,]*\.?\d*")
EPS = re.compile(r"(?:basic\s+(?:and\s+diluted\s+)?)?(?:earnings?|profit|\(loss\)|loss)\s*(?:/\s*\(?(?:loss|profit)\)?\s*)?"
                 r"per\s+(?:ordinary\s+)?share|basic\s+eps\b", re.I)
NAV = re.compile(r"net\s+assets?\s+(?:value\s+)?per\s+(?:ordinary\s+)?share", re.I)
PROFIT = re.compile(r"(?:equity\s+holders|owners|shareholders)\s+of\s+the\s+(?:parent|company|bank|holding)|"
                    r"(?:net\s+)?(?:profit|\(loss\)|loss)\s*(?:/\s*\(?(?:loss|profit)\)?)?\s+(?:after\s+tax\s+)?"
                    r"for\s+the\s+(?:period|year|quarter)", re.I)
ATTRIB = re.compile(r"equity\s+holders|owners|shareholders", re.I)
EQUITY = re.compile(r"total\s+equity\s+attributable|equity\s+attributable\s+to\s+(?:the\s+)?(?:equity\s+holders|owners|"
                    r"shareholders)|^\s*total\s+(?:shareholders'?\s*)?equity\b", re.I)
QUARTER_HDR = re.compile(r"\bquarter\b|\bthree\s+months\b|\b0?3\s*months\b", re.I)
CUM_HDR = re.compile(r"\b(?:six|nine|twelve|0?6|0?9|12)\s*months\b|\byear\s+ended\b|\bhalf\s+year\b|\bcumulative\b", re.I)
UNITS = (1.0, 1e3, 1e6)
FYE_LABEL = {"1": "31 Mar", "2": "31 Dec"}
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def numbers(text: str) -> list[float]:
    """Numbers on a statement line: '(1,234)' is negative; years like 2026 in headers are dropped by callers."""
    out = []
    for t in NUMTOK.findall(text):
        neg = t.strip().startswith("(") or t.strip().startswith("-")
        v = t.strip("() -").replace(",", "")
        if not v or v == ".":
            continue
        try:
            x = float(v)
        except ValueError:
            continue
        out.append(-x if neg else x)
    return out


def _labelled(lines: list[str], pat: re.Pattern, limit: int = 40) -> list[tuple[int, list[float], str]]:
    """(line index, numbers after the label, label line) for each line matching `pat`; when the numbers sit on the
    next line (labels wrapped above them), take those."""
    out = []
    for i, ln in enumerate(lines):
        m = pat.search(ln)
        if not m:
            continue
        v = numbers(ln[m.end():])
        if len(v) == 1 and v[0].is_integer() and 0 < v[0] < 100 and not re.search(r"\d\.\d", ln[m.end():]):
            v = []                                         # 'Earnings per share   9': a note reference
        if not v and i + 1 < len(lines) and not re.search(r"[A-Za-z]{4,}", lines[i + 1]):
            v = numbers(lines[i + 1])
        if not v:
            # 'Earnings per share' as a heading, numbers on a following '- basic' / 'Basic (Rs.)' line; only numbers
            # to the right of that label count (some layouts print other columns left of it)
            for k in range(i + 1, min(len(lines), i + 4)):
                b = re.search(r"^\s*[-–•]?\s*(?:\(?[a-z]\)\s*)?basic\b[^\d(\-]*", lines[k], re.I)
                if b:
                    v = numbers(lines[k][b.end():])
                    break
        v = [x for x in v if not (x.is_integer() and 1990 <= x <= 2040)]       # stray year headers
        if v:
            out.append((i, v, re.sub(r"\s{2,}", "  ", ln.strip())))
        if len(out) >= limit:
            break
    return out


def _tol(per_share: float) -> float:
    """2 % plus the rounding of the printed per-share figure (half a unit of its last decimal place)."""
    txt = f"{abs(per_share):.6f}".rstrip("0").rstrip(".")
    dp = len(txt.split(".")[1]) if "." in txt else 0
    return min(0.15, TOL + 0.5 * 10 ** -max(dp, 2) / max(abs(per_share), 1e-9))


def _reconcile(per_share: float, total: float, shares: float) -> float | None:
    """The unit (1, 1e3, 1e6) under which per_share x shares == total, or None."""
    if not per_share or not total or not shares or (per_share > 0) != (total > 0):
        return None
    for u in UNITS:
        r = per_share * shares / (total * u)
        if abs(r - 1) <= _tol(per_share):
            return u
    return None


def header_class(lines: list[str], i: int) -> str:
    """'quarter' / 'ytd' / 'unknown' for the first numeric column: the nearest line above (within 80) that names a
    period length decides; a bare 'period ended' header line is skipped over."""
    for k in range(i - 1, max(-1, i - 80), -1):
        ln = lines[k]
        q, c = QUARTER_HDR.search(ln), CUM_HDR.search(ln)
        if q and c:
            return "quarter" if q.start() < c.start() else "ytd"
        if q:
            return "quarter"
        if c:
            return "ytd"
    return "unknown"


@dataclass(frozen=True)
class Scan:
    """What the old extract() found in a report before trying a share count: the EPS lines (each with its profit
    candidates in the order tried, and its column class), the NAV lines in the order tried, and the equity lines."""
    eps: tuple                       # ((eps, label, class, ((profit, profit label), ...)), ...)
    navs: tuple                      # ((nav, label), ...)
    equities: tuple                  # ((equity, label), ...)


def scan(text: str) -> Scan:
    lines = text.splitlines()
    profits = _labelled(lines, PROFIT, limit=80)
    eps = []
    for i, ev, label in _labelled(lines, EPS, limit=6):
        above = [p for p in profits if i - 60 <= p[0] < i]
        # attributable-to-owners first (EPS is on that), then the nearest profit line
        above.sort(key=lambda p: (not ATTRIB.search(p[2]), i - p[0]))
        eps.append((ev[0], label, header_class(lines, i), tuple((pv[0], plabel) for _j, pv, plabel in above)))
    navs = _labelled(lines, NAV, limit=8)
    navs.sort(key=lambda n: (not re.search(r"group|consolidated", n[2], re.I), bool(re.search(r"\bcompany\b", n[2], re.I)), n[0]))
    equities = _labelled(lines, EQUITY, limit=20)
    return Scan(tuple(eps), tuple((nv[0], label) for _i, nv, label in navs),
                tuple((qv[0], qlabel) for _j, qv, qlabel in equities))


def match(s: Scan, shares: float) -> dict:
    """The old extract(text, shares), from the scan."""
    out = {"eps": None, "eps_line": "", "profit": None, "unit": None, "eps_class": "", "nav": None, "nav_line": "",
           "equity": None, "nav_unit": None}
    for ev, label, cls, above in s.eps:
        for pv, plabel in above:
            u = _reconcile(ev, pv, shares)
            if u:
                out.update(eps=ev, eps_line=label, profit=pv * u, unit=u, eps_class=cls, profit_line=plabel)
                break
        if out["eps"] is not None:
            break
    for nv, label in s.navs:
        for qv, qlabel in s.equities:
            u = _reconcile(nv, qv, shares)
            if u:
                out.update(nav=nv, nav_line=label, equity=qv * u, nav_unit=u, equity_line=qlabel)
                break
        if out["nav"] is not None:
            break
    return out


def extract(text: str, shares: float) -> dict:
    return match(scan(text), shares)


def fiscal_quarter(period: str, fye: str) -> tuple[int, int] | None:
    """(fiscal year label, quarter 1-4) for a quarter-end date; fye '1' = 31 March, '2' = 31 December."""
    d = dt.date.fromisoformat(period)
    if (d.month, d.day) not in ((3, 31), (6, 30), (9, 30), (12, 31)):
        return None
    if fye == "2":
        return d.year, (d.month - 1) // 3 + 1
    q = {6: 1, 9: 2, 12: 3, 3: 4}[d.month]
    return (d.year + 1 if d.month >= 6 else d.year), q


def quarter_end(title: str, period: str) -> str:
    """The quarter a report covers: the CSE's period date when it is a quarter end; otherwise the date in the title
    ('...Quarter ended 30th June 2026', '30/06/2025', '30.06.2025'), else the last quarter end at least 15 days
    before the CSE's date (some records carry the filing date)."""
    p = dt.date.fromisoformat(period)
    if (p.month, p.day) in ((3, 31), (6, 30), (9, 30), (12, 31)):
        return period
    n = re.search(r"\b(\d{1,2})[./-](\d{1,2})[./-](20\d\d)\b", title or "")
    if n:
        try:
            d = dt.date(int(n.group(3)), int(n.group(2)), int(n.group(1)))
            if (d.month, d.day) in ((3, 31), (6, 30), (9, 30), (12, 31)):
                return d.isoformat()
        except ValueError:
            pass
    m = re.search(r"(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]{3,9})\.?,?\s+(20\d\d)", title or "")
    if m and m.group(2)[:3].lower() in MONTHS:
        try:
            d = dt.date(int(m.group(3)), MONTHS[m.group(2)[:3].lower()], int(m.group(1)))
            if (d.month, d.day) in ((3, 31), (6, 30), (9, 30), (12, 31)):
                return d.isoformat()
        except ValueError:
            pass
    d = dt.date.fromisoformat(period) - dt.timedelta(days=15)
    for y, mo, da in sorted(((y, mo, da) for y in (d.year - 1, d.year) for mo, da in ((3, 31), (6, 30), (9, 30), (12, 31))),
                            reverse=True):
        if dt.date(y, mo, da) <= d:
            return dt.date(y, mo, da).isoformat()
    return period


def ttm(rows: list[dict], fye: str) -> tuple[float | None, str, str]:
    """(trailing-12-month profit attributable to owners, in Rs; the quarter it ends; how) from one company's
    verified report rows. Built from profit, not EPS, so a share split or bonus issue during the year doesn't mix
    old and new per-share figures."""
    by_q: dict[tuple[int, int], dict] = {}
    for r in rows:
        fq = fiscal_quarter(r["period_date"], fye)
        if fq and r["eps_status"] == "verified" and r["profit"] not in (None, ""):
            by_q[fq] = r
    quarterly: dict[tuple[int, int], float] = {}
    ytd: dict[tuple[int, int], float] = {}
    for (fy, q), r in sorted(by_q.items()):
        v, cls = float(r["profit"]), r["eps_class"]
        if q == 1:
            quarterly[(fy, q)] = ytd[(fy, q)] = v
        elif cls == "quarter":
            quarterly[(fy, q)] = v
        elif cls == "ytd":
            ytd[(fy, q)] = v
    for _ in range(4):                                  # year-to-date <-> quarter, within a financial year
        for (fy, q), v in list(ytd.items()):
            if q > 1 and (fy, q - 1) in ytd and (fy, q) not in quarterly:
                quarterly[(fy, q)] = v - ytd[(fy, q - 1)]
        for (fy, q), v in list(quarterly.items()):
            if q > 1 and (fy, q - 1) in ytd and (fy, q) not in ytd:
                ytd[(fy, q)] = ytd[(fy, q - 1)] + v
    if not quarterly:
        return None, "", ""
    last = max(quarterly)
    seq, (fy, q) = [], last
    for _ in range(4):
        if (fy, q) not in quarterly:
            return None, "", f"quarter {q} of FY{fy} not known"
        seq.append(quarterly[(fy, q)])
        fy, q = (fy, q - 1) if q > 1 else (fy - 1, 4)
    return sum(seq), by_q[last]["period_date"], "sum of 4 quarters' profit"


# --- the inputs, as the old build() assembled them -------------------------------------------------------------

def csv_float(v: float) -> float:
    """A number as the old CSV writer stored it and its reader read it back (cse/storage.py fmt: whole numbers
    exactly, others rounded to 8 decimals)."""
    if v.is_integer() and abs(v) < 1e15:
        return float(int(v))
    return float(repr(round(v, 8)))


def report_shares(market: own.Market, reports: list[own.Report], cache: own.TableCache) -> dict[str, float]:
    """report id -> period-end shares (N + X) from its verified shareholder tables (shares / fraction), as the old
    report_shares() read them from the holdings file the ownership step had just written for the same session."""
    per: dict[str, dict[str, float]] = defaultdict(dict)
    for rep in sorted(reports, key=lambda r: (r.code, r.period_date, r.id)):
        if rep.status != "ok" or rep.code not in market.names or rep.period_date > market.session:
            continue
        for cls, t in cache.choose(rep, market).items():
            if t.status not in own.USABLE or not t.period_total:
                continue
            for r in t.rows:
                fraction = csv_float(r["shares"] / t.period_total)
                if fraction > 0.005:
                    per[rep.id].setdefault(cls, csv_float(r["shares"]) / fraction)
    return {rid: sum(v.values()) for rid, v in per.items()}


class ShareCounts:
    """code -> every distinct shares-issued total (N + X) the CSE reported, newest first (old share_counts): per
    session, the trade summary's market cap / close, then the company summary's quantity issued."""

    def __init__(self, data: own.MarketData):
        self.data = data

    def at(self, session: dt.date) -> dict[str, list[float]]:
        issued: dict[str, float] = {}
        seen: dict[str, list[float]] = defaultdict(list)
        for d in self.data.dates:
            if d > session:
                break
            for symbol, cap, close in self.data.trades.get(d, []):
                if cap and close:
                    issued[symbol] = float(round(cap / close))
            for symbol, quantity, _cap in self.data.info.get(d, []):
                if quantity:
                    issued[symbol] = float(quantity)
            for code in {s.split(".")[0] for s in issued}:
                tot = (issued.get(code + ".N0000") or 0) + (issued.get(code + ".X0000") or 0)
                if tot and tot not in seen[code]:
                    seen[code].append(tot)
        return {c: v[::-1] for c, v in seen.items()}


class Extractor:
    """match() results, remembered per (report, share count)."""

    def __init__(self, text_of):
        self._text_of = text_of
        self._scans: dict[str, Scan] = {}
        self._matches: dict[tuple[str, float], dict] = {}

    def __call__(self, rep: own.Report, shares: float) -> dict:
        key = (rep.id, shares)
        if key not in self._matches:
            if rep.id not in self._scans:
                self._scans[rep.id] = scan(self._text_of(rep.text_sha256))
            self._matches[key] = match(self._scans[rep.id], shares)
        return self._matches[key]


def report_rows(market: own.Market, reports: list[own.Report], shares_by_rep: dict[str, float],
                counts: dict[str, list[float]], fye: dict[str, str], extract_fn) -> list[dict]:
    """The old build()'s per-report rows (reports.csv) at this session: `reports` are those known on that day."""
    out = []
    reps = [r for r in reports if r.status == "ok" and r.period_date <= market.session]
    for r in sorted(reps, key=lambda r: (r.code, r.period_date, r.id)):
        cur = (market.issued.get(r.code + ".N0000") or 0) + (market.issued.get(r.code + ".X0000") or 0)
        # the report's own count first, then every count the CSE has reported for the company (newest first; covers
        # an unverified table, and EPS printed on a weighted count near a later one)
        cands = list(dict.fromkeys(c for c in [shares_by_rep.get(r.id)] + counts.get(r.code, []) + [cur] if c))
        tried = [(c, extract_fn(r, c)) for c in cands] or [(0.0, extract_fn(r, 0.0))]
        sh, x = next(((c, e) for c, e in tried if e["eps"] is not None), None) \
            or next(((c, e) for c, e in tried if e["nav"] is not None), tried[0])
        out.append({"report_id": r.id, "code": r.code, "period_date": quarter_end(r.title, r.period_date),
                    "fye": fye.get(r.code, ""),
                    "shares": sh, "eps": x["eps"], "eps_class": x["eps_class"],
                    "eps_status": "verified" if x["eps"] is not None else "not found",
                    "profit": x["profit"], "unit": x["unit"], "eps_line": x["eps_line"][:160],
                    "nav": x["nav"], "nav_status": "verified" if x["nav"] is not None else "not found",
                    "equity": x["equity"], "nav_line": x["nav_line"][:160], "url": r.url})
    return out


def dividends_ttm(actions: list[dict], asof: str) -> dict[str, float]:
    """Cash dividends per share with an ex-date in the 365 days to `asof` (the actions in use, as the old
    dividends_ttm took them from corporate_actions.csv through effective())."""
    start = (dt.date.fromisoformat(asof) - dt.timedelta(days=365)).isoformat()
    out: dict[str, float] = defaultdict(float)
    for a in actions:
        if a["type"] == "cash_dividend" and start < a["ex_date"] <= asof and a.get("amount_per_share"):
            out[a["symbol"]] += float(a["amount_per_share"])
    return out


def latest_rows(rows: list[dict], market: own.Market, last_close: dict[str, tuple[float, str]],
                fye: dict[str, str], divs: dict[str, float]) -> list[dict]:
    """The old latest.csv: per company, at the session's last close."""
    latest = []
    by_code: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_code[r["code"]].append(r)
    for code, crows in sorted(by_code.items()):
        sym = code + ".N0000"
        price, price_date = last_close.get(sym, (None, ""))
        navr = max((r for r in crows if r["nav_status"] == "verified"), key=lambda r: r["period_date"], default=None)
        profit, eps_to, how = ttm(crows, fye.get(code, "1"))
        # per-share figures on today's share count (the latest session's market cap / close), so that price / EPS =
        # market cap / profit and price / NAV = market cap / equity, as in the CSE's own market PER and PBV
        cur = (market.issued.get(code + ".N0000") or 0) + (market.issued.get(code + ".X0000") or 0)
        shares_now = cur or float(max(crows, key=lambda r: r["period_date"])["shares"] or 0)
        eps = profit / shares_now if profit is not None and shares_now else None
        nav = float(navr["equity"]) / shares_now if navr and shares_now else None
        d = divs.get(sym, 0.0)
        latest.append({"code": code, "price": price, "price_date": price_date,
                       "shares": shares_now, "fye": FYE_LABEL.get(fye.get(code, ""), ""),
                       "nav": nav, "nav_period": navr["period_date"] if navr else "",
                       "pb": price / nav if price and nav and nav > 0 else None,
                       "ttm_profit": profit, "ttm_eps": eps, "ttm_to": eps_to, "ttm_note": how,
                       "earnings_yield": eps / price if price and eps is not None else None,
                       "pe": price / eps if price and eps and eps / price > 0.002 else None,   # P/E above 500 is noise
                       "roe": eps / nav if eps is not None and nav and nav > 0 else None,
                       "div_ttm": d, "dy": d / price if price else None})
    return latest


def finite(v):
    return None if isinstance(v, float) and (math.isnan(v) or math.isinf(v)) else v
