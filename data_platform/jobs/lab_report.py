"""The owner's portfolio-lab report:  python -m data_platform.jobs.lab_report --out <file.html> [--version 1.1.0]

INTERNAL RESEARCH ONLY (decision 0023). The lab's outputs are unpublished; this job is the one way to read them. It
reads the database with the owner's own login (DATABASE_URL) and writes ONE self-contained HTML file (no scripts, no
external links or fonts) to a path OUTSIDE the repository; it refuses a path inside it, so a report can never be
committed by accident. Nothing here is advice: the portfolios are rules applied to estimates.

Contents: the latest estimate date (risk-free rate and its source, the assumed premium, the universe); the full
portfolios and the versions with 10 and 15 names (weights, risk, what binds, tracking error); the constrained
frontier; a comparison by number of names as in docs/plan-retail-features.md §6; the forward record; the caveats;
and three wording mock-ups for the lawyer (paths P1, P2, P3 of plan §5), clearly marked as such.
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

from ..core import db
from ..core import settings as settings_mod
from ..core.settings import REPO_ROOT
from ..models import registry
from ..models._lib import cse_optimize as opt
from ..models.cse_portfolio_lab import compute as lab_model
from . import lab_backtest_report as bt_report

SIZES = (25, 20, 15, 12, 10, 8, 6, 5)
KINDS = ("min_variance", "max_sharpe")
MIN_WEEKS_FOR_STATISTICS = 26          # the old tool showed no record statistics before 26 weeks


def esc(v) -> str:
    return html.escape(str(v))


def pct(v, digits=1) -> str:
    return "–" if v is None else f"{v * 100:.{digits}f}%"


def num(v, digits=3) -> str:
    return "–" if v is None else f"{v:.{digits}f}"


def lkr(v) -> str:
    return "–" if v is None else f"Rs {v:,.0f}"


def table(head: list[str], body: list[list], cls: str = "") -> str:
    th = "".join(f"<th>{esc(h)}</th>" for h in head)
    rows = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in body)
    return f'<table class="{cls}"><thead><tr>{th}</tr></thead><tbody>{rows}</tbody></table>'


# --- reading -----------------------------------------------------------------------------------------------------

def q(conn, sql: str, *params) -> list[dict]:
    return [dict(r) for r in conn.execute(sql, params)]


def latest(conn, version: str) -> dict | None:
    rows = q(conn, """select * from models.cse_lab_summary where method_version = %s and status <> 'waiting'
                      order by as_of desc limit 1""", version)
    return rows[0] if rows else None


def problem_at(conn, version: str, day: dt.date, notional: float, params: dict):
    """The day's optimisation problem, rebuilt from the stored estimates (as cse_portfolio_lab builds it)."""
    summary = q(conn, "select * from models.cse_risk_summary where method_version = %s and as_of = %s", version, day)[0]
    rows = q(conn, """select * from models.cse_risk_estimate where method_version = %s and as_of = %s
                      order by symbol""", version, day)
    weekly: dict[str, dict] = defaultdict(dict)
    for r in q(conn, """select series, week_end, weekly_return from models.cse_weekly_return
                        where method_version = %s and week_end between %s and %s""",
               version, summary["first_week"], summary["last_week"]):
        weekly[r["series"]][r["week_end"].isoformat()] = r["weekly_return"]
    cfg = {k: params[k] for k in ("max_weight", "max_sector_weight", "max_group_weight", "participation",
                                  "days_to_build")}
    cfg["notional_lkr"] = notional
    daily = None
    if params.get("covariance", "identity") == "daily":     # version 1.2.0: rebuilt from the daily returns
        tri: dict[str, dict] = defaultdict(dict)
        for r in q(conn, """select symbol, session_date, tri from models.cse_total_return where method_version = '1.0.0'
                            and session_date <= %s and symbol = any(%s)""", day, [r["symbol"] for r in rows]):
            tri[r["symbol"]][r["session_date"].isoformat()] = r["tri"]
        sessions = [r["session_date"].isoformat() for r in q(conn, """select session_date from cse.indices_daily_current
                    where index_code = 'ASI' and session_date <= %s order by session_date""", day)]
        daily = lab_model.Daily({k: pd.Series(v, dtype=float).sort_index() for k, v in tri.items()}, sessions,
                                int(params.get("daily_lags", 2)))
    prob, _ = lab_model.problem_of(summary, rows, weekly, cfg, daily)
    return summary, prob


