"""lk_savings_compare: the arithmetic, the CCPI link, taxes, the summary, real files end to end, and point in time."""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest
import yaml

from data_platform.models.lk_savings_compare import compute as m

D = dt.date
FIX = Path(__file__).resolve().parents[4] / "tests" / "fixtures"
PARAMS = yaml.safe_load((Path(__file__).parents[1] / "manifest.yaml").read_text())["versions"][0]["parameters"]


def months(start: dt.date, n: int) -> list[dt.date]:
    return [m.add_months(start, i) for i in range(n)]


# --- small pieces -----------------------------------------------------------------------------------------------

def test_add_months():
    assert m.add_months(D(2020, 11, 1), 2) == D(2021, 1, 1)
    assert m.add_months(D(2020, 1, 1), -1) == D(2019, 12, 1)
    assert m.add_months(D(2003, 1, 1), 120) == D(2013, 1, 1)


@pytest.mark.parametrize("day, pct", [(D(2022, 12, 1), 0), (D(2023, 1, 1), 5), (D(2025, 3, 1), 5), (D(2025, 4, 1), 10),
                                      (D(2030, 1, 1), 10)])
def test_advance_income_tax_by_the_date_interest_is_paid(day, pct):
    assert m.rate_in_force(PARAMS["fd_advance_tax"], day) == pct


def test_bill_withholding_window():
    w = PARAMS["bill_withholding_added_back"]
    assert not m.in_window(w, D(2002, 4, 1)) and m.in_window(w, D(2002, 5, 1))
    assert m.in_window(w, D(2018, 3, 1)) and not m.in_window(w, D(2018, 4, 1))


# --- the CCPI link ----------------------------------------------------------------------------------------------

def test_cpi_link_is_continuous_keeps_each_bases_changes_and_uses_the_oldest_base():
    old = {d: 100.0 + i for i, d in enumerate(months(D(2010, 1, 1), 36))}          # 2010-01 .. 2012-12
    new = {d: 50.0 * 1.01 ** i for i, d in enumerate(months(D(2012, 1, 1), 24))}    # 2012-01 .. 2013-12
    linked, links = m.link_cpi({"old": old, "new": new}, ["old", "new"])
    (link,) = links
    assert link.month == D(2012, 1, 1) and link.factor == pytest.approx(old[D(2012, 1, 1)] / 50.0)
    assert linked[D(2011, 12, 1)] == (old[D(2011, 12, 1)], "old")                  # before the link: as published
    assert linked[D(2012, 1, 1)][0] == pytest.approx(old[D(2012, 1, 1)])            # continuous at the link
    assert linked[D(2012, 1, 1)][1] == "new"                                        # the newer base from its first month
    for a, b in [(D(2012, 3, 1), D(2013, 11, 1))]:                                  # the newer base's own changes
        assert linked[b][0] / linked[a][0] == pytest.approx(new[b] / new[a])
    assert len(linked) == 48


def test_three_bases_chain_and_a_future_base_changes_nothing_before_it():
    a = {d: 100.0 for d in months(D(2000, 1, 1), 24)}
    b = {d: 10.0 for d in months(D(2001, 1, 1), 24)}
    c = {d: 1.0 for d in months(D(2002, 6, 1), 12)}
    two, _ = m.link_cpi({"a": a, "b": b}, ["a", "b"])
    three, links = m.link_cpi({"a": a, "b": b, "c": c}, ["a", "b", "c"])
    assert [round(x.factor, 9) for x in links] == [10.0, 10.0]
    assert three[D(2003, 5, 1)] == (pytest.approx(100.0), "c")
    assert all(three[d] == two[d] for d in two if d < D(2002, 6, 1))


def test_bases_that_do_not_overlap_cannot_be_linked():
    with pytest.raises(ValueError, match="do not overlap"):
        m.link_cpi({"a": {D(2000, 1, 1): 100.0}, "b": {D(2001, 1, 1): 100.0}}, ["a", "b"])


# --- growth -----------------------------------------------------------------------------------------------------

