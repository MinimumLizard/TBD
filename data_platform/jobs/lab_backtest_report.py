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


def fold(title: str, summary: str, body: str, *, open_: bool = False, anchor: str = "") -> str:
    """A drop-down section, in the site's own markup (components/Section.tsx): the title and a one-line summary stay
    visible when it is closed. A plain <details>, so it works without scripts, in the file and in the preview."""
    return (f'<details class="section"{f' id="{anchor}"' if anchor else ""}{" open" if open_ else ""}><summary>'
            f'<span class="s-title">{title}</span><span class="s-sum">{summary}</span>'
            f'<span class="s-chev" aria-hidden="true"></span></summary><div class="s-body">{body}</div></details>')


def tiles(items: list[tuple[str, str, str]]) -> str:
    """Headline numbers: (label, value, note)."""
    return '<div class="tiles">' + "".join(
        f'<div class="tile stat"><span class="label">{esc(label)}</span><span class="value">{value}</span>'
        f'<span class="sub">{note}</span></div>' for label, value, note in items) + "</div>"


SMALL_WORDS = {"OF", "AND", "THE", "FOR"}
ACRONYMS = {"IOC", "LOLC", "NDB", "HNB", "DFCC", "CIC", "JKH", "HSBC", "SLT", "CDB", "AIA", "PLC", "LTD", "BPPL",
            "ACL", "TKYO", "RIL", "HNBA"}


def display_name(name: str | None, symbol: str) -> str:
    """A company's name as the CSE writes it (capitals, ending in PLC), in ordinary case, with its ticker. A word that
    is part of the ticker, or a known abbreviation, stays in capitals (Lanka IOC, LOLC Holdings)."""
    code = symbol.split(".")[0]
    if not name:
        return code

    def word(w: str, i: int) -> str:
        core = w.strip("()&,.")
        if core in ACRONYMS or (len(core) >= 3 and core in code):
            return w
        if w in SMALL_WORDS and i:
            return w.lower()
        if len(core) <= 2:
            return w
        return "(" + w[1:].capitalize() if w.startswith("(") else w.capitalize()

    words = name.replace(" P L C", "").removesuffix(" PLC").split()
    return f"{' '.join(word(w, i) for i, w in enumerate(words))} ({code})"


def next_review(d: dt.date) -> dt.date:
    """The first day of the next review month (January, April, July, October) after d."""
    for months in range(1, 13):
        m = (d.month - 1 + months) % 12 + 1
        y = d.year + (d.month - 1 + months) // 12
        if m in (1, 4, 7, 10):
            return dt.date(y, m, 1)
    return d


# --- sections ------------------------------------------------------------------------------------------------------

def section_intro() -> str:
    return """
<div class="lab-intro">
<p class="lead">This page is a lesson in how a portfolio of Colombo Stock Exchange shares can be built by following
written rules, step by step, and what those rules would have done since April. It is a worked example to learn
from. It is not a list of shares to deal in, and it says nothing about what anyone should do with their money.</p>
<ul class="three">
<li><b>The rules come first.</b> They were written down before any result was seen, and applied the same way every
time.</li>
<li><b>No hindsight.</b> On each date the rules use only what was known on that date.</li>
<li><b>It does not know you.</b> Your savings, goals and circumstances are not part of it, so it cannot say what
suits you.</li>
</ul>
</div>"""


def section_rules(p: dict) -> str:
    k = 15
    return fold("The rules, step by step", "Six steps, from which shares can be considered to how often it is reviewed", f"""
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
</ol>""", anchor="rules")


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
    return fold("Why the rules measure risk this way", f"Five ways of estimating risk, tested week by week: the one used had the smallest swings ({pct(chosen['realised_volatility'])} against {pct(first['realised_volatility'])})", f"""
<p>A portfolio built for low risk is only as good as its estimate of how the shares move together. Five ways of making
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
day. The number of lagged days (two) was fixed before any result was seen, and the result barely changes with none to
four (the research note, §2). No costs are counted here: this compares estimates, not trading rules.</p>""", anchor="evidence")


