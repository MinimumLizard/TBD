"""cse_dealings: directors' share dealings, one row per disclosed transaction (audit C18, the old terminal's
data/dealings/dealings.csv).

Version 1 ports MinimumLizard/CSE@e05c6f3 cse/dealings.py (parse, side_of, weekdays_between, drop_refiled) line for
line; only names and comments are reworded, and the side labels are neutral words (`purchase`, `disposal`, `other`)
where the old CSV used the two trading verbs and "other". The rules it keeps:
  * the notices are the CSE's structured records (dType "DealingsByDirectors"), one row per transaction in them;
  * the side is read from the free-text transaction type; anything that is not clearly a purchase or a disposal
    (gifts, transfers, inheritance, mixed or unrecognised wording) is `other` and never counted as either;
  * a later notice for the same company, director and account that repeats every transaction of an earlier one is
    a re-filing: the earlier notice's rows are kept but marked `superseded_by` and not counted;
  * the disclosure lag is counted in weekdays (public holidays are not removed).
Numbers are stored as the old CSV stored them: whole numbers exactly, others rounded to 8 decimal places.

What is new: the director's role is also read into a short category (`role`), so the published table needs no free
text; names and the free text as filed are kept in a separate table that is not published (METHOD.md).

Outputs: models.cse_dealing (no names) and models.cse_dealing_as_filed (names and free text; unpublished).
"""
from __future__ import annotations

import datetime as dt
import math
import re
from collections import Counter

CDN = "https://cdn.cse.lk/"
DEALING_TYPE = "DealingsByDirectors"
TYPED = "getAnnouncementById"

# The old cse/dealings.py patterns, unchanged. First match wins in side_of: OTHER, then purchase vs disposal.
PURCHASE = re.compile(r"pu?r?chas|a[cq]{1,2}ui|\bbuy|bought|subscri|allot\w*\W+rights|rights\W+(?:issue\W+)?(?:allot|subscri)",
                      re.I)
DISPOSAL = re.compile(r"\bsale\b|\bsell|\bsold|dispos", re.I)
OTHER = re.compile(r"gift|transfer|inherit|bequest|transmission|donat", re.I)
SIDES = ("purchase", "disposal", "other")


def side_of(trans_type: str) -> str:
    """The old side_of: `other` if the text names a gift, transfer, inheritance, bequest, transmission or donation;
    else `purchase` if only the purchase pattern matches, `disposal` if only the disposal pattern matches; else
    `other` (neither, or both)."""
    t = trans_type or ""
    if OTHER.search(t):
        return "other"
    p, d = bool(PURCHASE.search(t)), bool(DISPOSAL.search(t))
    return "purchase" if p and not d else "disposal" if d and not p else "other"