def inputs(n_months=12 * 12, start=D(2014, 1, 1), fd=10.0, bill=9.0, inflation_monthly=0.005, **kw):
    ds = months(start, n_months)
    rates = {"AWNFDR": {d: fd for d in ds}, "TB_12M": {d: bill for d in ds}}
    rates.update(kw.pop("rates", {}))
    cpi = {d: (100 * (1 + inflation_monthly) ** i, "x") for i, d in enumerate(ds)}
    params = {**PARAMS, **kw}
    return m.monthly_inputs(rates, cpi, params), params


def row(rows, start, h, instrument, basis):
    (r,) = [r for r in rows if r["start_month"] == start and r["horizon_years"] == h and r["instrument"] == instrument
            and r["basis"] == basis]
    return r


def test_constant_rates_compound_once_a_year():
    ms, params = inputs()
    rows = m.growth_rows(ms, params)
    r = row(rows, D(2014, 1, 1), 10, "fd", "nominal")
    assert r["value"] == pytest.approx(100_000 * 1.10 ** 10) and r["annual_rate"] == pytest.approx(0.10)
    assert r["end_month"] == D(2024, 1, 1) and r["fd_series"] == "AWNFDR"
    # bills bought in 2014-2016 were printed after the 10% withholding tax: 9% printed is 10% before tax
    assert row(rows, D(2014, 1, 1), 3, "tbill", "nominal")["value"] == pytest.approx(100_000 * 1.10 ** 3)
    assert row(rows, D(2018, 4, 1), 3, "tbill", "nominal")["value"] == pytest.approx(100_000 * 1.09 ** 3)
    real = row(rows, D(2014, 1, 1), 1, "fd", "real")["value"]
    assert real == pytest.approx(110_000 / 1.005 ** 12)
    # nothing ends after the last month with data
    assert max(r["end_month"] for r in rows) == D(2025, 12, 1)
    assert not any(r["horizon_years"] == 10 and r["start_month"] > D(2015, 12, 1) for r in rows)


def test_deposit_tax_is_taken_at_the_rate_in_force_when_the_interest_is_paid():
    ms, params = inputs(start=D(2021, 1, 1), n_months=72)
    rows = m.growth_rows(ms, params)
    # placed 2022-12, paid 2023-12 at 5%; placed 2024-03, paid 2025-03 at 5%; placed 2024-04, paid 2025-04 at 10%
    assert row(rows, D(2021, 12, 1), 1, "fd", "nominal_after_tax")["value"] == pytest.approx(110_000)   # paid 2022-12
    assert row(rows, D(2022, 12, 1), 1, "fd", "nominal_after_tax")["value"] == pytest.approx(100_000 * (1 + 0.10 * 0.95))
    assert row(rows, D(2024, 3, 1), 1, "fd", "nominal_after_tax")["value"] == pytest.approx(100_000 * (1 + 0.10 * 0.95))
    assert row(rows, D(2024, 4, 1), 1, "fd", "nominal_after_tax")["value"] == pytest.approx(100_000 * (1 + 0.10 * 0.90))
    two = row(rows, D(2022, 4, 1), 3, "fd", "nominal_after_tax")["value"]   # paid 2023-04 (5%), 2024-04 (5%), 2025-04 (10%)
    assert two == pytest.approx(100_000 * 1.095 * 1.095 * 1.09)
    assert not any(r["instrument"] == "tbill" and "after_tax" in r["basis"] for r in rows)


def test_bill_yields_printed_after_the_withholding_tax_are_compared_before_it():
    ms, params = inputs(start=D(2017, 1, 1), n_months=36)
    rows = m.growth_rows(ms, params)
    assert row(rows, D(2018, 3, 1), 1, "tbill", "nominal")["value"] == pytest.approx(100_000 * (1 + 0.09 / 0.9))
    assert row(rows, D(2018, 4, 1), 1, "tbill", "nominal")["value"] == pytest.approx(109_000)
    by_month = {x.month: x for x in ms}
    assert by_month[D(2018, 3, 1)].bill_published == 9.0 and by_month[D(2018, 3, 1)].bill_rate == pytest.approx(10.0)


