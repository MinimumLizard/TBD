"""Cross-check the crypto section against independent public reference points:

    python -m data_platform.jobs.crosscheck_crypto          # DATABASE_URL: a database with the Bitstamp history and
                                                             # the crypto models computed (jobs.models --market crypto)

Prints a Markdown table (measured, reference, tolerance, pass or fail, note) for docs/research/crypto-crosscheck.md,
and exits 1 if any check fails. The references come from docs/research/crypto-itc-review.md and the other public
sources named in each row; they are never used to fit anything. Where a reference is venue-dependent the tolerance
says so: Bitstamp's daily close is one venue's last trade of the UTC day, while many references are an index or an
intraday high.

tests/test_crypto_crosscheck.py runs the same checks when CROSSCHECK_DATABASE_URL points at such a database.
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from dataclasses import dataclass

D = dt.date.fromisoformat
CYCLE_VERSION = "1.0.0"


@dataclass
class Check:
    group: str
    name: str
    measured: str
    reference: str
    tolerance: str
    passed: bool
    note: str = ""


def _closes(conn, pair: str) -> dict[dt.date, float]:
    return {r["day"]: r["close"] for r in conn.execute(
        "select day, close from crypto.ohlc_daily where pair = %s order by day", (pair,))}


def _events(conn, kind: str, pair: str = "btcusd") -> list[dt.date]:
    return [r["day"] for r in conn.execute(
        """select day from models.crypto_cycle_event where method_version = %s and pair = %s and kind = %s
           order by day""", (CYCLE_VERSION, pair, kind))]


def _cycle(conn, day: dt.date, pair: str = "btcusd") -> dict:
    return conn.execute("""select * from models.crypto_cycle_daily where method_version = %s and pair = %s
                           and day = %s""", (CYCLE_VERSION, pair, day)).fetchone()


def _money(v: float) -> str:
    return f"${v:,.2f}" if v < 1000 else f"${v:,.0f}"


def _nearest(days: list[dt.date], target: dt.date) -> dt.date | None:
    return min(days, key=lambda d: abs((d - target).days)) if days else None


def pi_cycle(conn) -> list[Check]:
    out = []
    tops = _events(conn, "pi_top_cross")
    for label, ref_days, ref_text in [
        ("2013 top", (D("2013-11-29"), D("2013-11-30")), "2013-11-29/30"),
        ("2017 top", (D("2017-12-16"), D("2017-12-17")), "2017-12-17"),
        ("April 2021 top", (D("2021-04-13"), D("2021-04-14")), "2021-04-13/14"),
    ]:
        hit = _nearest(tops, ref_days[0])
        gap = min(abs((hit - r).days) for r in ref_days) if hit else None
        out.append(Check("Pi cycle", f"111/350 crossing near the {label}", str(hit), ref_text, "within 21 days",
                         gap is not None and gap <= 21, f"{gap} day(s) from the nearest reference date"))
    late = [d for d in tops if d > D("2021-06-30")]
    out.append(Check("Pi cycle", "No 111/350 crossing at the October 2025 high", ", ".join(map(str, late)) or "none",
                     "reportedly no crossing at the 2025-10-06 high", "none after mid-2021", not late))
    extra = [d for d in tops if d < D("2013-06-30")]
    out.append(Check("Pi cycle", "Other 111/350 crossings", ", ".join(map(str, extra)) or "none",
                     "the April 2013 high (2013-04-09/10 on Mt.Gox) is also a widely reported crossing", "information",
                     True, "near the first 2013 high; not a reference in the review"))
    bottoms = _events(conn, "pi_bottom_cross")
    for label, ref in [("January 2015 low", D("2015-01-14")), ("December 2018 low", D("2018-12-15"))]:
        hit = _nearest(bottoms, ref)
        gap = abs((hit - ref).days) if hit else None
        out.append(Check("Pi cycle", f"150/471 crossing near the {label}", str(hit), str(ref), "within 21 days",
                         gap is not None and gap <= 21, f"{gap} day(s)"))
    hit = _nearest(bottoms, D("2022-07-13"))
    gap = abs((hit - D("2022-07-13")).days) if hit else None
    out.append(Check("Pi cycle", "150/471 crossing in July 2022", str(hit),
                     "reported by Cointelegraph on 2022-07-12 as about to cross ('the third Pi Cycle bottom')",
                     "within 7 days", gap is not None and gap <= 7,
                     "the review's 'only 2015 and 2018 so far' predates it"))
    row = _cycle(conn, D("2022-07-12"))
    for col, ref in (("pi_ema_150", 32_332.0), ("pi_sma_471x0745", 32_208.0)):
        err = row[col] / ref - 1
        out.append(Check("Pi cycle", f"{col} on 2022-07-12", _money(row[col]), f"{_money(ref)} (Cointelegraph)",
                         "±3% (another venue)", abs(err) <= 0.03, f"{err:+.2%}"))
    return out


def moving_averages(conn) -> list[Check]:
    out = []
    june = [_cycle(conn, D("2026-06-21") + dt.timedelta(days=k))["sma_200w"] for k in range(10)]
    lo, hi = min(june), max(june)
    out.append(Check("200-week average", "21–30 June 2026, range", f"{_money(lo)} – {_money(hi)}",
                     "$61.6k – $62.4k (late June 2026, by source)", "±3% of the reference range",
                     lo >= 61_600 * 0.97 and hi <= 62_400 * 1.03,
                     f"{lo / 61_600 - 1:+.1%} to {hi / 62_400 - 1:+.1%} against the range's ends"))
    aug = [_cycle(conn, D("2026-08-01") + dt.timedelta(days=k))["sma_200w"] for k in range(31)]
    mid = _cycle(conn, D("2026-08-15"))["sma_200w"]
    out.append(Check("200-week average", "15 August 2026 (August range)",
                     f"{_money(mid)} ({_money(min(aug))} – {_money(max(aug))})", "about $63.8k (August 2026)",
                     "±3%", abs(mid / 63_800 - 1) <= 0.03, f"{mid / 63_800 - 1:+.2%}"))
    return out


def cycle_table(conn) -> list[Check]:
    last = conn.execute("select max(day) d from models.crypto_cycle_anchor where method_version = %s",
                        (CYCLE_VERSION,)).fetchone()["d"]
    anchors = {(r["kind"], r["epoch"]): r for r in conn.execute(
        """select * from models.crypto_cycle_anchor where method_version = %s and pair = 'btcusd' and day = %s""",
        (CYCLE_VERSION, last))}
    refs = [
        # kind, epoch, reference dates, reference price range, price tolerance, reference text
        ("cycle_peak", 1, (D("2013-11-29"), D("2013-11-30")), (1_163, 1_242), 0.05, "2013 top: ~$1,163 (CoinDesk) to $1,242 (Mt.Gox)"),
        ("cycle_low", 1, (D("2015-01-14"), D("2015-01-15")), (152, 177), 0.05, "2015 low: ~$152–177"),
        ("cycle_peak", 2, (D("2017-12-17"),), (19_783, 20_089), 0.05, "2017 top: ~$19,783 (CoinDesk) to $20,089 intraday"),
        ("cycle_low", 2, (D("2018-12-15"),), (3_122, 3_122), 0.03, "2018 low: ~$3,122"),
        ("cycle_peak", 3, (D("2021-11-10"),), (68_789, 69_044), 0.03, "2021 top: ~$68,789–69,044"),
        ("cycle_low", 3, (D("2022-11-21"), D("2022-11-22")), (15_480, 15_480), 0.03, "2022 low: ~$15,480"),
        ("cycle_peak", 4, (D("2025-10-06"),), (126_080, 126_270), 0.03, "2025 high: ~$126,080–126,270"),
    ]
    out = []
    highs = {r["day"]: (r["high"], r["low"]) for r in conn.execute(
        "select day, high, low from crypto.ohlc_daily where pair = 'btcusd'")}
    for kind, epoch, days, (plo, phi), tol, text in refs:
        a = anchors.get((kind, epoch))
        if a is None:
            out.append(Check("Cycle table", text, "missing", text, "", False))
            continue
        gap = min(abs((a["anchor_day"] - d).days) for d in days)
        # the reference is often an intraday extreme: compare it with Bitstamp's own high (peaks) or low (lows)
        hi, lo = highs[a["anchor_day"]]
        extreme_near = [highs[d][0 if kind == "cycle_peak" else 1] for d in highs if abs((d - a["anchor_day"]).days) <= 3]
        extreme = max(extreme_near) if kind == "cycle_peak" else min(extreme_near)
        close_ok = plo * (1 - tol) <= a["anchor_close"] <= phi * (1 + tol)
        extreme_ok = plo * (1 - tol) <= extreme <= phi * (1 + tol)
        passed = gap <= 7 and (close_ok or extreme_ok)
        out.append(Check(
            "Cycle table", f"{kind.replace('_', ' ')}, epoch {epoch}",
            f"{a['anchor_day']} close {_money(a['anchor_close'])}; intraday {'high' if kind == 'cycle_peak' else 'low'} "
            f"±3 days {_money(extreme)}", text, f"date ±7 days; price ±{tol:.0%} (close or intraday)", passed,
            f"{gap} day(s) from the reference date" + ("" if close_ok else "; the close differs, the intraday extreme matches")
            + (" (provisional)" if a["provisional"] else "")))
    return out


def halvings() -> list[Check]:
    from ..models._lib.crypto import HALVINGS

    explorer = {1: D("2012-11-28"), 2: D("2016-07-09"), 3: D("2020-05-11"), 4: D("2024-04-20")}
    return [Check("Halvings", f"halving {k} (block {210_000 * k:,})", str(HALVINGS[k]),
                  f"{explorer[k]} (block header time, blockstream.info, read 2026-10-18)", "same UTC date",
                  HALVINGS[k] == explorer[k]) for k in sorted(explorer)]


def closes(conn) -> list[Check]:
    btc = _closes(conn, "btcusd")
    # independent year-end closes (the cycle table above covers the highs and lows of the review's table)
    refs = [
        ("2016-12-31", (960, 1_000), "2016 year-end: ~$960–1,000 (press, walletinvestor)", 0.03),
        ("2019-12-31", (7_183, 7_193), "2019 year-end: ~$7,183–7,193 (press)", 0.03),
        ("2020-12-31", (29_000, 29_244), "2020 year-end: ~$29,000–29,244 (walletinvestor, substack)", 0.03),
        ("2023-12-31", (42_265, 42_265), "2023 year-end: $42,265 (walletinvestor)", 0.03),
        ("2024-12-31", (93_429, 93_429), "2024 year-end: $93,429 (walletinvestor)", 0.03),
    ]
    out = []
    for day, (lo, hi), text, tol in refs:
        c = btc[D(day)]
        ok = lo * (1 - tol) <= c <= hi * (1 + tol)
        dev = 0.0 if lo <= c <= hi else (c / lo - 1 if c < lo else c / hi - 1)
        out.append(Check("BTC closes", day, _money(c), text, f"±{tol:.0%}", ok,
                         f"{dev:+.2%} from the range" if dev else "inside the range"))
    return out


def consistency(conn) -> list[Check]:
    """ETH/BTC is its own Bitstamp market; ETH/USD ÷ BTC/USD is computed from two others. They should agree."""
    rows = conn.execute("""select e.day, e.close eth, b.close btc, x.close ethbtc from crypto.ohlc_daily e
                           join crypto.ohlc_daily b on b.day = e.day and b.pair = 'btcusd'
                           join crypto.ohlc_daily x on x.day = e.day and x.pair = 'ethbtc'
                           where e.pair = 'ethusd' and e.day >= '2018-01-01' order by e.day""").fetchall()
    devs = sorted(abs(r["eth"] / r["btc"] / r["ethbtc"] - 1) for r in rows)
    median, p99 = devs[len(devs) // 2], devs[int(len(devs) * 0.99)]
    return [Check("Consistency", f"ETH/BTC vs ETH/USD ÷ BTC/USD, {len(devs)} days from 2018",
                  f"median {median:.3%}, 99th percentile {p99:.2%}", "the two should agree closely",
                  "median under 0.5%", median < 0.005, "three separate Bitstamp markets")]


def power_law(conn) -> list[Check]:
    r = conn.execute("""select * from models.crypto_trend_band where method_version = '1.0.0' and pair = 'btcusd'
                        and fit = 'power_law' order by day desc limit 1""").fetchone()
    t = (r["day"] - D("2009-01-03")).days
    import math
    ref_line = 10 ** (-17.01 + 5.82 * math.log10(t))
    return [Check("Power law", f"fit on {r['day']} (A, B)", f"A = {r['intercept']:.2f}, B = {r['slope']:.3f}",
                  "A ≈ −17.01, B ≈ 5.82 (Santostasi, data from 2010)", "information",
                  True, f"our line {_money(r['fitted'])} vs the published line {_money(ref_line)} on that day "
                        f"({r['fitted'] / ref_line - 1:+.1%}); our data starts in September 2011")]


def run(conn) -> list[Check]:
    return pi_cycle(conn) + moving_averages(conn) + cycle_table(conn) + halvings() + closes(conn) \
        + consistency(conn) + power_law(conn)


def markdown(checks: list[Check]) -> str:
    lines = ["| Group | Check | Measured | Reference | Tolerance | Result | Note |", "|---|---|---|---|---|---|---|"]
    for c in checks:
        result = "info" if c.tolerance == "information" else ("pass" if c.passed else "**FAIL**")
        lines.append(f"| {c.group} | {c.name} | {c.measured} | {c.reference} | {c.tolerance} | {result} | {c.note} |")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description=__doc__.split("\n")[0]).parse_args(argv)
    from ..core import db, settings as settings_mod

    conn = db.connect(settings_mod.load().database_url)
    checks = run(conn)
    print(markdown(checks))
    failed = [c for c in checks if not c.passed]
    print(f"\n{len(checks)} checks, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