def section_compare(conn) -> str:
    summary = q(conn, "select * from models.cse_bt_summary where method_version = %s", NEW)
    if not summary:
        return ""
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
        fall = "none" if not qr["max_drawdown"] else signed(qr["max_drawdown"])
        rows.append([esc(LABELS[name]), signed(qr["total_return"]), pct(qr["volatility"]), fall,
                     lkr(qr["costs"]) if qr["costs"] is not None else "–",
                     signed(dy["total_return"]) if dy and dy["costs"] is not None else "–",
                     lkr(dy["costs"]) if dy and dy["costs"] is not None else "–",
                     esc(dy["n_rebalances"]) if dy and dy["n_rebalances"] is not None else "–"])
    flag, was = by.get(FLAGSHIP), old.get(FLAGSHIP)
    mk, bills = by.get(("quarterly", "market")), by.get(("quarterly", "bills"))
    compare = ""
    if flag and was and mk:
        compare = table(["", "Return", "Volatility", "Largest fall", "Costs", "Traded (of average value)"], [
            ["<b>The example portfolio, current rules</b>", signed(flag["total_return"]), pct(flag["volatility"]),
             signed(flag["max_drawdown"]), lkr(flag["costs"]), pct(flag["turnover"], 0)],
            ["The same portfolio, first rules", signed(was["total_return"]), pct(was["volatility"]),
             signed(was["max_drawdown"]), lkr(was["costs"]), pct(was["turnover"], 0)],
            [esc(LABELS["market"]), signed(mk["total_return"]), pct(mk["volatility"]), signed(mk["max_drawdown"]), "–", "–"],
            [esc(LABELS["bills"]), signed(bills["total_return"]), pct(bills["volatility"]), "none", "–", "–"]])
    months = round((end - start).days / 30.4)
    mv = sorted(r["volatility"] for (pol, name), r in by.items() if pol == "quarterly" and name.startswith("min_variance"))
    mv_range = f"{pct(mv[0])} to {pct(mv[-1])}" if len(mv) > 1 else pct(mv[0]) if mv else "–"
    return fold("Other ways to build a portfolio, compared",
                "The same test for maximum Sharpe, equal weight, 10 names, and the lab's first rules",
                f"""
<p>The example portfolio is one of several the rules can build. All of them are tested the same way, from
{day(start)} to {day(end)}, Rs 1 million each, with costs.</p>
<ul class="small">
<li><b>Minimum variance</b> looks for the lowest swings. It uses no forecast of returns.</li>
<li><b>Maximum Sharpe</b> looks for the most expected return per unit of swing. It needs a forecast of returns (here
an assumed 6 % a year above bills, scaled by each share's beta), so it depends on an assumption.</li>
<li><b>Equal weight</b> puts the same amount in each of minimum variance's shares: the simplest comparison.</li>
</ul>
<h3>The example portfolio under the current rules and under the lab's first rules</h3>
{value}
{compare}
<h3>How far each fell from its highest value</h3>
{falls}
<p class="small muted">Zero means a new high. The depth of a fall is what a person living through it sees; it is
the plainest measure of what "steadier" means.</p>
<h3>Every portfolio the rules can build</h3>
{table(["Portfolio", "Return, quarterly", "Volatility", "Largest fall", "Costs, quarterly", "Return, dynamic",
        "Costs, dynamic", "Rebalances, dynamic"], rows)}
<p class="small muted">"Dynamic" checks every month and rebalances when the portfolio has moved too far from the
rules' fresh choice. It traded more and was no steadier, which is why the example keeps quarterly reviews.</p>
<ul class="small">
<li>The minimum-variance portfolios were the steadiest share portfolios: volatility {mv_range} against the market's
{pct(mk['volatility'] if mk else None)}. Under the first rules the same 15-name portfolio was no steadier than the
market ({pct(was['volatility'] if was else None)}).</li>
<li>Costs: {lkr(flag['costs'] if flag else None)} over the period under the current rules, against
{lkr(was['costs'] if was else None)} under the first rules.</li>
<li>{months} months is far too short to judge any method on its return. Differences of a few percentage points
between these portfolios are within what chance alone produces.</li>
</ul>""", anchor="compare")


