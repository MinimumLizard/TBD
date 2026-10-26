"""The record's rules on real closes (the old terminal's tests, ported: tests/fixtures/cse/2026-10-02 charts of CIC,
COMB, HAYL and LOLC and the ASPI): inception with whole shares and costs, dividends, splits and rights on holdings, the
stale-price correction, the drift band, the rebalance calendar, and a day without model weights."""
from __future__ import annotations

import math

import pytest

from conftest import FIXTURES
from data_platform.collectors.cse import parse
from data_platform.models._lib import cse_record as rec
from data_platform.models.cse_lab_record import compute as m

CHART = FIXTURES / "cse" / "2026-10-02"
CFG = {"record_notional_lkr": 10_000_000, "cost_per_side": 0.0112, "dividend_withholding": 0.10,
       "band_relative": 0.25, "band_absolute": 0.02, "min_trade_lkr": 25_000, "rebalance_months": [1, 4, 7, 10]}
SYMS = ["LOLC.N0000", "COMB.N0000", "HAYL.N0000", "CIC.N0000"]


def closes():
    out = {}
    for s in SYMS:
        rows = parse.stock_chart((CHART / "companyChartDataByStock" / f"{s}.json").read_bytes(), s)
        out[s] = {r["session_date"].isoformat(): r["close"] for r in rows}
    return out


def aspi():
    rows = parse.index_chart((CHART / "chartData_1_p5.json").read_bytes(), "ASI")
    return {r["session_date"].isoformat(): r["value"] for r in rows}


SESSIONS = sorted(aspi())
S0 = next(s for s in SESSIONS if s >= "2025-11-05")
TARGETS = {"LOLC.N0000": 0.4, "COMB.N0000": 0.3, "HAYL.N0000": 0.3}
ALL = {p: TARGETS for p in rec.TRADED}
EMPTY = {t: [] for t in m.OUTPUTS}


class Book:
    """A record kept in memory across sessions, through the model's own advance() (as stored, read back)."""

    def __init__(self, digits=None):
        self.rows, self.digits = {t: [] for t in m.OUTPUTS}, digits

    def run(self, session, actions=(), targets=ALL, cfg=CFG):
        last, states = m.state_of(self.rows)
        up = rec.update(last, states, "test", session, SESSIONS, targets, rec.Pricer(closes(), list(actions), session),
                        list(actions), aspi(), cfg)
        new = m.to_rows(up, self.digits, {})
        for t in m.OUTPUTS:
            self.rows[t] += new[t]
        return up

    def state(self):
        return m.state_of(self.rows)[1]


def test_inception_takes_whole_shares_and_pays_costs():
    up = Book().run(S0)
    assert up.status == f"inception {S0}"
    c = closes()
    rows = [t for t in up.trades if t["portfolio"] == "min_variance"]
    assert {t["action"] for t in rows} == {rec.INCREASE}
    for t in rows:
        p = c[t["symbol"]][S0]
        assert t["shares"] == math.floor(TARGETS[t["symbol"]] * 10_000_000 / (p * 1.0112))
        assert t["cost"] == pytest.approx(t["value"] * 0.0112)
    nav = next(n for n in up.nav if n["portfolio"] == "min_variance")
    spent = sum(t["value"] + t["cost"] for t in rows)
    assert nav["cash"] == pytest.approx(10_000_000 - spent) and nav["cash"] >= 0
    assert nav["nav"] == pytest.approx(10_000_000 - sum(t["cost"] for t in rows))
    assert next(n for n in up.nav if n["portfolio"] == "market")["nav"] == 10_000_000


def test_a_session_already_recorded_adds_nothing_and_an_earlier_one_is_refused():
    b = Book()
    b.run(S0)
    before = {t: list(v) for t, v in b.rows.items()}
    up = b.run(S0)
    assert up.status.startswith(f"record already has {S0}") and b.rows == before
    with pytest.raises(RuntimeError, match="after session"):
        b.run(SESSIONS[SESSIONS.index(S0) - 1])


def test_cash_dividend_credited_on_its_ex_date_net_of_withholding():
    b, t = Book(), {p: {"CIC.N0000": 1.0} for p in rec.TRADED}
    b.run("2026-06-24", targets=t)
    st = b.state()["min_variance"]
    held, cash0 = st.shares["CIC.N0000"], st.cash
    div = [{"symbol": "CIC.N0000", "type": "cash_dividend", "ex_date": "2026-07-01", "amount_per_share": 0.5}]
    # 1 July 2026 is the first session of July, a rebalance date; take July out to see the credit on its own
    up = b.run("2026-07-01", div, targets=t, cfg={**CFG, "rebalance_months": [1, 4, 10]})
    d = [x for x in up.trades if x["portfolio"] == "min_variance" and x["action"] == "dividend"][0]
    assert d["value"] == pytest.approx(held * 0.5 * 0.90)
    assert next(n for n in up.nav if n["portfolio"] == "min_variance")["cash"] == pytest.approx(cash0 + d["value"])


def test_a_split_changes_the_share_count_without_a_jump_in_value():
    b, t = Book(), {p: {"CIC.N0000": 1.0} for p in rec.TRADED}
    first = b.run("2025-10-13", targets=t)
    nav0 = next(n for n in first.nav if n["portfolio"] == "risk_parity")["nav"]
    held = b.state()["risk_parity"].shares["CIC.N0000"]
    split = [{"symbol": "CIC.N0000", "type": "subdivision", "ex_date": "2025-10-22", "factor": 5.0}]
    up = b.run("2025-10-22", split, targets=t)
    h = next(x for x in up.holdings if x["portfolio"] == "risk_parity" and x["symbol"] == "CIC.N0000")
    assert h["shares"] == held * 5
    nav1 = next(n for n in up.nav if n["portfolio"] == "risk_parity")["nav"]
    assert nav1 / nav0 - 1 == pytest.approx((34.2 * 5 - 170) * held / nav0, abs=1e-6)


