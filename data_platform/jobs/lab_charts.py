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


OTHER = "var(--other,#9aa5b5)"          # the "Other" slice of a pie: a neutral, never a sixth hue


def donut(slices: list[tuple[str, float]], *, aria: str, centre: str = "", centre_sub: str = "",
          size: int = 220, max_slices: int = 5, other_label: str = "Other", keep_order: bool = False) -> str:
    """A ring chart of parts of one whole (decision 0025: the owner asked for pie charts).

    At most `max_slices` named slices, in the chart colours' fixed order, largest first (or as given, with
    `keep_order`, for parts that have an order of their own, such as dates); the rest are folded into one
    neutral "Other" slice, so a colour always means one named part. Slices are separated by a thin gap in the page's
    own colour. A legend beside the ring names every slice with its share, so the reading never depends on colour
    alone; each slice also carries a <title>, which browsers show on hover."""
    items = [(label, float(v)) for label, v in slices if v and v > 0]
    if not keep_order:
        items.sort(key=lambda x: -x[1])
    if not items:
        return ""
    total = sum(v for _, v in items)
    shown = items[:max_slices]
    rest = items[max_slices:]
    if rest:
        shown.append((f"{other_label} ({len(rest)})" if len(rest) > 1 else rest[0][0], sum(v for _, v in rest)))
    colours = [colour(i) for i in range(min(len(shown), len(SERIES)))]
    if rest:
        colours = colours[:len(shown) - 1] + [OTHER]
    r_out, r_in = size / 2 - 4, size / 2 - 4 - size * 0.17
    cx = cy = size / 2
    parts, angle = [], -math.pi / 2
    for (label, v), c in zip(shown, colours):
        sweep = v / total * 2 * math.pi
        a0, a1 = angle, angle + sweep
        if sweep >= 2 * math.pi - 1e-9:            # one slice: a full ring
            parts.append(f'<circle cx="{cx}" cy="{cy}" r="{(r_out + r_in) / 2:.1f}" fill="none" '
                         f'style="stroke:{c}" stroke-width="{r_out - r_in:.1f}"><title>{esc(label)}: 100%</title></circle>')
        else:
            large = 1 if sweep > math.pi else 0
            pt = lambda r, a: f"{cx + r * math.cos(a):.2f},{cy + r * math.sin(a):.2f}"
            d = (f"M{pt(r_out, a0)} A{r_out:.1f},{r_out:.1f} 0 {large} 1 {pt(r_out, a1)} "
                 f"L{pt(r_in, a1)} A{r_in:.1f},{r_in:.1f} 0 {large} 0 {pt(r_in, a0)} Z")
            parts.append(f'<path d="{d}" style="fill:{c};stroke:var(--surface,#fff)" stroke-width="2" '
                         f'stroke-linejoin="round"><title>{esc(label)}: {v / total:.1%}</title></path>')
        angle = a1
    if centre:
        parts.append(f'<text class="val big" x="{cx}" y="{cy + (2 if centre_sub else 7)}" text-anchor="middle">{esc(centre)}</text>')
    if centre_sub:
        parts.append(f'<text x="{cx}" y="{cy + 20}" text-anchor="middle">{esc(centre_sub)}</text>')
    legend = "".join(f'<li><i style="background:{c}"></i><span class="lbl">{esc(label)}</span>'
                     f'<span class="pc">{v / total:.0%}</span></li>' for (label, v), c in zip(shown, colours))
    return (f'<figure class="lab-donut"><svg viewBox="0 0 {size} {size}" width="{size}" height="{size}" role="img" '
            f'aria-label="{esc(aria)}">{"".join(parts)}</svg><ul class="donut-legend">{legend}</ul></figure>')