def test_awfdr_stands_in_before_awnfdr_and_is_flagged():
    ds = months(D(2013, 1, 1), 48)
    ms, params = inputs(start=D(2013, 1, 1), n_months=48,
                        rates={"AWNFDR": {d: 10.0 for d in ds if d >= D(2014, 4, 1)}, "AWFDR": {d: 8.0 for d in ds}})
    rows = m.growth_rows(ms, params)
    assert row(rows, D(2013, 1, 1), 1, "fd", "nominal")["fd_series"] == "AWFDR"
    mixed = row(rows, D(2013, 6, 1), 2, "fd", "nominal")
    assert mixed["fd_series"] == "AWFDR+AWNFDR" and mixed["value"] == pytest.approx(100_000 * 1.08 * 1.10)
    assert row(rows, D(2014, 4, 1), 1, "fd", "nominal")["fd_series"] == "AWNFDR"


def test_a_missing_rate_leaves_the_periods_that_need_it_out():
    ms, params = inputs(start=D(2014, 1, 1), n_months=48)
    hole = [x for x in ms if x.month != D(2015, 1, 1)] + [m.Month(D(2015, 1, 1), 10.0, "AWNFDR", None, None, 101.0, "x", 0)]
    rows = m.growth_rows(sorted(hole, key=lambda x: x.month), params)
    assert not any(r["start_month"] == D(2014, 1, 1) and r["horizon_years"] >= 2 for r in rows)
    assert any(r["start_month"] == D(2014, 1, 1) and r["horizon_years"] == 1 for r in rows)


def test_summary_counts_and_extremes():
    growth = []
    for i, (fd, bill) in enumerate([(110_000, 105_000), (104_000, 106_000), (90_000, 95_000)]):
        start = m.add_months(D(2010, 1, 1), i)
        for instrument, value in (("fd", fd), ("tbill", bill)):
            for basis in m.BASES[instrument]:
                growth.append({"start_month": start, "horizon_years": 1, "instrument": instrument, "basis": basis,
                               "value": value})
    s = {(r["instrument"], r["basis"]): r for r in m.summary_rows(growth, {**PARAMS, "summary_horizons": [1]})}
    fd, bill = s[("fd", "nominal")], s[("tbill", "nominal")]
    assert fd["n_periods"] == 3 and fd["n_ahead"] == 1 and bill["n_ahead"] == 2
    assert fd["n_above_start"] == 2 and bill["n_above_start"] == 2
    assert fd["best_value"] == 110_000 and fd["best_start"] == D(2010, 1, 1)
    assert fd["worst_value"] == 90_000 and fd["worst_start"] == D(2010, 3, 1) and fd["median_value"] == 104_000
    assert fd["worst_annual"] == pytest.approx(-0.10)
    assert s[("fd", "nominal_after_tax")]["n_ahead"] is None        # bills have no after-tax figure to compare with


# --- the real published files, end to end -----------------------------------------------------------------------

@pytest.fixture
def real_facts(conn, store):
    """The cut-down real CBSL table 4.04 (2017 to January 2019) and the DCS CCPI base 2013, stored by the collectors'
    own code."""
    from data_platform.collectors import rates_store
    from data_platform.collectors.cbsl import parse as cbsl
    from data_platform.collectors.dcs_cpi import parse as dcs
    from data_platform.core import db

    now = dt.datetime(2026, 10, 18, tzinfo=dt.timezone.utc)
    for dataset, body, parse, version, errors in [
        ("cbsl_4.04", (FIX / "cbsl" / "table4.04_cut.xlsx").read_bytes(), cbsl.parse_monthly_rates,
         cbsl.PARSER_VERSION, (cbsl.ParseError,)),
        ("dcs_ccpi_", (FIX / "dcs_cpi" / "ccpi_base2013.txt").read_bytes(),
         lambda b: dcs.parse_ccpi_text(b.decode()), dcs.PARSER_VERSION, (dcs.ParseError,)),
    ]:
        url = f"https://example.test/{dataset}"
        fetch_id, sha = db.record_fetch(conn, store, source_id="cbsl", method="GET", url=url, params={},
                                        http_status=200, body=body, content_type=None, fetched_at=now)
        status, _, _ = rates_store.store_file(
            conn, source_id="cbsl" if dataset.startswith("cbsl") else "dcs_cpi", dataset=dataset, url=url,
            label=None, file_date=D(2026, 10, 12) if dataset.startswith("cbsl") else None, fetch_id=fetch_id,
            sha256=sha, fetched_at=now, body=body, parse=parse, parser_version=version, parse_errors=errors)
        assert status == "ok"
    conn.commit()
    return conn