# --- sections ------------------------------------------------------------------------------------------------------

def reason_kind(reason: str) -> str:
    """A reason without its numbers, so reasons can be counted by kind."""
    for prefix, kind in (("not an ordinary share", "not an ordinary share"), ("history", "history too short"),
                         ("traded on", "traded on too few sessions"), ("median daily turnover", "turnover too low"),
                         ("sector unclassified", "sector unclassified"), ("excluded", "excluded (private list)")):
        if reason.startswith(prefix):
            return kind
    return reason

def section_status(summary: dict, lab: dict, uni: list[dict], params: dict | None = None) -> str:
    reasons = defaultdict(int)
    for r in uni:
        if not r["included"]:
            reasons[reason_kind(r["reason"])] += 1
    rows = [[esc(k), v] for k, v in sorted(reasons.items(), key=lambda kv: -kv[1])]
    return f"""
<h2>Estimate date {esc(summary['as_of'])}</h2>
<ul>
<li>Universe: <b>{lab['n_universe']}</b> shares of {summary['n_securities']} securities listed; weekly returns
{esc(summary['first_week'])} to {esc(summary['last_week'])} ({summary['history_weeks']} weeks);
{"covariance from the daily returns over the same span, with two days of lagged covariances" if (params or {}).get("covariance") == "daily" else "covariance from the weekly returns"},
Ledoit-Wolf shrinkage {num(summary['shrinkage'])}.</li>
<li>Risk-free rate: <b>{pct(summary['risk_free'], 2)}</b> ({esc(summary['risk_free_source'])}).</li>
<li>Equity risk premium: <b>{pct(summary['equity_risk_premium'])}</b> &mdash; an <b>assumption</b>, used only for the
CAPM expected returns.</li>
<li>Market proxy: {esc(summary['market_proxy'])}. Liquidity caps computed for a portfolio of {lkr(lab['notional_lkr'])}.</li>
<li>Lab status: {esc(lab['status'])} &mdash; {esc(lab['message'])}</li>
</ul>
<h3>Left out of the universe, by reason</h3>{table(['Reason', 'Securities'], rows)}"""


def section_portfolios(conn, version: str, day: dt.date) -> str:
    ports = q(conn, """select * from models.cse_lab_portfolio where method_version = %s and as_of = %s
                       order by family, names_target nulls first, portfolio""", version, day)
    weights = defaultdict(list)
    for w in q(conn, """select * from models.cse_lab_weight where method_version = %s and as_of = %s
                        order by weight desc""", version, day):
        weights[w["portfolio"]].append(w)
    head = ["Portfolio", "Names", "Weights set on", "E[R]", "Volatility", "Sharpe", "Tracking error vs full",
            "What binds", "Note"]
    body = [[f"<b>{esc(opt.LABELS.get(p['portfolio']) or bt_report.LABELS.get(p['portfolio'], p['portfolio']))}</b>", p["n_names"] or "–",
             esc(p["formed_on"] or "–"), pct(p["expected_return"]), pct(p["volatility"]), num(p["sharpe"]),
             pct(p["tracking_error"]), esc(p["binding"] or ""), esc(p["message"] or "")] for p in ports]
    out = ["<h2>The portfolios</h2>", table(head, body)]
    for p in ports:
        ws = weights.get(p["portfolio"], [])
        if not ws or p["family"] == "full" and p["portfolio"] in ("equal_weight", "risk_parity"):
            continue
        rows = [[esc(w["symbol"]), pct(w["weight"], 2), esc(w["sector"] or ""), pct(w["risk_contribution"]),
                 "at cap" if w["at_cap"] else ""] for w in ws]
        label = opt.LABELS.get(p["portfolio"]) or bt_report.LABELS.get(p["portfolio"], p["portfolio"])
        out.append(f"<details class=\"more\"><summary>{esc(label)}: {len(ws)} names</summary>"
                   + table(["Share", "Weight", "Sector", "Share of risk", ""], rows, "small") + "</details>")
    return "\n".join(out)


