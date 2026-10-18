"""lk_savings_compare: what Rs 100,000 grew to in a 12-month fixed deposit and in 12-month treasury bills, before and
after tax, and after inflation, for every start month and length of time. Education only: no instrument is
presented as preferable; the outputs are counts and ranges (METHOD.md).

Inputs are the CBSL's monthly interest-rate table (4.04) and the DCS's CCPI, as published. The model's own choices,
all in the manifest's parameters and explained in METHOD.md:

  * the deposit rate: AWNFDR (new fixed deposits) where the CBSL publishes it (from April 2014), else AWFDR (all
    outstanding fixed deposits), flagged on every row that uses it;
  * the bill yield: the 12-month primary market yield. From May 2002 to March 2018 the CBSL printed it after a 10%
    withholding tax; the tax is added back so both instruments are compared before tax;
  * tax on deposits: the advance income tax in force on the date the interest is paid (5% from 2023-01-01, 10% from
    2025-04-01; none modelled before 2023);
  * inflation: the CCPI, linked across its base years at the first month of each newer base, on the 2002 base.

Point in time: a row for a start month and horizon uses only facts dated up to its end month, so it never changes
when later months arrive (unless the CBSL or DCS revise a figure it used).
"""
from __future__ import annotations

import datetime as dt
import statistics
from dataclasses import dataclass

INSTRUMENTS = ("fd", "tbill")
BASES = {"fd": ("nominal", "nominal_after_tax", "real", "real_after_tax"), "tbill": ("nominal", "real")}


