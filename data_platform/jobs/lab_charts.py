"""Charts for the owner's lab report (jobs/lab_report.py): inline SVG, no scripts, so the report reads the same as a
file and inside the owners' preview. Colours are the site's chart colours (web/app/globals.css: --series-1..5, in
their fixed order, checked for colour-blind separation), read from the page when it defines them and falling back to
the light palette. Reference series (the market, treasury bills) are drawn in the muted ink, dashed, so a colour
always means one of the portfolios. Every mark carries a <title>, which browsers show on hover.

Text is drawn in the page's ink, never in a series colour; two series or more always get a legend; lines also carry
their last value at the right-hand end.
"""
from __future__ import annotations

import datetime as dt
import html
import math

SERIES = ["#1b4f9c", "#c98500", "#00a39a", "#6250d6", "#c2477e"]
MUTED = "var(--muted,#55617a)"
W = 760


def colour(i: int) -> str:
    return f"var(--series-{i + 1},{SERIES[i]})"


def esc(v) -> str:
    return html.escape(str(v))


def _figure(svg: str, legend: list[tuple[str, str, str]], aria: str, height: int, note: str = "") -> str:
    """legend: (label, colour, kind) with kind line | dash | bar."""
    items = "".join(
        f'<span class="lg"><i class="{kind}" style="{"border-color" if kind in ("dash", "dot") else "background"}:{c}"></i>{esc(label)}</span>'
        for label, c, kind in legend)
    cap = f"<figcaption>{items}</figcaption>" if items else ""
    extra = f'<p class="small muted">{note}</p>' if note else ""
    return (f'<figure class="lab-chart"><svg viewBox="0 0 {W} {height}" role="img" aria-label="{esc(aria)}">{svg}</svg>'
            f'{cap}{extra}</figure>')


def _ticks(lo: float, hi: float, target: int = 5) -> list[float]:
    span = max(hi - lo, 1e-9)
    raw = span / target
    mag = 10 ** math.floor(math.log10(raw))
    step = next(s * mag for s in (1, 2, 2.5, 5, 10) if s * mag >= raw)
    first = math.ceil(lo / step) * step
    out, v = [], first
    while v <= hi + 1e-9:
        out.append(round(v, 10))
        v += step
    return out


def lines(series: list[dict], *, aria: str, fmt, end_fmt=None, height: int = 300, base: float | None = None,
          note: str = "") -> str:
    """Lines over time. series: {label, points: [(date, value)], colour, width?, dash?}. `base` draws a reference
    level (100 for an index, 0 for a fall from a peak). Each line carries its last value at its right-hand end."""
    series = [s for s in series if s["points"]]
    if not series:
        return ""
    end_fmt = end_fmt or fmt
    dates = sorted({d for s in series for d, _ in s["points"]})
    lo = min(v for s in series for _, v in s["points"])
    hi = max(v for s in series for _, v in s["points"])
    if base is not None:
        lo, hi = min(lo, base), max(hi, base)
    pad = (hi - lo) * 0.06 or 1
    lo, hi = lo - pad, hi + pad
    left, right, top, bottom = 46, 64, 12, 26
    x0, x1 = dates[0].toordinal(), dates[-1].toordinal()
    X = lambda d: left + (d.toordinal() - x0) / max(x1 - x0, 1) * (W - left - right)
    Y = lambda v: top + (hi - v) / (hi - lo) * (height - top - bottom)
    parts = []
    for v in _ticks(lo, hi):
        parts.append(f'<line x1="{left}" x2="{W - right}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" class="grid"/>'
                     f'<text x="{left - 6}" y="{Y(v) + 4:.1f}" text-anchor="end">{esc(fmt(v))}</text>')
    if base is not None:
        parts.append(f'<line x1="{left}" x2="{W - right}" y1="{Y(base):.1f}" y2="{Y(base):.1f}" class="base"/>')
    for y, m in sorted({(d.year, d.month) for d in dates}):
        first = min(d for d in dates if (d.year, d.month) == (y, m))
        if X(first) < W - right - 12:
            parts.append(f'<text x="{X(first):.1f}" y="{height - 8}" text-anchor="middle">{dt.date(y, m, 1):%b}</text>')
    ends = []
    for s in series:
        path = " ".join(f"{'M' if i == 0 else 'L'}{X(d):.1f},{Y(v):.1f}" for i, (d, v) in enumerate(s["points"]))
        dash = f' stroke-dasharray="{s["dash"]}"' if s.get("dash") else ""
        last = s["points"][-1][1]
        parts.append(f'<path d="{path}" fill="none" style="stroke:{s["colour"]}" stroke-width="{s.get("width", 2)}" '
                     f'stroke-linejoin="round"{dash}><title>{esc(s["label"])}: {esc(end_fmt(last))}</title></path>')
        ends.append([Y(last), end_fmt(last), s["colour"]])
    ends.sort(key=lambda e: e[0])
    for i in range(1, len(ends)):                       # keep the end labels from sitting on each other
        ends[i][0] = max(ends[i][0], ends[i - 1][0] + 12)
    for y, text, c in ends:
        parts.append(f'<circle cx="{W - right + 5:.1f}" cy="{y - 3.5:.1f}" r="3" style="fill:{c}"/>'
                     f'<text class="val" x="{W - right + 11}" y="{y:.1f}">{esc(text)}</text>')
    kind = lambda s: "line" if not s.get("dash") else "dot" if int(s["dash"].split()[0]) <= 2 else "dash"
    legend = [(s["label"], s["colour"], kind(s)) for s in series]
    return _figure("".join(parts), legend, aria, height, note)