FRONTIER_POINTS = [("min_variance", "Minimum variance", 2), ("max_sharpe", "Maximum Sharpe", 1),
                   ("risk_parity", "Risk parity", 3), ("equal_weight", "Equal weight", 4)]


def section_frontier(conn, version: str, day: dt.date) -> str:
    pts = q(conn, """select expected_return, volatility from models.cse_lab_frontier where method_version = %s
                     and as_of = %s order by point""", version, day)
    ports = {r["portfolio"]: r for r in q(conn, """select portfolio, expected_return, volatility from
                     models.cse_lab_portfolio where method_version = %s and as_of = %s and volatility is not null""",
                                          version, day)}
    if not pts:
        return "<h3>The trade-off between risk and expected return</h3><p>No frontier on this date.</p>"
    points = [{"label": label, "x": ports[k]["volatility"], "y": ports[k]["expected_return"],
               "colour": bt_report.charts.colour(c)} for k, label, c in FRONTIER_POINTS if k in ports]
    if "market" in ports:
        points.append({"label": "The market (ASPI)", "x": ports["market"]["volatility"],
                       "y": ports["market"]["expected_return"], "colour": bt_report.charts.MUTED})
    chart = bt_report.charts.frontier([(p["volatility"], p["expected_return"]) for p in pts], points,
                                      aria="Expected return against volatility for the full portfolios")
    return f"""<h3>The trade-off between risk and expected return</h3>
<p>Each point is one of the full portfolios on {esc(day)}. Further right, it swings more; higher up, it has a higher
expected return. The line is the best trade-off the rules' limits allow: no portfolio within the limits sits above
it. The expected returns come from an assumption (6 % a year above bills, scaled by each share's beta), so the
vertical position is only as good as that assumption; the horizontal one is measured.</p>
{chart}"""


def section_fewer_names(prob: opt.Problem, max_weight: float) -> str:
    """Plan §6's comparison on the day's estimates: the K largest names of the full portfolio, re-optimised with
    the cap max(10 %, 1.5/K) and the floor 0.5/K (a first formation: no buffer)."""
    full = opt.solve_full(prob)
    out = ["<h2>How much is lost with fewer names (plan §6 on today's estimates)</h2>"]
    for kind in KINDS:
        base = opt.stats(full[kind], prob)
        rows = [[f"Full ({int((full[kind] > 1e-6).sum())} names)", pct(base["volatility"]), num(base["sharpe"]),
                 "–"]]
        for k in SIZES:
            names = opt.retail_names(opt.ranking(full[kind], prob.symbols), k, None, 1.5)
            idx = [prob.symbols.index(s) for s in names]
            try:
                wk = opt.solve_retail(kind, opt.subproblem(prob, idx, opt.retail_cap(k, max_weight)),
                                      opt.retail_floor(k))
            except opt.Infeasible:
                rows.append([k, "not possible within the sector and group caps", "", ""])
                continue
            w = np.zeros(len(prob.symbols))
            w[idx] = wk
            s = opt.stats(w, prob)
            rows.append([k, pct(s["volatility"]),
                         f"{num(s['sharpe'])} ({s['sharpe'] / base['sharpe']:.0%} of full)" if base["sharpe"] else "–",
                         pct(opt.tracking_error(w, full[kind], prob.cov))])
        out.append(f"<h3>{esc(opt.LABELS[kind])}</h3>"
                   + table(["Names", "Volatility", "Sharpe", "Tracking error vs full"], rows))
    return "\n".join(out)