@pytest.mark.db
def test_real_tables_spot_check(real_facts):
    from conftest import run_models

    run_models(real_facts, ["lk_savings_compare"])
    q = real_facts.execute("""select instrument, basis, value, fd_series from models.savings_growth
                              where start_month = '2018-01-01' and horizon_years = 1""").fetchall()
    got = {(r["instrument"], r["basis"]): r for r in q}
    # By hand from the published tables: AWNFDR January 2018 = 10.870154104158702%; the 12-month bill yield printed
    # for January 2018 = 8.9%, after the 10% withholding tax, so 8.9 / 0.9 before it; CCPI (2013 = 100) January
    # 2018 = 122.8 and January 2019 = 127.4.
    assert got[("fd", "nominal")]["value"] == pytest.approx(110_870.154104158702)
    assert got[("fd", "nominal")]["fd_series"] == "AWNFDR"
    assert got[("fd", "nominal_after_tax")]["value"] == pytest.approx(110_870.154104158702)   # no tax before 2023
    assert got[("tbill", "nominal")]["value"] == pytest.approx(100_000 * (1 + 8.9 / 0.9 / 100))
    assert got[("fd", "real")]["value"] == pytest.approx(110_870.154104158702 * 122.8 / 127.4)
    assert got[("tbill", "real")]["value"] == pytest.approx(100_000 * (1 + 8.9 / 0.9 / 100) * 122.8 / 127.4)
    # 2018-04 onwards: no withholding to add back (bill bought April 2018, 9.59% printed)
    april = real_facts.execute("""select bill_published_pct, bill_rate_pct, fd_tax_pct, cpi_base from models.savings_rates
                                  where month = '2018-04-01'""").fetchone()
    assert april["bill_published_pct"] == april["bill_rate_pct"] == 9.59 and april["fd_tax_pct"] == 0
    starts = real_facts.execute("select min(start_month) a, max(start_month) b, count(distinct start_month) n "
                                "from models.savings_growth").fetchone()
    assert (starts["a"], starts["b"], starts["n"]) == (D(2017, 1, 1), D(2018, 1, 1), 13)
    summary = real_facts.execute("select n_periods from models.savings_summary where horizon_years = 1").fetchall()
    assert {r["n_periods"] for r in summary} == {13}


# --- point in time ----------------------------------------------------------------------------------------------

def synthetic(conn, store, last_month: dt.date, tag: str, revise: dict | None = None):
    """Store a 'table 4.04' and a 'CCPI' file covering 2010-01 to last_month, as a new published version."""
    from data_platform.collectors import rates_store
    from data_platform.collectors.cbsl.parse import Parsed
    from data_platform.core import db

    now = dt.datetime(2026, 10, 18, tzinfo=dt.timezone.utc)
    ds = [d for d in months(D(2010, 1, 1), 240) if d <= last_month]
    rate_rows = [{"series": s, "month": d, "value": (v + (i % 7) * 0.3) if not (revise and (s, d) in revise)
                  else revise[(s, d)]}
                 for i, d in enumerate(ds) for s, v in (("AWFDR", 9.0), ("AWNFDR", 10.0), ("TB_12M", 9.5))
                 if not (s == "AWNFDR" and d < D(2014, 4, 1))]
    cpi_rows = [{"index_code": "CCPI", "base": "2013", "month": d, "value": 100 * 1.004 ** i + (i % 5) * 0.1}
                for i, d in enumerate(ds)]
    for dataset, rows, fdate in (("cbsl_4.04", rate_rows, last_month), ("dcs_ccpi_2013", cpi_rows, None)):
        body = f"{dataset} {tag}".encode()
        url = f"https://example.test/{dataset}/{tag}"
        fetch_id, sha = db.record_fetch(conn, store, source_id="cbsl", method="GET", url=url, params={},
                                        http_status=200, body=body, content_type=None, fetched_at=now)
        rates_store.store_file(conn, source_id="cbsl" if dataset.startswith("cbsl") else "dcs_cpi", dataset=dataset,
                               url=url, label=None, file_date=fdate, fetch_id=fetch_id, sha256=sha, fetched_at=now,
                               body=body, parse=lambda b, r=rows, ds_=dataset: Parsed(ds_, r), parser_version=1,
                               parse_errors=(ValueError,))
    conn.commit()