def frontier(line: list[tuple[float, float]], points: list[dict], *, aria: str, height: int = 340, note: str = "") -> str:
    """Expected return against volatility: the frontier as a line, each portfolio as a labelled point.
    points: {label, x, y, colour}. Axis text in the page's muted ink; point labels in its main ink."""
    if not line and not points:
        return ""
    xs = [x for x, _ in line] + [p["x"] for p in points]
    ys = [y for _, y in line] + [p["y"] for p in points]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    px, py = (x1 - x0) * 0.08 or 0.01, (y1 - y0) * 0.12 or 0.01
    x0, x1, y0, y1 = x0 - px, x1 + px, y0 - py, y1 + py
    left, right, top, bottom = 52, 120, 14, 40
    X = lambda v: left + (v - x0) / (x1 - x0) * (W - left - right)
    Y = lambda v: top + (y1 - v) / (y1 - y0) * (height - top - bottom)
    parts = []
    for v in _ticks(y0, y1):
        parts.append(f'<line x1="{left}" x2="{W - right}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" class="grid"/>'
                     f'<text x="{left - 6}" y="{Y(v) + 4:.1f}" text-anchor="end">{v * 100:.0f}%</text>')
    for v in _ticks(x0, x1):
        parts.append(f'<text x="{X(v):.1f}" y="{height - bottom + 16}" text-anchor="middle">{v * 100:.0f}%</text>')
    parts.append(f'<text x="{(left + W - right) / 2:.0f}" y="{height - 6}" text-anchor="middle">'
                 f'How much it swings (volatility, a year)</text>')
    parts.append(f'<text x="12" y="{(top + height - bottom) / 2:.0f}" transform="rotate(-90 12 {(top + height - bottom) / 2:.0f})" '
                 f'text-anchor="middle">Expected return (an assumption)</text>')
    if line:
        path = " ".join(f"{'M' if i == 0 else 'L'}{X(x):.1f},{Y(y):.1f}" for i, (x, y) in enumerate(line))
        parts.append(f'<path d="{path}" fill="none" style="stroke:{colour(0)}" stroke-width="2.4">'
                     f'<title>The best trade-off the rules allow</title></path>')
    placed: list[float] = []
    for p in sorted(points, key=lambda p: Y(p["y"])):
        ly = Y(p["y"]) + 4
        for q_ in placed:                       # keep labels from sitting on each other
            if abs(ly - q_) < 13:
                ly = q_ + 13
        placed.append(ly)
        parts.append(f'<circle cx="{X(p["x"]):.1f}" cy="{Y(p["y"]):.1f}" r="5.5" '
                     f'style="fill:{p["colour"]};stroke:var(--surface,#fff)" stroke-width="2">'
                     f'<title>{esc(p["label"])}: {p["x"]:.1%} volatility, {p["y"]:.1%} expected return</title></circle>'
                     f'<text class="val" x="{X(p["x"]) + 9:.1f}" y="{ly:.1f}">{esc(p["label"])}</text>')
    legend = [("The best trade-off the rules allow", colour(0), "line")]
    return _figure("".join(parts), legend, aria, height, note)


STYLE = (".lab-chart{margin:14px 0}.lab-chart svg{width:100%;max-width:100%;font-size:11px}"
         ".lab-chart text{fill:var(--muted,#55617a)}.lab-chart text.val{fill:var(--text,#111a2c)}"
         ".lab-chart .grid{stroke:var(--border,#dce2ea)}.lab-chart .base{stroke:var(--muted,#55617a);stroke-dasharray:3 3}"
         ".lab-chart figcaption{display:flex;flex-wrap:wrap;gap:4px 16px;font-size:12px;color:var(--muted,#55617a)}"
         ".lab-chart .lg i{display:inline-block;width:14px;height:0;margin-right:6px;vertical-align:middle;"
         "border-top:3px solid transparent}.lab-chart .lg i.line{height:3px;border:0}"
         ".lab-chart .lg i.bar{height:9px;width:9px;border:0;border-radius:2px}"
         ".lab-chart .lg i.dash{border-top-style:dashed;background:none}"
         ".lab-chart .lg i.dot{border-top-style:dotted;background:none}"
         ".lab-donut{display:flex;flex-wrap:wrap;align-items:center;gap:12px 24px;margin:8px 0}"
         ".lab-donut svg{flex:none;max-width:100%;height:auto}.lab-donut text{fill:var(--muted,#55617a);font-size:12px}"
         ".lab-donut text.val{fill:var(--text,#111a2c)}.lab-donut text.big{font-size:22px;font-weight:600}"
         ".donut-legend{list-style:none;margin:0;padding:0;display:grid;gap:6px;min-width:200px;font-size:14px}"
         ".donut-legend li{display:grid;grid-template-columns:12px 1fr auto;gap:8px;align-items:center}"
         ".donut-legend i{width:12px;height:12px;border-radius:3px}.donut-legend .pc{font-variant-numeric:tabular-nums;"
         "color:var(--muted,#55617a)}")