def section_record(conn, version: str) -> str:
    navs = q(conn, """select series, session_date, portfolio, nav from models.cse_lab_nav where method_version = %s
                      order by session_date""", version)
    if not navs:
        return ("<h2>Record</h2><p>No record yet for this version: it starts at the first run that finds valid "
                "model weights, and is never backfilled.</p>")
    by = defaultdict(list)
    for r in navs:
        by[(r["series"], r["portfolio"])].append(r)
    rows = []
    for (series, p), rs in sorted(by.items()):
        start, end = rs[0], rs[-1]
        weeks = (end["session_date"] - start["session_date"]).days / 7
        change = end["nav"] / start["nav"] - 1 if weeks >= MIN_WEEKS_FOR_STATISTICS else None
        rows.append([esc(series), esc(p), esc(start["session_date"]), esc(end["session_date"]), lkr(end["nav"]),
                     pct(change) if change is not None else f"not shown before {MIN_WEEKS_FOR_STATISTICS} weeks"])
    counts = q(conn, """select action, count(*) n, sum(cost) cost from models.cse_lab_trade where method_version = %s
                        group by action order by action""", version)
    crow = [[esc(c["action"]), c["n"], lkr(c["cost"])] for c in counts]
    return ("<h2>Forward record</h2><p>Each portfolio from its own start, whole shares, 1.12 % cost per side, "
            "corporate actions booked; append-only.</p>"
            + table(["Series", "Portfolio", "From", "To", "Value", "Change since start"], rows)
            + "<h3>Changes recorded</h3>" + table(["Kind", "Count", "Costs paid"], crow))


CAVEATS = """<h2>Read these with the numbers</h2><ul>
<li><b>In-sample estimates.</b> One year of weekly returns; expected returns from CAPM with an assumed 6 % premium.
With one year of data a Sharpe ratio's uncertainty is roughly &plusmn;1: differences of a few hundredths are noise.
Nothing here promises any return.</li>
<li><b>Maximum Sharpe is unstable.</b> One new week of data can change several of its largest names; the versions with
fewer names therefore change only at the half-yearly reviews, with a buffer, and their record includes costs.</li>
<li>The ASPI is a price index (no dividends); the CSE's own data are used under the source rules of decision 0009.</li>
<li>These are model portfolios computed by rules, for internal research. Nothing here is advice or an offer; none of
it may be published before the lawyer's view (decision 0010 point 6).</li></ul>"""


def section_mockups(ports: list[dict], weights: dict, day: dt.date) -> str:
    """Three wording mock-ups for the lawyer (plan §5): how the 15-name minimum-variance portfolio could appear under
    each path. Wording only; no instruction to anyone."""
    candidates = [x for x in ports if x["portfolio"].startswith("min_variance_") and x["status"] == "ok"]
    p = max(candidates, key=lambda x: x["names_target"]) if candidates else None   # 15 names, in the models
    if p is None:
        return "<h2>Mock-ups for the lawyer</h2><p>No 15-name portfolio on this date.</p>"
    k = p["names_target"]
    ws = sorted(weights.get(p["portfolio"], []), key=lambda w: -w["weight"])[:3]
    sample = ", ".join(f"{esc(w['symbol'])} {pct(w['weight'])}" for w in ws)
    banner = '<p class="mock">MOCK-UP FOR LEGAL REVIEW &mdash; NOT PUBLISHED &mdash; WORDING ONLY</p>'
    return f"""<h2>Mock-ups for the lawyer (plan §5)</h2>
<p>The same portfolio ({esc(p['portfolio'])}, set on {esc(p['formed_on'])}) as it might be worded under each path. The
lawyer decides which paths are open; none of these is in use.</p>
<div class="mockup">{banner}<h3>P1 &middot; Licensed investment adviser</h3>
<p><i>Model portfolio &ldquo;Minimum Variance {k}&rdquo;, prepared by [licensed adviser, SEC registration no.]. Composition at
the review of {esc(p['formed_on'])}: {sample}, &hellip; Estimated volatility {pct(p['volatility'])} a year.
Suitability, risk disclosures and the adviser's terms apply.</i></p>
<p class="note">Needs the SEC licence; the only path under which a portfolio could be presented as advice.</p></div>
<div class="mockup">{banner}<h3>P2 &middot; Published rules-based index</h3>
<p><i>ZinvestIQ CSE Minimum Variance {k} Index. Rules: the {k} largest constituents of the constrained minimum-variance
portfolio of the eligible universe, re-weighted with caps of {max(0.10, 1.5 / k):.0%} per share, 30 % per sector and 20 % per ownership
group, minimum weight {0.5 / k:.1%}, reconstituted on the first session of January and July. Reconstitution
of {esc(p['formed_on'])}: weight changes &mdash; for example {sample}. Index level and its history are reported as
calculated. This is an index, not a portfolio offered to anyone.</i></p>
<p class="note">Reports weight changes of an index under published rules, with no instruction to anyone.</p></div>
<div class="mockup">{banner}<h3>P3 &middot; A tool the user runs</h3>
<p><i>Portfolio constructor. Choose the number of names (10&ndash;25), the caps and the objective; the tool shows the
resulting weights and their estimated risk from public data. It does not ask for, store or use your holdings or
circumstances. Example output with {k} names and the default caps: {sample}, &hellip; estimated volatility
{pct(p['volatility'])}.</i></p>
<p class="note">The user sets every input; the output is a calculation, not a statement about what anyone should
do (decision 0010 point 4).</p></div>"""