def test_the_price_of_a_share_that_has_not_traded_since_a_split_is_corrected():
    split = [{"symbol": "CIC.N0000", "type": "subdivision", "ex_date": "2025-10-15", "factor": 5.0}]
    assert rec.Pricer(closes(), split, "2025-10-20").price("CIC.N0000") == pytest.approx(170 / 5)


def test_rights_are_taken_up_and_paid_from_cash():
    b, t = Book(), {p: {"HAYL.N0000": 0.5} for p in rec.TRADED}
    b.run("2026-03-11", targets=t)
    held = b.state()["max_sharpe"].shares["HAYL.N0000"]
    rights = [{"symbol": "HAYL.N0000", "type": "rights", "ex_date": "2026-03-18", "ratio_new": 3.0,
               "ratio_held": 50.0, "subscription_price": 200.0}]
    up = b.run("2026-03-18", rights, targets=t)
    r = [x for x in up.trades if x["portfolio"] == "max_sharpe" and x["action"] == "rights"][0]
    assert r["shares"] == math.floor(held * 3 / 50) and r["value"] == pytest.approx(r["shares"] * 200.0)


def test_names_outside_the_drift_band_go_back_to_their_weight_at_the_next_close():
    b = Book()
    b.run(S0)
    rows = []
    for s in SESSIONS[SESSIONS.index(S0) + 1:]:
        if rec.is_scheduled(s, SESSIONS, CFG["rebalance_months"]):
            break
        up = b.run(s)
        flagged = {h["symbol"] for h in up.holdings if h["portfolio"] == "min_variance" and h["flag"] == "1"}
        rows.append((flagged, [t for t in up.trades if t["portfolio"] == "min_variance" and t["reason"] == "drift band"]))
    assert len(rows) > 20
    for (flagged, _), (_, changes) in zip(rows, rows[1:]):
        assert {t["symbol"] for t in changes} <= flagged


def test_band_and_calendar():
    assert rec.band(0.10, CFG) == pytest.approx(0.025)
    assert rec.band(0.04, CFG) == pytest.approx(0.02)
    assert rec.is_scheduled("2026-01-02", ["2025-12-31", "2026-01-02", "2026-01-05"], [1, 4, 7, 10])
    assert not rec.is_scheduled("2026-01-05", ["2025-12-31", "2026-01-02", "2026-01-05"], [1, 4, 7, 10])
    assert not rec.is_scheduled("2026-02-02", ["2026-01-30", "2026-02-02"], [1, 4, 7, 10])


def test_a_rebalance_date_brings_every_name_to_its_new_weight():
    b = Book()
    b.run("2025-12-31")
    new = {p: {"LOLC.N0000": 0.5, "COMB.N0000": 0.5} for p in rec.TRADED}
    first_jan = next(s for s in SESSIONS if s.startswith("2026-01"))
    up = b.run(first_jan, targets=new)
    assert "scheduled rebalance" in up.status
    held = {h["symbol"]: h for h in up.holdings if h["portfolio"] == "min_variance"}
    assert "HAYL.N0000" not in held                    # removed from the portfolio entirely
    assert any(t["symbol"] == "HAYL.N0000" and t["action"] == rec.DECREASE for t in up.trades)
    assert held["LOLC.N0000"]["target_weight"] == 0.5


def test_without_model_weights_the_record_keeps_valuing_and_skips_the_rebalance():
    b = Book()
    b.run("2025-12-31")
    first_jan = next(s for s in SESSIONS if s.startswith("2026-01"))
    up = b.run(first_jan, targets=None)
    assert "scheduled rebalance skipped" in up.status
    assert not [t for t in up.trades if t["action"] in (rec.INCREASE, rec.DECREASE)]
    assert {n["portfolio"] for n in up.nav} >= set(rec.TRADED) | {"market"}
    assert Book().run(S0, targets=None).nav == []        # and no record is started without them


def test_rounded_storage_is_read_back_rounded_as_the_old_files_were():
    b = Book(digits=8)
    b.run(S0)
    cash = next(r["cash"] for r in b.rows[m.NAV] if r["portfolio"] == "min_variance")
    assert cash == round(cash, 8) and b.state()["min_variance"].cash == cash


def test_advance_records_each_session_in_order_and_never_rewrites_one():
    targets = {s: ALL for s in SESSIONS}
    todo = [s for s in SESSIONS if S0 <= s <= "2025-11-20"]
    first, _ = m.advance(EMPTY, todo[:3], SESSIONS, targets, aspi(), closes(), [], CFG, "t", rec.TRADED, None, True)
    both, _ = m.advance(first, todo, SESSIONS, targets, aspi(), closes(), [], CFG, "t", rec.TRADED, None, True)
    once, _ = m.advance(EMPTY, todo, SESSIONS, targets, aspi(), closes(), [], CFG, "t", rec.TRADED, None, True)
    assert both == once                                  # in two runs or one: the same record
    assert both[m.NAV][:len(first[m.NAV])] == first[m.NAV]    # the earlier rows unchanged
    assert sorted({r["session_date"].isoformat() for r in both[m.NAV]}) == todo
