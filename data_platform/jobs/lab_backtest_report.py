"""The walk-forward test and today's example portfolio, as sections of the owner's lab report (jobs/lab_report.py).

Written as education (decision 0024): how a rules-based portfolio is built, what the rules would have done since
the first date they could run, and why each holding of today's example portfolio is there. It describes rules
applied to public data; it never says what anyone should do. Self-contained HTML (inline SVG, no scripts), so the
report reads the same as a file and inside the owners' preview.
"""
from __future__ import annotations

import datetime as dt
import html
from collections import defaultdict

FLAGSHIP = ("quarterly", "min_variance_15")      # the example portfolio (proposal: docs/plan-portfolio-lab.md)
CHART = ["min_variance_15", "min_variance_10", "max_sharpe_10", "equal_weight_15", "market", "bills"]
LABELS = {"min_variance_10": "Minimum variance, 10 names", "min_variance_15": "Minimum variance, 15 names",
          "max_sharpe_10": "Maximum Sharpe, 10 names", "max_sharpe_15": "Maximum Sharpe, 15 names",
          "equal_weight_10": "Equal weight, 10 names", "equal_weight_15": "Equal weight, 15 names",
          "market": "ASPI (prices only, no dividends)", "bills": "Treasury bills (12-month yield)"}
COLOURS = {"min_variance_15": "#23573f", "min_variance_10": "#7cc4a0", "max_sharpe_10": "#5b4d86",
           "equal_weight_15": "#a3741c", "market": "#5d625c", "bills": "#ad3a2c"}
KIND = {"inception": "start", "scheduled": "quarterly review", "threshold": "monthly check: moved too far",
        "drift": "drift band"}


def esc(v) -> str:
    return html.escape(str(v))


def pct(v, digits=1) -> str:
    return "–" if v is None else f"{v * 100:+.{digits}f}%" if digits < 0 else f"{v * 100:.{digits}f}%"


def signed(v, digits=1) -> str:
    return "–" if v is None else f"{v * 100:+.{digits}f}%"


def lkr(v) -> str:
    return "–" if v is None else f"Rs {v:,.0f}"


def day(d) -> str:
    return f"{d:%-d %b %Y}" if hasattr(d, "strftime") else str(d)


def q(conn, sql: str, *params) -> list[dict]:
    return [dict(r) for r in conn.execute(sql, params)]


def table(head: list[str], body: list[list], cls: str = "") -> str:
    th = "".join(f"<th>{esc(h)}</th>" for h in head)
    rows = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in body)
    return f'<div class="table-wrap"><table class="{cls}"><thead><tr>{th}</tr></thead><tbody>{rows}</tbody></table></div>'