STYLE = """:root{--bg:#f5f7fa;--surface:#fff;--surface-2:#edf1f6;--border:#dce2ea;--text:#111a2c;--muted:#55617a;
--accent:#1b4f9c;--accent-soft:#e7eefa;--gold:#c98500;--down:#b8392b;--warn-bg:#fdf3dc;--warn-text:#6b4a0e;
--series-1:#1b4f9c;--series-2:#c98500;--series-3:#00a39a;--series-4:#6250d6;--series-5:#c2477e;--other:#9aa5b5}
@media (prefers-color-scheme:dark){:root{--bg:#0b1220;--surface:#111a2b;--surface-2:#17223a;--border:#25324b;
--text:#e6ebf4;--muted:#9aa7bd;--accent:#8ab4f8;--accent-soft:#152748;--gold:#e0a83a;--down:#f08b7d;--warn-bg:#2e2613;
--warn-text:#ecd08f;--series-1:#4a8fe8;--series-2:#c98500;--series-3:#17a096;--series-4:#9085e9;--series-5:#d55181;
--other:#5d6b82}}
body{font:15px/1.55 system-ui,sans-serif;margin:24px auto;max-width:1000px;padding:0 16px;color:var(--text);
background:var(--bg)}a{color:var(--accent)}h1{font-size:26px}h2{font-size:20px;margin-top:32px}h3{font-size:16px}
table{border-collapse:collapse;margin:8px 0;background:var(--surface)}td,th{border:1px solid var(--border);
padding:4px 8px;text-align:left;vertical-align:top}th{background:var(--surface-2)}.small td,.small{font-size:13px}
.warn{background:var(--warn-bg);color:var(--warn-text);border-radius:8px;padding:8px 12px}
.mockup{border:2px dashed var(--down);border-radius:8px;padding:8px 14px;margin:14px 0}.mock{color:var(--down);font-weight:bold}
.note,.muted{color:var(--muted)}.note{font-size:13px}
.explain{background:var(--accent-soft);border-radius:8px;padding:8px 14px;margin:12px 0}
.lead{font-size:17px}.lab-intro ul{padding-left:20px}.lab-intro ul.three{list-style:none;padding:0;display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(230px,1fr))}.lab-intro ul.three li{border:1px solid var(--border);border-radius:10px;padding:14px;color:var(--muted)}.lab-intro ul.three li b{display:block;color:var(--text)}ol.steps li{margin-bottom:6px}
details.section{background:var(--surface);border:1px solid var(--border);border-radius:10px;margin:12px 0}
details.section>summary{list-style:none;cursor:pointer;padding:14px 18px;display:grid;grid-template-columns:1fr auto;gap:2px 12px}
details.section>summary::-webkit-details-marker{display:none}
details.section>summary .s-title{font-weight:600;font-size:18px}details.section>summary .s-sum{color:var(--muted);font-size:14px}
details.section>summary .s-chev{grid-column:2;grid-row:1/span 2;align-self:center}
details.section>summary .s-chev::before{content:"\\25BE";color:var(--muted)}details.section[open]>summary .s-chev::before{content:"\\25B4"}
details.section[open]>summary{border-bottom:1px solid var(--border)}details.section>.s-body{padding:12px 18px 18px}
details.more{margin:12px 0}details.more>summary{cursor:pointer;color:var(--accent);font-weight:600}
.tiles{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:10px;margin:12px 0}
.tile{background:var(--surface-2);border-radius:8px;padding:10px 12px;display:grid;gap:2px}
.tile .label{font-size:13px;color:var(--muted)}.tile .value{font-size:22px;font-weight:600}.tile .sub{font-size:13px;color:var(--muted)}
.donuts{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:8px 24px}""" + bt_report.charts.STYLE


