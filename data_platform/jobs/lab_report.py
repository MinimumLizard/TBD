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

from ..core import db, settings as settings_mod
from ..core.settings import REPO_ROOT
from ..models import registry
from ..models._lib import cse_optimize as opt
from ..models.cse_portfolio_lab import compute as lab_model

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
    prob, _ = lab_model.problem_of(summary, rows, weekly, cfg)
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

def section_status(summary: dict, lab: dict, uni: list[dict]) -> str:
    reasons = defaultdict(int)
    for r in uni:
        if not r["included"]:
            reasons[reason_kind(r["reason"])] += 1
    rows = [[esc(k), v] for k, v in sorted(reasons.items(), key=lambda kv: -kv[1])]
    return f"""
<h2>Estimate date {esc(summary['as_of'])}</h2>
<ul>
<li>Universe: <b>{lab['n_universe']}</b> shares of {summary['n_securities']} securities listed; weekly returns
{esc(summary['first_week'])} to {esc(summary['last_week'])} ({summary['history_weeks']} weeks); Ledoit-Wolf shrinkage
{num(summary['shrinkage'])}.</li>
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
    body = [[f"<b>{esc(opt.LABELS.get(p['portfolio'], p['portfolio']))}</b>", p["n_names"] or "–",
             esc(p["formed_on"] or "–"), pct(p["expected_return"]), pct(p["volatility"]), num(p["sharpe"]),
             pct(p["tracking_error"]), esc(p["binding"] or ""), esc(p["message"] or "")] for p in ports]
    out = ["<h2>The portfolios</h2>", table(head, body)]
    for p in ports:
        ws = weights.get(p["portfolio"], [])
        if not ws or p["family"] == "full" and p["portfolio"] in ("equal_weight", "risk_parity"):
            continue
        rows = [[esc(w["symbol"]), pct(w["weight"], 2), esc(w["sector"] or ""), pct(w["risk_contribution"]),
                 "at cap" if w["at_cap"] else ""] for w in ws]
        out.append(f"<details><summary>{esc(p['portfolio'])}: {len(ws)} names</summary>"
                   + table(["Share", "Weight", "Sector", "Share of risk", ""], rows, "small") + "</details>")
    return "\n".join(out)


def section_frontier(conn, version: str, day: dt.date) -> str:
    pts = q(conn, """select expected_return, volatility from models.cse_lab_frontier where method_version = %s
                     and as_of = %s order by point""", version, day)
    ports = q(conn, """select portfolio, expected_return, volatility from models.cse_lab_portfolio
                       where method_version = %s and as_of = %s and volatility is not null""", version, day)
    if not pts:
        return "<h2>Frontier</h2><p>No frontier on this date.</p>"
    xs = [p["volatility"] for p in pts + ports]
    ys = [p["expected_return"] for p in pts + ports]
    x0, x1, y0, y1 = min(xs) * 0.95, max(xs) * 1.05, min(ys) * 0.97, max(ys) * 1.03
    W, H, M = 640, 360, 50
    sx = lambda v: M + (v - x0) / (x1 - x0) * (W - 2 * M)  # noqa: E731
    sy = lambda v: H - M - (v - y0) / (y1 - y0) * (H - 2 * M)  # noqa: E731
    line = " ".join(f"{sx(p['volatility']):.1f},{sy(p['expected_return']):.1f}" for p in pts)
    dots = "".join(f'<circle cx="{sx(p["volatility"]):.1f}" cy="{sy(p["expected_return"]):.1f}" r="4"/>'
                   f'<text x="{sx(p["volatility"]) + 6:.1f}" y="{sy(p["expected_return"]) - 6:.1f}">'
                   f'{esc(p["portfolio"])}</text>' for p in ports)
    ticks = "".join(f'<text x="{sx(v):.1f}" y="{H - M + 18}" text-anchor="middle">{v * 100:.0f}%</text>'
                    for v in np.linspace(x0, x1, 5))
    ticks += "".join(f'<text x="{M - 8}" y="{sy(v) + 4:.1f}" text-anchor="end">{v * 100:.1f}%</text>'
                     for v in np.linspace(y0, y1, 5))
    return f"""<h2>Constrained efficient frontier</h2>