def add_months(d: dt.date, n: int) -> dt.date:
    k = d.year * 12 + d.month - 1 + n
    return dt.date(k // 12, k % 12 + 1, 1)


def _day(v) -> dt.date:
    return v if isinstance(v, dt.date) else dt.date.fromisoformat(str(v)[:10])


def rate_in_force(schedule: list[dict], day: dt.date) -> float:
    """The percentage in force on `day` from a schedule [{from: date, pct: number}, ...] (0 before the first)."""
    pct = 0.0
    for step in sorted(schedule, key=lambda s: _day(s["from"])):
        if _day(step["from"]) <= day:
            pct = float(step["pct"])
    return pct


def in_window(window: dict | None, day: dt.date) -> bool:
    return bool(window) and _day(window["from"]) <= day <= _day(window["to"])


# --- the CCPI across base years -----------------------------------------------------------------------------------

@dataclass(frozen=True)
class Link:
    newer: str
    older: str
    month: dt.date          # the first month of the newer base: from here on, the newer base is used
    factor: float           # older / newer in that month


def link_cpi(by_base: dict[str, dict[dt.date, float]], order: list[str]) -> tuple[dict[dt.date, tuple[float, str]], list[Link]]:
    """Link the bases, oldest first in `order`, into one series on the oldest base.

    Each month takes the newest base that covers it. A newer base is joined at its first month L: its figures are
    multiplied by older[L] / newer[L], so the series is continuous at L and keeps each base's own month-to-month
    changes. Expressing the result on the OLDEST base means a future base year rescales nothing already published.
    Returns ({month: (value, base used)}, the links)."""
    bases = [b for b in order if by_base.get(b)]
    if not bases:
        return {}, []
    out: dict[dt.date, tuple[float, str]] = {m: (v, bases[0]) for m, v in by_base[bases[0]].items()}
    links, scale = [], 1.0
    for older, newer in zip(bases, bases[1:]):
        start = min(by_base[newer])
        if start not in by_base[older]:
            raise ValueError(f"CCPI base {newer} starts {start:%Y-%m}, which base {older} does not cover: "
                             "the bases do not overlap, so they cannot be linked")
        factor = by_base[older][start] / by_base[newer][start]
        scale *= factor
        links.append(Link(newer, older, start, factor))
        for m in [m for m in out if m >= start]:
            del out[m]
        for m, v in by_base[newer].items():
            out[m] = (v * scale, newer)
    return dict(sorted(out.items())), links


# --- the monthly inputs -------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Month:
    month: dt.date
    fd_rate: float | None          # percent per annum
    fd_series: str | None
    bill_published: float | None
    bill_rate: float | None        # before tax
    cpi: float | None
    cpi_base: str | None
    fd_tax_pct: float              # advance income tax on deposit interest paid in this month


def monthly_inputs(rates: dict[str, dict[dt.date, float]], cpi: dict[dt.date, tuple[float, str]], params: dict) -> list[Month]:
    months = sorted(set().union(*(rates.get(s, {}) for s in params["fd_series_order"]),
                                rates.get(params["bill_series"], {}), cpi))
    out = []
    gross_up = params.get("bill_withholding_added_back")
    for m in months:
        fd = next(((rates[s][m], s) for s in params["fd_series_order"] if m in rates.get(s, {})), (None, None))
        published = rates.get(params["bill_series"], {}).get(m)
        bill = published
        if bill is not None and in_window(gross_up, m):
            bill = published / (1 - float(gross_up["pct"]) / 100)
        c = cpi.get(m, (None, None))
        out.append(Month(m, fd[0], fd[1], published, bill, c[0], c[1], rate_in_force(params["fd_advance_tax"], m)))
    return out


def data_through(months: list[Month]) -> dt.date | None:
    """The last month for which the deposit rate, the bill yield and the CCPI are all published."""
    full = [m.month for m in months if m.fd_rate is not None and m.bill_rate is not None and m.cpi is not None]
    return max(full) if full else None


# --- growth -------------------------------------------------------------------------------------------------------

def growth_rows(months: list[Month], params: dict) -> list[dict]:
    """Every (start month, horizon) whose end month is published, per instrument and basis."""
    by_month = {m.month: m for m in months}
    through = data_through(months)
    if through is None:
        return []
    amount = float(params["amount"])
    out = []
    for start in sorted(by_month):
        s = by_month[start]
        if s.cpi is None:
            continue
        for h in params["horizons"]:
            end = add_months(start, 12 * h)
            if end > through or end not in by_month or by_month[end].cpi is None:
                continue
            rolls = [by_month.get(add_months(start, 12 * j)) for j in range(h)]
            if any(r is None or r.fd_rate is None or r.bill_rate is None for r in rolls):
                continue
            fd = fd_net = bill = amount
            for j, r in enumerate(rolls):
                paid = add_months(start, 12 * (j + 1))           # interest is paid when the deposit matures
                tax = by_month[paid].fd_tax_pct if paid in by_month else rate_in_force(params["fd_advance_tax"], paid)
                fd *= 1 + r.fd_rate / 100
                fd_net *= 1 + r.fd_rate / 100 * (1 - tax / 100)
                bill *= 1 + r.bill_rate / 100
            deflate = s.cpi / by_month[end].cpi
            series = "+".join(sorted({r.fd_series for r in rolls}, key=params["fd_series_order"][::-1].index))
            values = {("fd", "nominal"): fd, ("fd", "nominal_after_tax"): fd_net, ("fd", "real"): fd * deflate,
                      ("fd", "real_after_tax"): fd_net * deflate, ("tbill", "nominal"): bill,
                      ("tbill", "real"): bill * deflate}
            for (instrument, basis), value in values.items():
                out.append({"start_month": start, "horizon_years": h, "instrument": instrument, "basis": basis,
                            "end_month": end, "value": value, "annual_rate": (value / amount) ** (1 / h) - 1,
                            "fd_series": series if instrument == "fd" else None})
    return out


def summary_rows(growth: list[dict], params: dict) -> list[dict]:
    amount = float(params["amount"])
    index = {(r["start_month"], r["horizon_years"], r["instrument"], r["basis"]): r["value"] for r in growth}
    out = []
    for h in params["summary_horizons"]:
        for instrument in INSTRUMENTS:
            other = "tbill" if instrument == "fd" else "fd"
            for basis in BASES[instrument]:
                rows = sorted((r for r in growth if r["horizon_years"] == h and r["instrument"] == instrument
                               and r["basis"] == basis), key=lambda r: r["start_month"])
                if not rows:
                    continue
                comparable = basis in BASES[other]          # bills have no after-tax figure: no comparison
                ahead = sum(1 for r in rows if r["value"] > index[(r["start_month"], h, other, basis)]) \
                    if comparable else None
                best = max(rows, key=lambda r: (r["value"], -r["start_month"].toordinal()))
                worst = min(rows, key=lambda r: (r["value"], r["start_month"].toordinal()))
                median = statistics.median(r["value"] for r in rows)
                rate = lambda v: (v / amount) ** (1 / h) - 1   # noqa: E731
                out.append({
                    "horizon_years": h, "instrument": instrument, "basis": basis, "n_periods": len(rows),
                    "first_start": rows[0]["start_month"], "last_start": rows[-1]["start_month"], "n_ahead": ahead,
                    "n_above_start": sum(1 for r in rows if r["value"] > amount),
                    "median_value": median, "best_value": best["value"], "best_start": best["start_month"],
                    "worst_value": worst["value"], "worst_start": worst["start_month"],
                    "median_annual": rate(median), "best_annual": rate(best["value"]),
                    "worst_annual": rate(worst["value"]),
                })
    return out


def rate_rows(months: list[Month]) -> list[dict]:
    by_month = {m.month: m for m in months}
    out = []
    for m in months:
        year_ago = by_month.get(add_months(m.month, -12))
        out.append({"month": m.month, "fd_rate_pct": m.fd_rate, "fd_series": m.fd_series,
                    "bill_published_pct": m.bill_published, "bill_rate_pct": m.bill_rate, "cpi": m.cpi,
                    "cpi_base": m.cpi_base,
                    "inflation_yoy": m.cpi / year_ago.cpi - 1 if m.cpi and year_ago and year_ago.cpi else None,
                    "fd_tax_pct": m.fd_tax_pct})
    return out


# --- the plug-in --------------------------------------------------------------------------------------------------

def compute(inputs, as_of):
    params = inputs.params
    where, args = ("month <= %s", (as_of,)) if as_of else ("", ())
    series = list(params["fd_series_order"]) + [params["bill_series"]]
    rates: dict[str, dict[dt.date, float]] = {}
    for r in inputs.rows("rates.cbsl_monthly_current", "series, month, value",
                         where=" and ".join(filter(None, ["series = any(%s)", where])), params=(series, *args),
                         order_by="series, month"):
        rates.setdefault(r["series"], {})[r["month"]] = r["value"]
    by_base: dict[str, dict[dt.date, float]] = {}
    for r in inputs.rows("rates.cpi_monthly_current", "base, month, value",
                         where=" and ".join(filter(None, ["index_code = 'CCPI'", where])), params=args,
                         order_by="base, month"):
        by_base.setdefault(r["base"], {})[r["month"]] = r["value"]
    unknown = set(by_base) - set(params["cpi_bases"])
    if unknown:
        raise ValueError(f"CCPI base(s) {sorted(unknown)} are not in the manifest's cpi_bases: add them in order")
    cpi, _ = link_cpi(by_base, params["cpi_bases"])
    months = monthly_inputs(rates, cpi, params)
    growth = growth_rows(months, params)
    return {
        "models.savings_rates": rate_rows(months),
        "models.savings_growth": growth,
        "models.savings_summary": summary_rows(growth, params),
    }