def parse_date(s: str | None) -> dt.date | None:
    for fmt in ("%d %b %Y", "%d %B %Y", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y"):
        try:
            return dt.datetime.strptime((s or "").strip(), fmt).date()
        except ValueError:
            continue
    return None


def weekdays_between(a: dt.date, b: dt.date) -> int:
    """Disclosure lag in weekdays (public holidays not removed). Negative when b is before a."""
    if b < a:
        return -weekdays_between(b, a)
    return sum(1 for k in range(1, (b - a).days + 1) if (a + dt.timedelta(k)).weekday() < 5)


def _num(v) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(str(v).replace(",", ""))
    except ValueError:
        return None


def _space(s) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


# --- the director's role, as a short category (new in this platform; METHOD.md) ---------------------------------

def role_of(text: str | None) -> str:
    """The role a notice's free-text "nature of directorship" states, as one category, without the free text (which
    sometimes names people). Spellings are first made uniform ("Non - Executive", "Non Executive" and
    "Non- Executive" all become "non-executive"; "Board of Directors" is ignored). Then the first rule that matches:
      several:  the text speaks of more than one director: "directors" or "executives" in the plural, two or more
                titles (Mr, Mrs, Ms, Miss, Dr), "respectively", "same directors", both an executive and a
                non-executive role, or two chair roles;
      chair:    chairman, chairperson or chair (with any other role of the same person);
      chief_executive: managing director, chief executive or CEO;
      independent_non_executive: "independent" that is not "non-independent";
      non_executive: non-executive;
      executive: executive (also misspelt "exaecutive"), finance director, director - finance;
      not_stated: anything else ("Please refer attachment", "Director", empty)."""
    t = _space(text).lower()
    t = re.sub(r"\bnon\s*-\s*|\bnon\s+(?=independent|executive)", "non-", t)
    t = t.replace("board of directors", "board")
    executive = bool(re.search(r"(?<!non-)\bexa?ecutive\b", t))
    non_executive = "non-executive" in t
    people = len(re.findall(r"\b(?:mr|mrs|ms|miss|dr)\b\.?", t))
    chairs = len(re.findall(r"\bchair(?:man|person)?\b", t))
    if (re.search(r"\bdirectors\b|\bexecutives\b", t) or people >= 2 or "respectively" in t
            or "same directors" in t or (executive and non_executive) or chairs >= 2):
        return "several"
    if chairs:
        return "chair"
    if re.search(r"\bmanaging director\b|\bchief executive\b|\bceo\b", t):
        return "chief_executive"
    if re.search(r"(?<!non-)\bindependent\b|\bindependant\b", t) and not executive:
        return "independent_non_executive"
    if non_executive:
        return "non_executive"
    if executive or re.search(r"\bdirector\s*-?\s*finance\b|\bfinance director\b", t):
        return "executive"
    return "not_stated"
    t = re.sub(r"non\s*-\s*", "non-", t)
    t = re.sub(r"non\s+(independent|executive)", r"non-\1", t)
    people = len(re.findall(r"\b(?:mr|mrs|ms|miss|dr)\b\.?", t))
    roles = len(re.findall(r"(?<!non-)\bexecutive\b|\bnon-executive\b|\bchair(?:man|person)?\b|\bmanaging director\b",
                           t))
    if (re.search(r"\bdirectors\b", t) or people >= 2 or "respectively" in t or "same directors" in t
            or (roles >= 2 and re.search(r",\s*(?:executive|non-executive|independent|managing|chair)", t))):
        return "several"
    if re.search(r"\bchair(?:man|person)?\b", t):
        return "chair"
    if re.search(r"\bmanaging director\b|\bchief executive\b|\bceo\b", t):
        return "chief_executive"
    if re.search(r"(?<!non-)\bindependent\b|\bindependant\b", t) and "non-executive" in t:
        return "independent_non_executive"
    if "non-executive" in t:
        return "non_executive"
    if re.search(r"\bexecutive\b|\bdirector\s*-\s*finance\b|\bfinance director\b", t):
        return "executive"
    return "not_stated"


# --- the old parse and drop_refiled ------------------------------------------------------------------------------

def parse(aid: str, data: dict) -> list[dict]:
    """One notice -> its transactions, as the old cse/dealings.parse (old column names; neutral side labels)."""
    b = (data or {}).get("reqBaseAnnouncement") or {}
    if b.get("dType") != DEALING_TYPE or not b.get("directorTransactions"):
        return []
    docs = (data or {}).get("reqAnnouncementDocs") or []
    url = (CDN + docs[0]["fileUrl"].lstrip("/")).replace(" ", "%20") if docs and docs[0].get("fileUrl") else ""
    announced = parse_date(b.get("dateOfAnnouncement")) or parse_date(b.get("dateOfNotification"))
    related = bool(b.get("accTypeRelInterest"))
    director = _space(b.get("dircetorsName"))
    account = _space(b.get("relInterestAccountName")) if related else director
    rows = []
    for t in b["directorTransactions"]:
        td = parse_date(t.get("transactionDate"))
        q, p = _num(t.get("quantity")), _num(t.get("price"))
        rows.append({
            "announcement_id": aid, "announced": announced.isoformat() if announced else "",
            "symbol": (b.get("symbol") or "").strip(), "company": (b.get("companyName") or "").strip(),
            "director": director, "director_role": (b.get("natureOfDir") or "").strip(),
            "account_type": "related" if related else "own", "account": account or director,
            "trade_date": td.isoformat() if td else "", "side": side_of(t.get("transType") or ""),
            "trans_type": (t.get("transType") or "").strip(), "quantity": q, "price": p,
            "value": q * p if q is not None and p is not None else None,
            "lag_days": weekdays_between(td, announced) if td and announced else None, "url": url,
        })
    return rows


def refiled(rows: list[dict]) -> dict[str, str]:
    """{earlier notice: the later notice that re-files it}. A later notice (by announcement date, then id) for the
    same company, director and account that repeats every transaction of an earlier one (same side, quantity and
    price; at least one also on the same date) replaces it. Identical lines inside one notice are separate trades.
    Old cse/dealings.drop_refiled, which dropped the earlier notice's rows; here they are kept and marked."""
    notices: dict[str, list[dict]] = {}
    for r in rows:
        notices.setdefault(r["announcement_id"], []).append(r)
    order = sorted(notices, key=lambda a: (notices[a][0]["announced"], int(a)))
    who = {a: (notices[a][0]["symbol"], notices[a][0]["director"].lower(), notices[a][0]["account"].lower())
           for a in order}
    sig = {a: Counter((r["side"], r["quantity"], r["price"]) for r in notices[a]) for a in order}
    exact = {a: {(r["trade_date"], r["side"], r["quantity"], r["price"]) for r in notices[a]} for a in order}
    by: dict[str, str] = {}
    for i, a in enumerate(order):
        for b in order[i + 1:]:
            if who[a] == who[b] and not sig[a] - sig[b] and exact[a] & exact[b]:
                by[a] = b
                break
    return by


def sort_key(r: dict):
    return (r["trade_date"] or r["announced"], r["announced"], int(r["announcement_id"]))


def as_stored(v):
    """Numbers as the old CSV stored them (old cse/storage.py fmt): whole numbers exactly, others to 8 decimals."""
    if isinstance(v, float) and not math.isnan(v) and not (v.is_integer() and abs(v) < 1e15):
        return round(v, 8)
    return v


# --- inputs ------------------------------------------------------------------------------------------------------

def notices(inputs) -> dict[str, dict]:
    """{announcement id: the latest typed detail response with a dealing record} as {reqBaseAnnouncement,
    reqAnnouncementDocs}. The old tool kept one file per notice; the platform keeps every distinct response, and the
    latest one counts (as for corporate actions)."""
    out: dict[str, dict] = {}
    for r in inputs.rows("cse.announcement_details", "announcement_id, base, docs",
                         where="has_detail and endpoint = %s and d_type = %s", params=(TYPED, DEALING_TYPE),
                         order_by="fetched_at, fetch_id"):
        out[str(r["announcement_id"])] = {"reqBaseAnnouncement": r["base"], "reqAnnouncementDocs": r["docs"]}
    return out


def transactions(inputs, as_of: dt.date | None) -> list[dict]:
    """Every transaction in the notices announced on or before as_of (all of them when as_of is None), in the old
    CSV's order, each with `superseded_by` (the re-filing notice, or None) and `line_no` (1-based, in the notice)."""
    rows: list[dict] = []
    for aid, data in notices(inputs).items():
        parsed = parse(aid, data)
        if as_of is not None and parsed and not (parsed[0]["announced"] and parsed[0]["announced"] <= as_of.isoformat()):
            continue
        for n, r in enumerate(parsed, 1):
            r["line_no"] = n
        rows += parsed
    by = refiled(rows)
    for r in rows:
        r["superseded_by"] = by.get(r["announcement_id"])
    rows.sort(key=sort_key)
    return rows


def compute(inputs, as_of):
    rows = transactions(inputs, as_of)
    dealing, as_filed = [], []
    for r in rows:
        tid = f"{r['announcement_id']}:{r['line_no']}"
        dealing.append({
            "transaction_id": tid, "announcement_id": int(r["announcement_id"]), "line_no": r["line_no"],
            "symbol": r["symbol"], "company": r["company"], "role": role_of(r["director_role"]),
            "account_type": r["account_type"], "trade_date": r["trade_date"] or None,
            "deal_date": r["trade_date"] or r["announced"] or None, "side": r["side"],
            "quantity": as_stored(r["quantity"]), "price": as_stored(r["price"]), "value": as_stored(r["value"]),
            "announced_date": r["announced"] or None, "lag_days": r["lag_days"],
            "superseded_by": int(r["superseded_by"]) if r["superseded_by"] else None})
        as_filed.append({"transaction_id": tid, "director": r["director"], "director_role": r["director_role"],
                         "account": r["account"], "trans_type": r["trans_type"], "source_url": r["url"]})
    return {"models.cse_dealing": dealing, "models.cse_dealing_as_filed": as_filed}