def plain_reason(h: dict, median_vol: float) -> str:
    """One short line, in plain words, of why the rules include a share (the full measurements are in the table
    under it)."""
    bits = []
    vol, corr = h["volatility"], h["avg_correlation"]
    if vol is not None and median_vol:
        bits.append("steadier than most shares" if vol < median_vol else "swings more than most shares")
    if corr is not None:
        bits.append("moves largely on its own" if corr < 0.15 else "moves partly with the others" if corr < 0.35
                    else "moves closely with the others")
    if h["at_cap"]:
        bits.append("at the 10 % limit per share")
    s = ", ".join(bits) if bits else "chosen by the rules"
    return s[0].upper() + s[1:] + "."


def section_portfolio(conn, names: dict[str, str]) -> str:
    """Today's example portfolio, at the top of the page: what it contains, in two pie charts and a short list."""
    policy, port = FLAGSHIP
    last = q(conn, """select max(as_of) d from models.cse_bt_target where method_version = %s and policy = %s
                      and portfolio = %s and applied""", NEW, policy, port)[0]["d"]
    if last is None:
        return fold("Today's example portfolio", "Not formed yet.", "<p>The rules have not formed it yet.</p>", open_=True)
    held = q(conn, """select * from models.cse_bt_target where method_version = %s and policy = %s
                      and portfolio = %s and applied and as_of = %s order by weight desc""", NEW, policy, port, last)
    event = q(conn, """select * from models.cse_bt_event where method_version = %s and policy = %s and portfolio = %s
                       and session_date = %s and kind <> 'drift'""", NEW, policy, port, last)
    e = event[0] if event else {}
    summary = {r["portfolio"]: r for r in q(conn, """select * from models.cse_bt_summary where method_version = %s
                                                      and policy = %s""", NEW, policy)}
    flag, mk = summary.get(port), summary.get("market")
    median_vol = e.get("universe_volatility_median") or 0.0
    sectors: dict[str, float] = defaultdict(float)
    for h in held:
        sectors[h["sector"] or "Unclassified"] += h["weight"]
    by_share = charts.donut([(display_name(names.get(h["symbol"]), h["symbol"]), h["weight"]) for h in held],
                            aria="The example portfolio by share", centre=str(len(held)), centre_sub="shares",
                            other_label="other shares")
    by_sector = charts.donut(list(sectors.items()), aria="The example portfolio by sector", centre=str(len(sectors)),
                             centre_sub="sectors", other_label="other sectors")
    rows = [[f"{esc(display_name(names.get(h['symbol']), h['symbol']))}<br><span class='small muted'>{esc(h['sector'])}</span>",
             pct(h["weight"]), esc(plain_reason(h, median_vol))] for h in held]
    detail = [[esc(display_name(names.get(h["symbol"]), h["symbol"])), pct(h["weight"]), pct(h["volatility"], 0),
               f"{h['beta']:.2f}" if h["beta"] is not None else "–",
               f"{h['avg_correlation']:.2f}" if h["avg_correlation"] is not None else "–",
               pct(h["risk_contribution"]), "kept" if h["in_previous"] else "new"] for h in held]
    value_risk = charts.bars(
        [{"label": display_name(names.get(h["symbol"]), h["symbol"])[:40],
          "values": [h["weight"] * 100, (h["risk_contribution"] or 0) * 100]} for h in held],
        aria="Each share's part of the portfolio's value and of its estimated risk", fmt=lambda v: f"{v:.1f}%",
        names=[("Part of the value", charts.colour(0)), ("Part of the estimated risk", charts.colour(1))],
        label_width=270)
    nxt = next_review(last)
    body = f"""
<p>The same rules, applied at the latest review on <b>{day(last)}</b>, chose these {len(held)} shares and how much of
the portfolio each takes. The weights stay as they are until the next review, on the first trading day of
{nxt:%B %Y}.</p>
{tiles([("Shares", str(len(held)), f"in {len(sectors)} sectors"),
        ("Swings since April", pct(flag["volatility"] if flag else None),
         f"a year; the market: {pct(mk['volatility'] if mk else None)}"),
        ("Largest fall since April", signed(flag["max_drawdown"] if flag else None),
         f"the market: {signed(mk['max_drawdown'] if mk else None)}"),
        ("Next review", f"{nxt:%b %Y}", "first trading day")])}
<div class="donuts">
<div><h3>By share</h3>{by_share}</div>
<div><h3>By sector</h3>{by_sector}</div>
</div>
<div class="explain"><p><strong>How to read this.</strong> The rules look for shares that are steady on their own and
that do not all move together, so that a fall in one is often offset by the others. They choose shares for how
their prices move, not for what the companies do or might do next. A different set of rules, or the same rules a
month later, can give a different list.</p></div>
<details class="more"><summary>All {len(held)} shares, and why the rules include each one</summary>
{table(["Share", "Part of the portfolio", "Why the rules include it"], rows)}
</details>
<details class="more"><summary>The measurements behind each reason</summary>
<p class="small muted">Volatility: how much the price swings in a year. Beta: how much it tends to move when the whole
market moves by 1. Correlation: how closely it moves with the other shares here (0 = not at all, 1 = exactly).
Share of risk: how much of the portfolio's estimated swings comes from it.</p>
{table(["Share", "Weight", "Volatility", "Beta", "Correlation with the others", "Share of risk", "At this review"], detail)}
{value_risk}
<p class="small muted">Where a share's two bars are about equal, it carries as much of the risk as of the value. A
longer second bar marks one of the more volatile names; a shorter one, a share that steadies the rest.</p>
</details>"""
    return fold("Today's example portfolio", f"{len(held)} shares in {len(sectors)} sectors, set on {day(last)}",
                body, open_=True, anchor="portfolio")