def svg_lines(series: dict[str, list[tuple[dt.date, float]]], width: int = 760, height: int = 300) -> str:
    """Lines indexed to 100 at the start, with a light grid, the 100 line, month labels and a legend."""
    pts = {k: [(d, v / s[0][1] * 100) for d, v in s] for k, s in series.items() if s}
    if not pts:
        return ""
    dates = sorted({d for s in pts.values() for d, _ in s})
    lo = min(v for s in pts.values() for _, v in s)
    hi = max(v for s in pts.values() for _, v in s)
    lo, hi = min(lo, 100) - 1, max(hi, 100) + 1
    left, right, top, bottom = 44, 12, 12, 26
    x0, x1 = dates[0].toordinal(), dates[-1].toordinal()
    X = lambda d: left + (d.toordinal() - x0) / max(x1 - x0, 1) * (width - left - right)  # noqa: E731
    Y = lambda v: top + (hi - v) / (hi - lo) * (height - top - bottom)  # noqa: E731
    parts = []
    step = 5 if hi - lo > 20 else 2
    v = (int(lo) // step + 1) * step
    while v < hi:
        parts.append(f'<line x1="{left}" x2="{width - right}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" class="grid"/>'
                     f'<text x="{left - 6}" y="{Y(v) + 4:.1f}" text-anchor="end">{v}</text>')
        v += step
    parts.append(f'<line x1="{left}" x2="{width - right}" y1="{Y(100):.1f}" y2="{Y(100):.1f}" class="base"/>')
    months = sorted({(d.year, d.month) for d in dates})
    for y, m in months:
        first = min(d for d in dates if (d.year, d.month) == (y, m))
        parts.append(f'<text x="{X(first):.1f}" y="{height - 8}" text-anchor="middle">{dt.date(y, m, 1):%b}</text>')
    for k, s in pts.items():
        path = " ".join(f"{'M' if i == 0 else 'L'}{X(d):.1f},{Y(v):.1f}" for i, (d, v) in enumerate(s))
        width_ = 2.6 if k == FLAGSHIP[1] else 1.6
        dash = ' stroke-dasharray="5 4"' if k in ("market", "bills") else ""
        parts.append(f'<path d="{path}" fill="none" stroke="{COLOURS.get(k, "#888")}" stroke-width="{width_}"{dash}/>')
    legend = "".join(f'<span class="lg"><i style="background:{COLOURS.get(k, "#888")}"></i>{esc(LABELS.get(k, k))} '
                     f'{s[-1][1] - 100:+.1f}%</span>' for k, s in pts.items())
    return (f'<figure class="lab-chart"><svg viewBox="0 0 {width} {height}" role="img" '
            f'aria-label="Value of each portfolio, indexed to 100 at the start">{"".join(parts)}</svg>'
            f'<figcaption>{legend}</figcaption></figure>')


# --- sections ------------------------------------------------------------------------------------------------------

def section_intro() -> str:
    return """
<div class="explain">
<p><strong>What this is.</strong> A worked example of how a rules-based portfolio of CSE shares is built, tested and
reviewed: the rules are written down in advance, applied the same way on every date with only the information
available then, and their results are shown with their costs, good periods and bad. It is research and education. It
does not take anyone's circumstances into account, and it is not advice to deal in any share.</p>
</div>"""


def section_rules(p: dict) -> str:
    k = 15
    return f"""
<h2>The rules, step by step</h2>
<ol class="steps">
<li><b>Which shares can be considered.</b> Ordinary shares that traded on at least {p['min_traded_share']:.0%} of the
sessions in the past year, with median daily turnover of at least Rs {p['min_median_turnover_lkr'] / 1e6:.0f} mn and a
known sector. Anything less traded cannot be priced reliably or traded without moving its price.</li>
<li><b>How risky each share is, and how the shares move together.</b> From up to {p['min_history_weeks']} weekly total
returns (dividends included; at least {p['preview_min_weeks']} while a full year is not yet available): each share's
volatility, its beta against the ASPI, and the covariance between every pair of shares, shrunk towards a simpler
estimate (Ledoit-Wolf) because a year of data is short.</li>
<li><b>The lowest-risk combination.</b> Minimum variance: the weights that give the smallest estimated volatility for
the whole portfolio, with no share above {p['max_weight']:.0%}, no sector above {p['max_sector_weight']:.0%} and no
ownership group above {p['max_group_weight']:.0%}. It favours shares that are steady on their own and that move
differently from each other. It uses no forecast of returns.</li>
<li><b>Fewer names, so the portfolio is practical.</b> The {k} largest weights of that portfolio, re-optimised with a
cap of {max(p['max_weight'], 1.5 / k):.0%} and a floor of {0.5 / k:.1%} per name, so that every holding is worth its
costs. At a review a name already in the portfolio stays while it still ranks in the top {int(1.5 * k)}: this buffer
avoids trading on small changes.</li>
<li><b>When it is reviewed.</b> On the first session of January, April, July and October; between reviews a name is
brought back only when its weight drifts by more than a quarter of its target (or two percentage points). The
dynamic alternative also checks on the first session of every month and rebalances when the holdings have moved
away from the rules' new portfolio by more than {p['te_threshold']:.0%} of estimated tracking error.</li>
<li><b>Costs.</b> Every trade pays {p['cost_per_side']:.2%} of its value; whole shares only; dividends, splits and
rights issues are booked on their ex-date.</li>
</ol>"""


def section_backtest(conn) -> str:
    summary = q(conn, "select * from models.cse_bt_summary where method_version = '1.0.0'")
    if not summary:
        return "<h2>What the rules would have done</h2><p>The walk-forward test has not run yet.</p>"
    by = {(r["policy"], r["portfolio"]): r for r in summary}
    start, end = summary[0]["start_date"], summary[0]["end_date"]
    navs: dict[str, list] = defaultdict(list)
    for r in q(conn, """select session_date, portfolio, nav from models.cse_bt_nav where method_version = '1.0.0'
                        and policy = 'quarterly' order by session_date"""):
        navs[r["portfolio"]].append((r["session_date"], r["nav"]))
    chart = svg_lines({k: navs[k] for k in CHART if k in navs})
    order = ["min_variance_15", "min_variance_10", "max_sharpe_15", "max_sharpe_10", "equal_weight_15",
             "equal_weight_10", "market", "bills"]
    rows = []
    for port in order:
        qr, dy = by.get(("quarterly", port)), by.get(("dynamic", port))
        if not qr:
            continue
        rows.append([esc(LABELS[port]), signed(qr["total_return"]), pct(qr["volatility"]), signed(qr["max_drawdown"]),
                     lkr(qr["costs"]) if qr["costs"] is not None else "–",
                     signed(dy["total_return"]) if dy and dy["costs"] is not None else "–",
                     lkr(dy["costs"]) if dy and dy["costs"] is not None else "–",
                     esc(dy["n_rebalances"]) if dy and dy["n_rebalances"] is not None else "–"])
    flag = by.get(FLAGSHIP)
    mk, bills = by.get(("quarterly", "market")), by.get(("quarterly", "bills"))
    events = q(conn, """select * from models.cse_bt_event where method_version = '1.0.0' and policy = %s and
                        portfolio = %s order by session_date""", *FLAGSHIP)
    log = [[day(e["session_date"]), esc(KIND.get(e["kind"], e["kind"])),
            esc(", ".join(x.split(".")[0] for x in e["names_in"].split(",") if x) or "–"),
            esc(", ".join(x.split(".")[0] for x in e["names_out"].split(",") if x) or "–"),
            lkr(e["turnover"]), lkr(e["cost"]), esc(e["estimate_weeks"] or "–")] for e in events if e["kind"] != "drift"]
    drifts = sum(1 for e in events if e["kind"] == "drift")
    months = round((end - start).days / 30.4)
    return f"""
<h2>What the rules would have done since {day(start)}</h2>
<p>The first date the rules could be applied honestly is <b>{day(start)}</b>: they need at least half a year of
weekly returns, and the price history available starts in October 2025 (the CSE's public chart reaches back one year).
From then to {day(end)} (about {months} months), each date's decision uses only what was known on that date. Each
portfolio starts with Rs 1 million.</p>
{chart}
<p class="small muted">Quarterly reviews. Portfolio values include dividends and costs; the ASPI is a price index and
leaves dividends out, so it understates the market's return by roughly the dividends paid (about 1&ndash;2 % over six
months).</p>
{table(["Portfolio", "Return, quarterly", "Volatility", "Largest fall", "Costs, quarterly", "Return, dynamic",
        "Costs, dynamic", "Rebalances, dynamic"], rows)}
<h3>Reading the result</h3>
<ul>
<li>The share market fell over the period (the ASPI {signed(mk['total_return'] if mk else None)}), and every
rules-based share portfolio lost money with it; treasury bills returned {signed(bills['total_return'] if bills else None)}.
Over six months, which way the market went matters far more than how the portfolio was built.</li>
<li>Minimum variance was steadier than maximum Sharpe (volatility {pct(flag['volatility'] if flag else None)} against
{pct(by[('quarterly', 'max_sharpe_10')]['volatility'] if ('quarterly', 'max_sharpe_10') in by else None)} for 10-name maximum Sharpe),
which is what it is designed to do; it did not avoid the market's fall.</li>
<li>Costs are large: about 2 to 3 % of the starting value over the period, most of it at the start and at the July
review. The monthly check traded more and did not earn its extra costs back in this period, which is why the example
below keeps quarterly reviews.</li>
<li>Six months is far too short to judge any method. Differences of a few percentage points between these portfolios
are within what chance alone produces; the test lengthens by itself as the record grows.</li>
</ul>
<h3>Every review of the example portfolio</h3>
{table(["Date", "Why", "In", "Out", "Traded", "Cost", "Weeks of data"], log)}
<p class="small muted">Plus {drifts} small drift-band adjustment{"" if drifts == 1 else "s"} between reviews.</p>"""


def reason(h: dict, median_vol: float, k: int) -> str:
    bits = []
    vol, corr = h["volatility"], h["avg_correlation"]
    if vol is not None:
        bits.append(("steadier than most of the shares considered" if vol < median_vol else "more volatile than the median share considered")
                    + f" (volatility {vol * 100:.0f}% a year")
        bits[-1] += f", beta {h['beta']:.2f})" if h.get("beta") is not None else ")"
    if corr is not None:
        bits.append("moves largely independently of the other names" if corr < 0.15 else
                    "moves only partly with the other names" if corr < 0.35 else "moves closely with the other names")
        bits[-1] += f" (average correlation {corr:.2f})"
    if h["at_cap"]:
        bits.append("at the per-share cap: the rules would give it more without the cap")
    elif h["at_floor"]:
        bits.append(f"at the floor of {0.5 / k:.1%}: the smallest weight worth its costs")
    rc = h["risk_contribution"]
    if rc is not None:
        bits.append(f"{rc * 100:.0f}% of the portfolio's estimated risk for {h['weight'] * 100:.0f}% of its value")
    bits.append("kept from the previous review" if h["in_previous"] else "new at this review")
    s = "; ".join(bits)
    return s[0].upper() + s[1:] + "."


def section_today(conn, names: dict[str, str]) -> str:
    policy, port = FLAGSHIP
    k = int(port.rsplit("_", 1)[1])
    last = q(conn, """select max(as_of) d from models.cse_bt_target where method_version = '1.0.0' and policy = %s
                      and portfolio = %s and applied""", policy, port)[0]["d"]
    if last is None:
        return ""
    held = q(conn, """select * from models.cse_bt_target where method_version = '1.0.0' and policy = %s
                      and portfolio = %s and applied and as_of = %s order by weight desc""", policy, port, last)
    today = q(conn, """select * from models.cse_bt_target where method_version = '1.0.0' and policy = %s
                       and portfolio = %s and today""", policy, port)
    event = q(conn, """select * from models.cse_bt_event where method_version = '1.0.0' and policy = %s and portfolio = %s
                       and session_date = %s and kind <> 'drift'""", policy, port, last)
    e = event[0] if event else None
    median_vol = (e or {}).get("universe_volatility_median") or 0.0
    sectors = defaultdict(float)
    for h in held:
        sectors[h["sector"]] += h["weight"]
    rows = [[f"<b>{esc(names.get(h['symbol'], h['symbol']))}</b><br><span class='small muted'>{esc(h['symbol'])} · "
             f"{esc(h['sector'])}</span>", pct(h["weight"]), esc(reason(h, median_vol, k))] for h in held]
    changed_today = sorted({t["symbol"] for t in today} ^ {h["symbol"] for h in held}) if today else []
    out = "; ".join(f"{esc(names.get(s, s))} ({esc(s.split('.')[0])})" for s in (e["names_out"].split(",") if e and e["names_out"] else []))
    sector_line = ", ".join(f"{esc(s)} {w * 100:.0f}%" for s, w in sorted(sectors.items(), key=lambda kv: -kv[1]))
    return f"""
<h2>Today's example portfolio, and the reason for each holding</h2>
<p>The same rules, applied at the latest review ({day(last)}): minimum variance with {k} names. These are the weights the
rules set; they stay until the next quarterly review unless a weight drifts outside its band.
{f"Estimated volatility {pct(e['model_volatility'])} a year." if e and e['model_volatility'] else ""}
Sectors: {sector_line}.</p>
{table(["Share", "Weight", "Why the rules include it"], rows)}
<p class="small muted">Volatility and correlation are estimated from {esc(e['estimate_weeks'] if e else '–')} weekly
returns to the review date. Left at this review: {out or "none"}.
{f"Rebuilt on the latest session, the rules would change {len(changed_today) // 2} name(s); under quarterly reviews that waits for the next review." if changed_today else "Rebuilt on the latest session, the rules would choose the same names."}</p>
<div class="explain"><p><strong>How to read this.</strong> Each reason is a measurement, not a view on the company:
the rules choose shares for how they move, alone and together, not for their prospects. A different set of rules, or
the same rules a month later, can give a different list. Nothing here says whether any share suits anyone.</p></div>"""
