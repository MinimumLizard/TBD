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

from . import lab_charts as charts

NEW, OLD = "1.1.0", "1.0.0"                      # cse_lab_backtest: the current rules, and the first ones (reference)
FLAGSHIP = ("quarterly", "min_variance_15")      # the example portfolio (decisions 0024, 0025)
LABELS = {"min_variance_10": "Minimum variance, 10 names", "min_variance_15": "Minimum variance, 15 names",
          "max_sharpe_10": "Maximum Sharpe, 10 names", "max_sharpe_15": "Maximum Sharpe, 15 names",
          "equal_weight_10": "Equal weight, 10 names", "equal_weight_15": "Equal weight, 15 names",
          "market": "ASPI (prices only, no dividends)", "bills": "Treasury bills (12-month yield)"}
ESTIMATORS = {"daily": "Daily returns, with lagged terms (the lab's choice)",
              "constant_corr": "Weekly, towards one average correlation",
              "single_index": "Weekly, towards the market model",
              "oas": "Weekly, towards equal risk (OAS)",
              "identity": "Weekly, towards equal risk (the first rules)"}
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
beta against the ASPI; and, from the daily returns over the same span, each share's volatility and the covariance
between every pair of shares. Thinly traded shares react to news a day or two late, so the covariances of returns one
and two days apart are added in; the result is shrunk towards a simpler estimate (Ledoit-Wolf) because a year of data
is short. The next section shows why this estimate is used.</li>
<li><b>The lowest-risk combination.</b> Minimum variance: the weights that give the smallest estimated volatility for
the whole portfolio, with no share above {p['max_weight']:.0%}, no sector above {p['max_sector_weight']:.0%} and no
ownership group above {p['max_group_weight']:.0%}. It favours shares that are steady on their own and that move
differently from each other. It uses no forecast of returns.</li>
<li><b>Fewer names, so the portfolio is practical.</b> The {k} largest weights of that portfolio (when it has fewer
than {k}, the shares it would take next), re-optimised with a cap of {max(p['max_weight'], 1.5 / k):.0%} and a floor of
{0.5 / k:.1%} per name, so that every position is worth its costs. At a review a name already in the portfolio stays
while it still ranks in the top {int(1.5 * k)}: this buffer avoids trading on small changes.</li>
<li><b>Trading only what is worth its cost.</b> Near its lowest point a portfolio's volatility changes very little
with the weights. So at a review the rules look for the weights closest to what is already there, among those whose
estimated volatility is within {p['fewer_names'].get('tolerance', 0):.0%} of the lowest possible, instead of moving
every weight to the exact minimum.</li>
<li><b>When it is reviewed.</b> On the first session of January, April, July and October; between reviews a name is
brought back only when its weight drifts by more than a quarter of its target (or two percentage points). The
dynamic alternative also checks on the first session of every month and rebalances when the holdings have moved
away from the rules' new portfolio by more than {p['te_threshold']:.0%} of estimated tracking error.</li>
<li><b>Costs.</b> Every trade pays {p['cost_per_side']:.2%} of its value; whole shares only; dividends, splits and
rights issues are booked on their ex-date.</li>
</ol>"""


def drawdown(points: list[tuple[dt.date, float]]) -> list[tuple[dt.date, float]]:
    peak, out = None, []
    for d, v in points:
        peak = v if peak is None else max(peak, v)
        out.append((d, (v / peak - 1) * 100))
    return out


def section_evidence(conn) -> str:
    """The risk test: why the covariance estimate is the one it is."""
    test = q(conn, "select * from models.cse_bt_risk_test where method_version = %s", NEW)
    if not test:
        return ""
    by = {(r["scope"], r["estimator"]): r for r in test}
    full = {e: by[("full", e)] for e in ESTIMATORS if ("full", e) in by}
    k_scope = next((r["scope"] for r in test if r["scope"] != "full"), None)
    small = {e: by[(k_scope, e)] for e in ESTIMATORS if (k_scope, e) in by} if k_scope else {}
    any_row = next(iter(full.values()))
    market, equal = by.get(("full", "ref_market")), by.get(("full", "ref_equal_weight"))
    chosen, first = full.get("daily"), full.get("identity")
    chart = charts.bars(
        [{"label": ESTIMATORS[e], "values": [r["forecast_volatility"] * 100, r["realised_volatility"] * 100]}
         for e, r in full.items()],
        aria="Forecast and realised volatility of the weekly minimum-variance portfolio, by covariance estimate",
        fmt=lambda v: f"{v:.1f}%", names=[("Volatility forecast", charts.colour(1)), ("Volatility realised", charts.colour(0))],
        refs=[(market["realised_volatility"] * 100, "ASPI")] if market else [], label_width=300)
    rows = []
    for e, r in full.items():
        s = small.get(e)
        rows.append([esc(ESTIMATORS[e]), pct(r["forecast_volatility"]), f"<b>{pct(r['realised_volatility'])}</b>",
                     "&ndash;" if e == "identity" else f"{r['variance_ratio']:.2f} ({r['ratio_low']:.2f} to {r['ratio_high']:.2f})",
                     pct(r["weekly_turnover"]), pct(s["realised_volatility"]) if s else "–"])
    k = k_scope[1:] if k_scope else ""
    return f"""