def build(conn, version: str, params: dict | None = None) -> str:
    manifests = registry.load_all()
    params = {**manifests["cse_portfolio_lab"].version(version).parameters, **(params or {})}
    lab = latest(conn, version)
    parts = ["<h1>Portfolio lab &mdash; internal research report</h1>",
             (f'<p class="warn"><b>INTERNAL RESEARCH ONLY. Not for publication or distribution.</b> Version '
              f'{esc(version)} of the lab models; generated {dt.datetime.now(dt.UTC):%Y-%m-%d %H:%M} UTC. '
              f'Model portfolios wait for a lawyer&rsquo;s view before anything is published (decision 0010 point 6).'
              f'</p>')]
    parts.append(f"<style>{bt_report.charts.STYLE}</style>")   # in the body, so the owners' preview keeps it
    if lab is None:
        parts.append("<p>No estimate date with portfolios yet for this version (the estimates may still be waiting: "
                     "for a year of weekly returns, the private settings, or a published bill yield).</p>")
    else:
        bt_params = manifests["cse_lab_backtest"].current.parameters
        names = {r["symbol"]: r["name"] for r in q(conn, "select symbol, name from models.cse_security_reference "
                                                         "where name is not null")}
        parts.append(bt_report.section_intro())
        parts.append(bt_report.section_portfolio(conn, names))
        parts.append(bt_report.section_since_april(conn))
        parts.append(bt_report.section_rebalancing(conn))
        parts.append('<h2 class="deeper">Go deeper</h2><p class="muted">Each part below opens with a click. They '
                     "explain the rules, the evidence for them and the full workings, for anyone who wants the "
                     "detail.</p>")
        parts.append(bt_report.section_rules(bt_params))
        parts.append(bt_report.section_evidence(conn))
        parts.append(bt_report.section_compare(conn))
        day = lab["as_of"]
        summary, prob = problem_at(conn, version, day, lab["notional_lkr"], params)
        uni = q(conn, "select * from models.cse_risk_universe where method_version = %s and as_of = %s", version, day)
        ports = q(conn, "select * from models.cse_lab_portfolio where method_version = %s and as_of = %s",
                  version, day)
        weights = defaultdict(list)
        for w in q(conn, "select * from models.cse_lab_weight where method_version = %s and as_of = %s", version, day):
            weights[w["portfolio"]].append(w)
        workings = [section_status(summary, lab, uni, params), section_portfolios(conn, version, day),
                    section_frontier(conn, version, day)]
        if lab["status"] == "ok":
            workings.append(section_fewer_names(prob, params["max_weight"]))
        workings += [section_record(conn, version), CAVEATS]
        body = "".join(workings).replace("<h2>", "<h3>").replace("</h2>", "</h3>")
        parts.append(bt_report.fold("For specialists: the full workings",
                                    f"Every portfolio, the frontier, the effect of fewer names and the forward record, "
                                    f"on {esc(day)} (lab version {esc(version)})", body, anchor="workings"))
        parts.append(bt_report.fold("Wording mock-ups for the lawyer",
                                    "How the example could be worded under each of the three publishing paths "
                                    "(internal, not in use)",
                                    section_mockups(ports, weights, day).replace("<h2>", "<h3>").replace("</h2>", "</h3>"),
                                    anchor="mockups"))
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" '
            f'content="width=device-width,initial-scale=1"><title>Portfolio lab report</title>'
            f'<style>{STYLE}</style></head><body>{"".join(parts)}</body></html>\n')


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", type=Path, required=True, help="the HTML file to write (outside the repository)")
    ap.add_argument("--version", help="the lab models' version (default: the current one)")
    args = ap.parse_args(argv)
    out = args.out.resolve()
    if out == REPO_ROOT or REPO_ROOT in out.parents:
        print(f"refusing to write inside the repository ({REPO_ROOT}): the report contains unpublished data")
        return 2
    version = args.version or registry.load_all()["cse_portfolio_lab"].current.method_version
    conn = db.connect(settings_mod.load().database_url)
    text = build(conn, version)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text)
    print(f"wrote {out} ({len(text):,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