def bars(rows: list[dict], *, aria: str, fmt, names: list[tuple[str, str]], refs: list[tuple[float, str]] = (),
         label_width: int = 210, note: str = "") -> str:
    """Horizontal bars, one row per label. rows: {label, values: [..]} with one value per entry of `names`
    ((legend label, colour)); a missing value is None. `refs`: vertical reference lines (value, label)."""
    rows = [r for r in rows if any(v is not None for v in r["values"])]
    if not rows:
        return ""
    k = len(names)
    bar, gap, row_gap = 10, 2, 10
    row_h = k * bar + (k - 1) * gap + row_gap
    top, bottom, right = (22 if refs else 8), 22, 54
    height = top + len(rows) * row_h + bottom
    hi = max([v for r in rows for v in r["values"] if v is not None] + [v for v, _ in refs]) * 1.05
    lo = min([0.0] + [v for r in rows for v in r["values"] if v is not None])
    X = lambda v: label_width + (v - lo) / (hi - lo) * (W - label_width - right)
    parts = []
    for v in _ticks(lo, hi, 5):
        parts.append(f'<line x1="{X(v):.1f}" x2="{X(v):.1f}" y1="{top}" y2="{height - bottom}" class="grid"/>'
                     f'<text x="{X(v):.1f}" y="{height - 6}" text-anchor="middle">{esc(fmt(v))}</text>')
    for i, r in enumerate(rows):
        y = top + i * row_h
        parts.append(f'<text class="val" x="{label_width - 8}" y="{y + (row_h - row_gap) / 2 + 4:.1f}" text-anchor="end">'
                     f'{esc(r["label"])}</text>')
        for j, v in enumerate(r["values"]):
            if v is None:
                continue
            yy = y + j * (bar + gap)
            x_a, x_b = sorted((X(0.0), X(v)))
            parts.append(f'<rect x="{x_a:.1f}" y="{yy}" width="{max(x_b - x_a, 1):.1f}" height="{bar}" rx="3" '
                         f'style="fill:{names[j][1]}"><title>{esc(r["label"])}, {esc(names[j][0])}: {esc(fmt(v))}</title></rect>'
                         f'<text x="{x_b + 5:.1f}" y="{yy + bar - 1}">{esc(fmt(v))}</text>')
    for v, label in refs:
        parts.append(f'<line x1="{X(v):.1f}" x2="{X(v):.1f}" y1="{top - 4}" y2="{height - bottom}" class="base"/>'
                     f'<text x="{X(v):.1f}" y="{top - 8}" text-anchor="middle">{esc(label)}</text>')
    legend = [(n, c, "bar") for n, c in names] if k > 1 else []
    return _figure("".join(parts), legend, aria, height, note)


STYLE = (".lab-chart{margin:14px 0}.lab-chart svg{width:100%;max-width:100%;font-size:11px}"
         ".lab-chart text{fill:var(--muted,#55617a)}.lab-chart text.val{fill:var(--text,#111a2c)}"
         ".lab-chart .grid{stroke:var(--border,#dce2ea)}.lab-chart .base{stroke:var(--muted,#55617a);stroke-dasharray:3 3}"
         ".lab-chart figcaption{display:flex;flex-wrap:wrap;gap:4px 16px;font-size:12px;color:var(--muted,#55617a)}"
         ".lab-chart .lg i{display:inline-block;width:14px;height:0;margin-right:6px;vertical-align:middle;"
         "border-top:3px solid transparent}.lab-chart .lg i.line{height:3px;border:0}"
         ".lab-chart .lg i.bar{height:9px;width:9px;border:0;border-radius:2px}"
         ".lab-chart .lg i.dash{border-top-style:dashed;background:none}"
         ".lab-chart .lg i.dot{border-top-style:dotted;background:none}")