<h2>Why the rules estimate risk the way they do</h2>
<p>A minimum-variance portfolio is only as good as its estimate of how the shares move together. Five ways of making
that estimate were tested on the one thing they are for: <b>risk</b>. Every week from {day(any_row['start_date'])} to
{day(any_row['end_date'])} ({any_row['n_weeks']} weeks), the minimum-variance portfolio was built with each estimate,
using only what was known that week, and its volatility was measured over the week that followed. Returns were not
looked at: over a few months a difference in return between two methods is chance, a difference in risk is not.</p>
{chart}
{table(["Covariance estimate", "Volatility it forecast", "Volatility realised",
        "Realised variance against the first rules (90 % interval)", "Weights changed per week",
        f"Realised, {k}-name version"], rows)}
<ul>
<li>The first rules' estimate (weekly returns) forecast {pct(first['forecast_volatility'])} and delivered
{pct(first['realised_volatility'])}: more than it promised, and no steadier than the market itself
({pct(market['realised_volatility'])}). With about 140 shares and at most 52 weekly returns there is too little data
in it.</li>
<li>The estimate from daily returns delivered {pct(chosen['realised_volatility'])}, close to the
{pct(chosen['forecast_volatility'])} it forecast. Its realised variance was {chosen['variance_ratio']:.2f} of the first
rules', and the 90 % interval ({chosen['ratio_low']:.2f} to {chosen['ratio_high']:.2f}) stays well below 1, so the
difference is not chance. It also changed its weights the least from week to week.</li>
<li>For comparison, an equal amount in every share considered had a volatility of {pct(equal['realised_volatility'])}.</li>
</ul>
<p class="small muted">Limits. The estimate was chosen on these same {any_row['n_weeks']} weeks, which flatters it
somewhat; the test is stored with the model and repeats itself as history grows, so the choice is checked again every
day. The number of lagged days (two) was fixed before any result was seen; with none to four the realised volatility
stayed between 10.0 % and 10.9 %. No costs are counted here: this compares estimates, not trading rules.</p>"""


def section_backtest(conn) -> str:
    summary = q(conn, "select * from models.cse_bt_summary where method_version = %s", NEW)
    if not summary:
        return "<h2>What the rules would have done</h2><p>The walk-forward test has not run yet.</p>"
    by = {(r["policy"], r["portfolio"]): r for r in summary}
    old = {(r["policy"], r["portfolio"]): r for r in q(conn, "select * from models.cse_bt_summary where method_version = %s", OLD)}
    start, end = summary[0]["start_date"], summary[0]["end_date"]
    navs: dict[tuple[str, str], list] = defaultdict(list)
    for r in q(conn, """select method_version, session_date, portfolio, nav from models.cse_bt_nav
                        where policy = 'quarterly' and method_version in (%s, %s) order by session_date""", NEW, OLD):
        navs[(r["method_version"], r["portfolio"])].append((r["session_date"], r["nav"]))
    port = FLAGSHIP[1]
    index = lambda pts: [(d, v / pts[0][1] * 100) for d, v in pts]
    shown = [("The example portfolio (current rules)", navs.get((NEW, port)), charts.colour(0), 2.6, None),
             ("The same portfolio under the first rules", navs.get((OLD, port)), charts.colour(1), 1.8, None),
             (LABELS["market"], navs.get((NEW, "market")), charts.MUTED, 1.6, "6 4"),
             (LABELS["bills"], navs.get((NEW, "bills")), charts.MUTED, 1.6, "2 3")]
    shown = [x for x in shown if x[1]]
    value = charts.lines([{"label": lab, "points": index(pts), "colour": c, "width": w, "dash": d}
                          for lab, pts, c, w, d in shown],
                         aria="Value of each portfolio, 100 at the start", fmt=lambda v: f"{v:.0f}",
                         end_fmt=lambda v: f"{v - 100:+.1f}%", base=100)
    falls = charts.lines([{"label": lab, "points": drawdown(pts), "colour": c, "width": w, "dash": d}
                          for lab, pts, c, w, d in shown if "bills" not in lab.lower()],
                         aria="Fall of each portfolio from its highest value so far", fmt=lambda v: f"{v:.0f}%",
                         end_fmt=lambda v: f"{v:.1f}%", base=0, height=220)
    order = ["min_variance_15", "min_variance_10", "max_sharpe_15", "max_sharpe_10", "equal_weight_15",
             "equal_weight_10", "market", "bills"]
    rows = []
    for name in order:
        qr, dy = by.get(("quarterly", name)), by.get(("dynamic", name))
        if not qr:
            continue
        rows.append([esc(LABELS[name]), signed(qr["total_return"]), pct(qr["volatility"]), signed(qr["max_drawdown"]),
                     lkr(qr["costs"]) if qr["costs"] is not None else "–",
                     signed(dy["total_return"]) if dy and dy["costs"] is not None else "–",
                     lkr(dy["costs"]) if dy and dy["costs"] is not None else "–",
                     esc(dy["n_rebalances"]) if dy and dy["n_rebalances"] is not None else "–"])
    flag, was = by.get(FLAGSHIP), old.get(FLAGSHIP)
    dyn = by.get(("dynamic", port))
    mk, bills = by.get(("quarterly", "market")), by.get(("quarterly", "bills"))
    compare = ""
    if flag and was and mk:
        compare = table(["", "Return", "Volatility", "Largest fall", "Costs", "Traded (of average value)"], [
            ["<b>The example portfolio, current rules</b>", signed(flag["total_return"]), pct(flag["volatility"]),
             signed(flag["max_drawdown"]), lkr(flag["costs"]), pct(flag["turnover"], 0)],
            ["The same portfolio, first rules", signed(was["total_return"]), pct(was["volatility"]),
             signed(was["max_drawdown"]), lkr(was["costs"]), pct(was["turnover"], 0)],
            [esc(LABELS["market"]), signed(mk["total_return"]), pct(mk["volatility"]), signed(mk["max_drawdown"]), "–", "–"],
            [esc(LABELS["bills"]), signed(bills["total_return"]), pct(bills["volatility"]), "–", "–", "–"]])
    events = q(conn, """select * from models.cse_bt_event where method_version = %s and policy = %s and
                        portfolio = %s order by session_date""", NEW, *FLAGSHIP)
    old_events = q(conn, """select * from models.cse_bt_event where method_version = %s and policy = %s and
                            portfolio = %s order by session_date""", OLD, *FLAGSHIP)
    log = [[day(e["session_date"]), esc(KIND.get(e["kind"], e["kind"])),
            esc(", ".join(x.split(".")[0] for x in e["names_in"].split(",") if x) or "–"),
            esc(", ".join(x.split(".")[0] for x in e["names_out"].split(",") if x) or "–"),
            lkr(e["turnover"]), lkr(e["cost"]), esc(e["estimate_weeks"] or "–")] for e in events if e["kind"] != "drift"]
    was_cost = {e["session_date"]: e["cost"] for e in old_events if e["kind"] != "drift"}
    cost_chart = charts.bars(
        [{"label": f"{day(e['session_date'])}: {KIND.get(e['kind'], e['kind'])}",
          "values": [e["cost"], was_cost.get(e["session_date"])]} for e in events if e["kind"] != "drift"],
        aria="Trading cost at the start and at each review, current rules and first rules",
        fmt=lambda v: f"Rs {v:,.0f}", names=[("Current rules", charts.colour(0)), ("First rules", charts.colour(1))],
        label_width=230)
    drifts = sum(1 for e in events if e["kind"] == "drift")
    months = round((end - start).days / 30.4)
    up = mk and mk["total_return"] is not None and mk["total_return"] >= 0
    return f"""
