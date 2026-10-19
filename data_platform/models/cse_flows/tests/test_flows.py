"""cse_flows: the old terminal's account rules (its tests, ported with made-up names), the per-company and per-account
tables, the flags, the windows and the point-in-time rule. Inputs: cse_dealings run on the synthetic notices in
tests/fixtures/cse/dealings, and a made-up security list."""
from __future__ import annotations

import datetime as dt
import json

import pytest

from conftest import FIXTURES
from data_platform.models.cse_dealings import compute as dealings_model
from data_platform.models.cse_flows import compute as m, entities
from data_platform.models.framework import load_manifest

NOTICES = FIXTURES / "cse" / "dealings" / "getAnnouncementById"
LIST_DAY = dt.date(2026, 9, 30)
SECURITIES = [{"session_date": LIST_DAY, "symbol": s, "name": n} for s, n in (
    ("AAA.N0000", "ALPHA EXAMPLE PLC"), ("AAA.X0000", "ALPHA EXAMPLE PLC"), ("BBB.N0000", "BETA SAMPLE HOLDINGS PLC"),
    ("CCC.R0000", "GAMMA RIGHTS"))]


def dealings_outputs(as_of=None) -> dict:
    from data_platform.models.cse_dealings.tests.test_dealings import Inputs as NoticeInputs

    notices = {int(p.stem): json.loads(p.read_text()) for p in NOTICES.glob("*.json")}
    out = dealings_model.compute(NoticeInputs(notices), as_of)
    for r in out["models.cse_dealing"]:          # as the database hands them back
        for k in ("trade_date", "deal_date", "announced_date"):
            r[k] = dt.date.fromisoformat(r[k]) if r[k] else None
    return out


class Inputs:
    def __init__(self, dealing: dict, securities=SECURITIES, params=None):
        self.dealing = dealing
        self.securities = securities
        self.params = dict(load_manifest("cse_flows").current.parameters, **(params or {}))

    def rows(self, dataset, columns="*", where="", params=(), order_by="", group_by=""):
        if dataset == "models.cse_dealing":
            return [dict(r) for r in self.dealing["models.cse_dealing"]]
        if dataset == "models.cse_dealing_as_filed":
            return [dict(r) for r in self.dealing["models.cse_dealing_as_filed"]]
        assert dataset == "cse.security_list", dataset
        if "min(session_date)" in where:
            first = min(r["session_date"] for r in self.securities)
            return [r for r in self.securities if r["session_date"] == first]
        return [r for r in self.securities if not params or r["session_date"] <= params[0]]


def run(as_of=None, dealing=None, **kw):
    return m.compute(Inputs(dealing or dealings_outputs(), **kw), as_of)


def market():
    return entities.market(SECURITIES)


# --- the account that dealt (old cse/flows.py and cse/ownership/names.py) -------------------------------------------

def test_a_related_account_resolves_to_the_listed_company():
    e = entities.actor_entity("Alpha Example PLC - Common Directors", market())
    assert (e.type, e.symbol, e.key, e.name) == ("listed", "AAA", "LISTED:AAA", "ALPHA EXAMPLE PLC")
    assert entities.actor_entity("Disposal of shares by Beta Sample Holdings PLC", market()).symbol == "BBB"


def test_descriptions_after_a_name_are_removed_but_a_relative_keeps_their_own_name():
    mk = market()
    assert entities.actor_entity("Example Holdings (Pvt) Ltd- Director", mk).name == "Example Holdings (Pvt) Ltd"
    assert entities.actor_entity("Example Holdings (Private) Limited, privately held company owned by Mr. Z Example",
                                 mk).name == "Example Holdings (Private) Limited"
    assert entities.actor_entity("Example Holdings (Pvt) Ltd, in which Mrs. C. Sample serves as a Director",
                                 mk).key == entities.actor_entity("Example Holdings Private Limited", mk).key
    assert "SPOUSE" in entities.actor_entity("Mrs X Sample (Spouse)", mk).key
    assert entities.actor_entity("Mr. A. B. Example", mk).type == "individual"


def test_generic_account_names_fall_back_to_the_director_then_to_the_company():
    assert entities.GENERIC_ACCOUNT.match("Please refer attachment")
    assert entities.account_name("N/A", "Mr. A. Example", "ALPHA EXAMPLE PLC") == "Mr. A. Example"
    assert entities.account_name("Shareholders", "As per attached", "ALPHA EXAMPLE PLC") == \
        "ALPHA EXAMPLE PLC – directors (see notice)"
    assert entities.account_name("Example Ltd", "Mr. A. Example", "X") == "Example Ltd"


def test_initials_are_never_matched_to_a_full_name():
    mk = market()
    assert entities.actor_entity("Mr. A. B. Example", mk).key != entities.actor_entity("Mr. Arun Bala Example", mk).key
    assert entities.actor_entity("Mr. A. B. Example", mk).key == entities.actor_entity("A.B. EXAMPLE", mk).key


# --- the tables -----------------------------------------------------------------------------------------------------

def company(out, day, window, symbol):
    return next(r for r in out["models.cse_flow_company"]
                if (r["as_of"], r["window_days"], r["symbol"]) == (dt.date.fromisoformat(day), window, symbol))


def test_two_different_purchasers_with_net_purchases_are_a_cluster():
    out = run()
    c = company(out, "2026-10-03", 30, "AAA")
    assert (c["purchase_value"], c["disposal_value"], c["net_value"]) == (17000.0, 0.0, 17000.0)
    assert (c["n_purchasers"], c["n_disposers"], c["n_transactions"], c["cluster"]) == (2, 0, 3, True)
    one = company(out, "2026-10-02", 30, "AAA")
    assert (one["n_purchasers"], one["cluster"]) == (1, False)          # one account twice is not a cluster