@pytest.mark.db
def test_a_row_never_changes_when_later_months_arrive(conn, store):
    from conftest import run_models

    synthetic(conn, store, D(2020, 6, 1), "v1")
    run_models(conn, ["lk_savings_compare"])
    before = {(r["start_month"], r["horizon_years"], r["instrument"], r["basis"]): r["value"]
              for r in conn.execute("select * from models.savings_growth")}
    synthetic(conn, store, D(2023, 9, 1), "v2")            # three more years of every series
    result = run_models(conn, ["lk_savings_compare"])["lk_savings_compare"]
    assert result.counts.inserted > 0
    revised = conn.execute("""select table_name, count(*) n from models.revisions
                              where table_name in ('models.savings_growth', 'models.savings_rates')
                              group by 1""").fetchall()
    assert revised == []                                    # nothing already published was rewritten
    after = {(r["start_month"], r["horizon_years"], r["instrument"], r["basis"]): r["value"]
             for r in conn.execute("select * from models.savings_growth")}
    assert all(after[k] == v for k, v in before.items())


@pytest.mark.db
def test_a_revised_rate_revises_exactly_the_periods_that_used_it(conn, store):
    from conftest import run_models

    synthetic(conn, store, D(2020, 6, 1), "v1")
    run_models(conn, ["lk_savings_compare"])
    synthetic(conn, store, D(2020, 6, 1), "v2", revise={("AWNFDR", D(2019, 6, 1)): 30.0})
    run_models(conn, ["lk_savings_compare"])
    changed = conn.execute("""select distinct row_key->>'start_month' s, (row_key->>'horizon_years')::int h
                              from models.revisions where table_name = 'models.savings_growth'""").fetchall()
    assert changed, "the revision must reach the outputs"
    for r in changed:   # every revised period placed or renewed a deposit in June 2019, and only fd rows changed
        start = D.fromisoformat(r["s"])
        assert any(m.add_months(start, 12 * j) == D(2019, 6, 1) for j in range(r["h"]))
    instruments = {r["i"] for r in conn.execute("""select distinct row_key->>'instrument' i from models.revisions
                                                   where table_name = 'models.savings_growth'""")}
    assert instruments == {"fd"}


@pytest.mark.db
def test_as_of_computes_the_same_rows_as_the_full_history(conn, store):
    """The in-memory 'as of' view (data up to a month) agrees with the full run on every row it has."""
    from data_platform.models.framework import Inputs, load_manifest

    synthetic(conn, store, D(2022, 12, 1), "v1")
    manifest = load_manifest("lk_savings_compare")
    full = m.compute(Inputs(conn, manifest, manifest.current), None)["models.savings_growth"]
    past = m.compute(Inputs(conn, manifest, manifest.current), D(2018, 12, 1))["models.savings_growth"]
    key = lambda r: (r["start_month"], r["horizon_years"], r["instrument"], r["basis"])   # noqa: E731
    full_by = {key(r): r["value"] for r in full}
    assert past and all(r["end_month"] <= D(2018, 12, 1) for r in past)
    assert all(full_by[key(r)] == r["value"] for r in past)