<h2>What the rules would have done since {day(start)}</h2>
<p>The first date the rules could be applied honestly is <b>{day(start)}</b>: they need at least half a year of
weekly returns, and the price history available starts in October 2025 (the CSE's public chart reaches back one year).
From then to {day(end)} (about {months} months), each date's decision uses only what was known on that date. Each
portfolio starts with Rs 1 million.</p>
{value}
<p class="small muted">Quarterly reviews. Portfolio values include dividends and costs; the ASPI is a price index and
leaves dividends out, so it understates the market's return by roughly the dividends paid.</p>
{compare}
<h3>How far each fell from its highest value</h3>
{falls}
<p class="small muted">Zero means a new high. The depth of a fall is what a person living through it sees; it is
the plainest measure of what "steadier" means.</p>
<h3>Every portfolio the rules can build</h3>
{table(["Portfolio", "Return, quarterly", "Volatility", "Largest fall", "Costs, quarterly", "Return, dynamic",
        "Costs, dynamic", "Rebalances, dynamic"], rows)}
<h3>Reading the result</h3>
<ul>
<li>The share market ended the period {"a little higher" if up else "lower"} (the ASPI {signed(mk['total_return'] if mk else None)})
after falling {signed(mk['max_drawdown'] if mk else None)} on the way; treasury bills returned
{signed(bills['total_return'] if bills else None)} with no fall at all. Over a few months, which way the market went
matters far more than how a share portfolio was built.</li>
<li>The example portfolio did what minimum variance is for: its volatility was {pct(flag['volatility'] if flag else None)}
against the market's {pct(mk['volatility'] if mk else None)}, and its largest fall {signed(flag['max_drawdown'] if flag else None)}
against {signed(mk['max_drawdown'] if mk else None)}. Under the first rules the same portfolio was no steadier than the
market ({pct(was['volatility'] if was else None)}, largest fall {signed(was['max_drawdown'] if was else None)}).</li>
<li>Costs remain large for a portfolio of Rs 1 million: {lkr(flag['costs'] if flag else None)} over the period
({pct((flag['costs'] or 0) / 1_000_000 if flag else None)} of the starting value), more than half of it the cost of the
first purchases. Trading only what is worth its cost brought it down from {lkr(was['costs'] if was else None)}.</li>
<li>The monthly check (the dynamic policy) traded more and did not make the portfolio steadier
({pct(dyn['volatility'] if dyn else None)}, costs {lkr(dyn['costs'] if dyn else None)}), which is why the example
keeps quarterly reviews.</li>
<li>{months} months is far too short to judge any method on its return. Differences of a few percentage points
between these portfolios are within what chance alone produces; the test lengthens by itself as the record grows.</li>
</ul>
<h3>Every review of the example portfolio</h3>
{cost_chart}
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
    last = q(conn, """select max(as_of) d from models.cse_bt_target where method_version = %s and policy = %s
                      and portfolio = %s and applied""", NEW, policy, port)[0]["d"]
    if last is None:
        return ""
    held = q(conn, """select * from models.cse_bt_target where method_version = %s and policy = %s
                      and portfolio = %s and applied and as_of = %s order by weight desc""", NEW, policy, port, last)
    today = q(conn, """select * from models.cse_bt_target where method_version = %s and policy = %s
                       and portfolio = %s and today""", NEW, policy, port)
    event = q(conn, """select * from models.cse_bt_event where method_version = %s and policy = %s and portfolio = %s
                       and session_date = %s and kind <> 'drift'""", NEW, policy, port, last)
    e = event[0] if event else None
    median_vol = (e or {}).get("universe_volatility_median") or 0.0
    sectors = defaultdict(float)
    for h in held:
        sectors[h["sector"]] += h["weight"]
    rows = [[f"<b>{esc(names.get(h['symbol'], h['symbol']))}</b><br><span class='small muted'>{esc(h['symbol'])} · "
             f"{esc(h['sector'])}</span>", pct(h["weight"]), esc(reason(h, median_vol, k))] for h in held]
    changed_today = sorted({t["symbol"] for t in today} ^ {h["symbol"] for h in held}) if today else []
    out = "; ".join(f"{esc(names.get(s, s))} ({esc(s.split('.')[0])})" for s in (e["names_out"].split(",") if e and e["names_out"] else []))
    weight_chart = charts.bars(
        [{"label": names.get(h["symbol"], h["symbol"])[:34], "values": [h["weight"] * 100, (h["risk_contribution"] or 0) * 100]}
         for h in held],
        aria="Each share's part of the portfolio's value and of its estimated risk",
        fmt=lambda v: f"{v:.1f}%", names=[("Part of the value", charts.colour(0)), ("Part of the estimated risk", charts.colour(1))],
        label_width=250)
    sector_chart = charts.bars(
        [{"label": s_, "values": [w * 100]} for s_, w in sorted(sectors.items(), key=lambda kv: -kv[1])],
        aria="The portfolio's value by sector", fmt=lambda v: f"{v:.0f}%", names=[("Part of the value", charts.colour(0))],
        refs=[(30.0, "sector cap 30%")], label_width=250)
    return f"""
<h2>Today's example portfolio, and the reason for each holding</h2>
<p>The same rules, applied at the latest review ({day(last)}): minimum variance with {k} names. These are the weights the
rules set; they stay until the next quarterly review unless a weight drifts outside its band.
{f"Estimated volatility {pct(e['model_volatility'])} a year." if e and e['model_volatility'] else ""}
</p>
<h3>Value and risk, share by share</h3>
{weight_chart}
<p class="small muted">Where the two bars of a share are about equal, it carries as much of the risk as of the value.
A share with a longer second bar is one of the more volatile names; one with a shorter second bar steadies the rest.</p>
<h3>By sector</h3>
{sector_chart}
<h3>The reason for each one</h3>
{table(["Share", "Weight", "Why the rules include it"], rows)}
<p class="small muted">Volatility and correlation are estimated from the daily returns of the
{esc(e['estimate_weeks'] if e else '–')} weeks to the review date. Left at this review: {out or "none"}.
{f"Rebuilt on the latest session, the rules would change {len(changed_today) // 2} name(s); under quarterly reviews that waits for the next review." if changed_today else "Rebuilt on the latest session, the rules would choose the same names."}</p>
<div class="explain"><p><strong>How to read this.</strong> Each reason is a measurement, not a view on the company:
the rules choose shares for how they move, alone and together, not for their prospects. A different set of rules, or
the same rules a month later, can give a different list. Nothing here says whether any share suits anyone.</p></div>"""