def test_a_refiled_disposal_counts_once_and_ends_the_cluster():
    c = company(run(), "2026-10-06", 30, "AAA")
    assert c["disposal_value"] == 12_000_000 and c["net_value"] == 17000 - 12_000_000
    assert (c["n_disposers"], c["cluster"], c["n_transactions"]) == (1, False, 4)


def test_other_dealings_are_never_purchases_or_disposals():
    out = run()
    assert not [r for r in out["models.cse_flow_company"] if r["symbol"] == "BBB"]
    s = {r["as_of"].isoformat(): r for r in out["models.cse_flow_summary"]}["2026-10-08"]
    assert (s["n_dealings"], s["n_trades"]) == (5, 4) and s["lag_median"] == 1.0          # lags 2, 1, 1, 2, 1
    gift = next(r for r in out["models.cse_flow_dealing"] if r["transaction_id"] == "900010:1")
    assert gift["side"] == "other" and gift["actor_type"] == "individual"


def test_flags_large_and_related_party():
    flags = {r["transaction_id"]: (r["large"], r["related_account"]) for r in run()["models.cse_flow_dealing"]}
    assert flags == {"900001:1": (False, False), "900001:2": (False, False), "900012:1": (False, False),
                     "900003:1": (True, True), "900010:1": (False, False)}     # 900002 was re-filed: not counted


def test_the_large_threshold_is_the_manifests_parameter():
    flags = {r["transaction_id"]: r["large"] for r in run(params={"large_lkr": 10_000})["models.cse_flow_dealing"]}
    assert flags["900001:1"] and not flags["900012:1"]


def test_per_account_rows_carry_names_and_their_net_by_company():
    actors = [r for r in run()["models.cse_flow_actor"] if r["as_of"] == dt.date(2026, 10, 6) and r["window_days"] == 30]
    by = {r["actor"]: r for r in actors}
    assert set(by) == {"Mr. A. B. Example", "Mrs. E. Sample", "Example Holdings (Pvt) Ltd"}
    assert by["Example Holdings (Pvt) Ltd"]["net_value"] == -12_000_000
    assert json.loads(by["Mr. A. B. Example"]["companies"]) == [["AAA", 16000.0]]
    assert by["Mr. A. B. Example"]["n_transactions"] == 2


def test_window_ends_on_each_dealing_date_and_starts_after_it_minus_the_days():
    deals = [{"date": d, "side": "purchase"} for d in ("2026-09-06", "2026-09-07", "2026-10-06", "2026-10-07")]
    got = [d["date"] for d in m.window(deals, dt.date(2026, 10, 6), 30)]
    assert got == ["2026-09-07", "2026-10-06"]                        # (D - 30 days, D]


def test_every_dealing_date_and_window_has_rows():
    out = run()
    days = sorted({r["as_of"] for r in out["models.cse_flow_summary"]})
    assert [d.isoformat() for d in days] == ["2026-10-01", "2026-10-02", "2026-10-03", "2026-10-06", "2026-10-08"]
    assert {r["window_days"] for r in out["models.cse_flow_company"]} == {30, 90, 365}


# --- point in time --------------------------------------------------------------------------------------------------

def _by_key(rows, key):
    return {tuple(r[k] for k in key): r for r in rows}


KEYS = {"models.cse_flow_company": ["as_of", "window_days", "symbol"], "models.cse_flow_summary": ["as_of"],
        "models.cse_flow_actor": ["as_of", "window_days", "actor_key"]}


def test_a_row_for_day_d_does_not_change_when_later_dealings_arrive():
    full = dealings_outputs()
    cut = dt.date(2026, 10, 3)
    early = {t: [dict(r) for r in rows] for t, rows in full.items()}
    keep = {r["transaction_id"] for r in early["models.cse_dealing"] if r["deal_date"] <= cut}
    early["models.cse_dealing"] = [r for r in early["models.cse_dealing"] if r["transaction_id"] in keep]
    before, after = run(dealing=early), run(dealing=full)
    for table, key in KEYS.items():
        b = _by_key(before[table], key)
        a = {k: r for k, r in _by_key(after[table], key).items() if r["as_of"] <= cut}
        assert b and b == a, table


def test_a_look_at_the_past_sees_only_what_was_announced_by_then():
    cut = dt.date(2026, 10, 5)
    past = run(as_of=cut, dealing=dealings_outputs())
    now = run()
    for table, key in KEYS.items():
        a = {k: r for k, r in _by_key(now[table], key).items() if r["as_of"] <= cut}
        assert _by_key(past[table], key) == a, table
    # on 7 October the re-filing of 8 October was not known yet: the first notice counted
    seen = {r["transaction_id"] for r in run(as_of=dt.date(2026, 10, 7))["models.cse_flow_dealing"]}
    assert "900002:1" in seen and "900003:1" not in seen


def test_without_a_security_list_every_account_is_named_by_its_own_name():
    out = run(securities=[])
    assert {r["actor_type"] for r in out["models.cse_flow_actor"]} <= {"individual", "company"}


@pytest.mark.parametrize("day", ["2026-09-01", "2026-10-31"])
def test_the_security_list_in_force_is_the_latest_on_or_before_the_day(day):
    later = dict(SECURITIES[0], session_date=dt.date(2026, 10, 15), name="ALPHA RENAMED PLC")
    lists = m.Lists(SECURITIES + [later])
    names = lists.market(dt.date.fromisoformat(day)).names
    assert names["AAA"] == ("ALPHA EXAMPLE PLC" if day < "2026-10-15" else "ALPHA RENAMED PLC")