def section_since_april(conn) -> str:
    """What the example portfolio would have done, against the market and treasury bills: one chart, three numbers."""
    summary = {r["portfolio"]: r for r in q(conn, """select * from models.cse_bt_summary where method_version = %s
                                                      and policy = 'quarterly'""", NEW)}
    if FLAGSHIP[1] not in summary:
        return ""
    flag, mk, bills = summary[FLAGSHIP[1]], summary.get("market"), summary.get("bills")
    start, end = flag["start_date"], flag["end_date"]
    navs: dict[str, list] = defaultdict(list)
    for r in q(conn, """select session_date, portfolio, nav from models.cse_bt_nav where method_version = %s
                        and policy = 'quarterly' and portfolio in (%s, 'market', 'bills') order by session_date""",
               NEW, FLAGSHIP[1]):
        navs[r["portfolio"]].append((r["session_date"], r["nav"]))
    index = lambda pts: [(d, v / pts[0][1] * 100) for d, v in pts]
    chart = charts.lines([
        {"label": "The example portfolio", "points": index(navs[FLAGSHIP[1]]), "colour": charts.colour(0), "width": 2.6},
        {"label": "The share market (ASPI)", "points": index(navs["market"]), "colour": charts.MUTED, "width": 1.6,
         "dash": "6 4"},
        {"label": "Treasury bills", "points": index(navs["bills"]), "colour": charts.MUTED, "width": 1.6, "dash": "2 3"}],
        aria="Value of Rs 100 in each, from the start", fmt=lambda v: f"{v:.0f}", end_fmt=lambda v: f"{v - 100:+.1f}%",
        base=100)
    months = round((end - start).days / 30.4)
    body = f"""
<p>Rs 1 million in each, from {day(start)} (the first date the rules could run honestly) to {day(end)}, about
{months} months. The portfolio's value includes dividends and every cost of trading.</p>
{chart}
{tiles([("The example portfolio", signed(flag["total_return"]), f"largest fall {signed(flag['max_drawdown'])}"),
        ("The share market", signed(mk["total_return"] if mk else None),
         f"largest fall {signed(mk['max_drawdown'] if mk else None)}; prices only"),
        ("Treasury bills", signed(bills["total_return"] if bills else None), "no fall at all")])}
<div class="explain"><p><strong>What this shows, and what it does not.</strong> The portfolio swung less than the
market and fell less at its worst, which is what these rules are built to do. Over a few months, which way the market
went matters far more than how a portfolio was built, and treasury bills, which do not swing at all, returned more.
{months} months says almost nothing about future returns.</p></div>"""
    return fold("How it would have done since April", f"{signed(flag['total_return'])}, against {signed(mk['total_return'] if mk else None)} for the market and {signed(bills['total_return'] if bills else None)} for treasury bills",
                body, open_=True, anchor="since-april")