<svg viewBox="0 0 {W} {H}" role="img" aria-label="Frontier: expected return against volatility">
<line x1="{M}" y1="{H - M}" x2="{W - M}" y2="{H - M}" class="axis"/><line x1="{M}" y1="{M}" x2="{M}" y2="{H - M}" class="axis"/>
<polyline points="{line}" class="frontier"/>{dots}{ticks}
<text x="{W / 2}" y="{H - 8}" text-anchor="middle">Estimated volatility (a year)</text>
<text x="14" y="{H / 2}" transform="rotate(-90 14 {H / 2})" text-anchor="middle">CAPM expected return</text></svg>"""


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
fewer names therefore change only on the quarterly calendar, with a buffer, and their record includes costs.</li>
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
the quarterly review of {esc(p['formed_on'])}: {sample}, &hellip; Estimated volatility {pct(p['volatility'])} a year.
Suitability, risk disclosures and the adviser's terms apply.</i></p>
<p class="note">Needs the SEC licence; the only path under which a portfolio could be presented as advice.</p></div>
<div class="mockup">{banner}<h3>P2 &middot; Published rules-based index</h3>
<p><i>ZinvestIQ CSE Minimum Variance {k} Index. Rules: the {k} largest constituents of the constrained minimum-variance
portfolio of the eligible universe, re-weighted with caps of {max(0.10, 1.5 / k):.0%} per share, 30 % per sector and 20 % per ownership
group, minimum weight {0.5 / k:.1%}, reconstituted on the first session of January, April, July and October. Reconstitution
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


STYLE = """body{font:15px/1.5 system-ui,sans-serif;margin:24px auto;max-width:1000px;padding:0 16px;color:#1d2433;
background:#fff}h1{font-size:24px}h2{font-size:19px;margin-top:32px;border-bottom:1px solid #d8dde6}
table{border-collapse:collapse;margin:8px 0}td,th{border:1px solid #d8dde6;padding:3px 8px;text-align:left}
th{background:#f2f4f8}.small td{font-size:13px}.warn{background:#fff3cd;border:1px solid #e0c060;padding:8px 12px}
.mockup{border:2px dashed #b03030;padding:8px 14px;margin:14px 0}.mock{color:#b03030;font-weight:bold}
.note{color:#555;font-size:13px}svg{width:100%;max-width:640px;font-size:11px}.axis{stroke:#888}
.frontier{fill:none;stroke:#2a5db0;stroke-width:2}circle{fill:#b05a2a}"""


def build(conn, version: str, params: dict | None = None) -> str:
    manifests = registry.load_all()
    params = {**manifests["cse_portfolio_lab"].version(version).parameters, **(params or {})}
    lab = latest(conn, version)
    parts = [f"<h1>Portfolio lab &mdash; internal research report</h1>"
             f'<p class="warn"><b>INTERNAL RESEARCH ONLY. Not for publication or distribution.</b> Version '
             f'{esc(version)} of the lab models; generated {dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M} UTC. '
             f'Model portfolios wait for a lawyer&rsquo;s view before anything is published (decision 0010 point 6).'
             f'</p>']
    if lab is None:
        parts.append("<p>No estimate date with portfolios yet for this version (the estimates may still be waiting: "
                     "for a year of weekly returns, the private settings, or a published bill yield).</p>")
    else:
        day = lab["as_of"]
        summary, prob = problem_at(conn, version, day, lab["notional_lkr"], params)
        uni = q(conn, "select * from models.cse_risk_universe where method_version = %s and as_of = %s", version, day)
        parts.append(section_status(summary, lab, uni))
        parts.append(section_portfolios(conn, version, day))
        parts.append(section_frontier(conn, version, day))
        if lab["status"] == "ok":
            parts.append(section_fewer_names(prob, params["max_weight"]))
        ports = q(conn, "select * from models.cse_lab_portfolio where method_version = %s and as_of = %s",
                  version, day)
        weights = defaultdict(list)
        for w in q(conn, "select * from models.cse_lab_weight where method_version = %s and as_of = %s", version, day):
            weights[w["portfolio"]].append(w)
        parts.append(section_record(conn, version))
        parts.append(CAVEATS)
        parts.append(section_mockups(ports, weights, day))
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