def section_rebalancing(conn) -> str:
    """How the portfolio is kept in shape: the owner asked whether it rebalances automatically, and how."""
    policy, port = FLAGSHIP
    events = q(conn, """select * from models.cse_bt_event where method_version = %s and policy = %s and portfolio = %s
                        order by session_date""", NEW, policy, port)
    reviews = [e for e in events if e["kind"] != "drift"]
    drifts = [e for e in events if e["kind"] == "drift"]
    if not reviews:
        return ""
    total_cost = sum(e["cost"] for e in events)
    costs = charts.donut([(f"{day(e['session_date'])}: {KIND.get(e['kind'], e['kind'])}", e["cost"]) for e in reviews]
                         + ([("Small adjustments between reviews", sum(e["cost"] for e in drifts))] if drifts else []),
                         aria="Trading costs since April, by occasion", centre=f"Rs {total_cost / 1000:,.1f}k",
                         centre_sub="in costs", keep_order=True)
    log = [[day(e["session_date"]), esc(KIND.get(e["kind"], e["kind"])),
            esc(", ".join(x.split(".")[0] for x in e["names_in"].split(",") if x) or "–"),
            esc(", ".join(x.split(".")[0] for x in e["names_out"].split(",") if x) or "–"),
            lkr(e["turnover"]), lkr(e["cost"])] for e in reviews]
    body = f"""
<h3>Does it rebalance automatically?</h3>
<p><b>In this lab, yes, on paper.</b> Every trading day the computer applies the rules to an imaginary Rs 1 million,
exactly as written, with no one deciding anything along the way:</p>
<ol class="steps">
<li><b>Four times a year, a review.</b> On the first trading day of January, April, July and October the rules are run
again on the latest prices. Shares may come in or go out, and every weight is brought back to its new target. A
share already in the portfolio stays unless it has clearly dropped down the rules' list, so small changes do not
cause trading.</li>
<li><b>In between, only if something drifts too far.</b> As prices move, each share's part of the portfolio drifts.
If one moves more than a quarter away from its target (or two percentage points), only that share is put back the
next day.</li>
<li><b>Every trade costs money.</b> Each change pays about 1.12 % of its value in brokerage and fees, only whole shares
are bought, and dividends and share splits are booked on the day they apply. Because of the costs, the rules trade
as little as they can: at a review they move the weights only as far as needed to stay within 1 % of the lowest
risk they can find.</li>
</ol>
<p><b>In real life, nothing trades by itself.</b> ZinvestIQ never looks after money or places orders. Someone following
rules like these would place the trades themselves through their own stockbroker on those dates, or a fund manager
would do it inside a fund.</p>
<h3>What it has cost so far</h3>
{costs}
<p class="small muted">{"More than half" if reviews[0]["cost"] > total_cost / 2 else "Part"} of the cost was the first
purchases. After that: {len(reviews) - 1} quarterly review{"" if len(reviews) == 2 else "s"}, and
{"no small adjustments" if not drifts else f"{len(drifts)} small adjustment{'' if len(drifts) == 1 else 's'}"} between
reviews.</p>
<details class="more"><summary>Every review in detail</summary>
{table(["Date", "Why", "Came in", "Went out", "Traded", "Cost"], log)}
</details>"""
    return fold("How the portfolio is kept in shape", "Reviewed four times a year; in between, only a share that drifts too far is put back",
                body, open_=True, anchor="rebalancing")
