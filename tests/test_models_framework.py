"""The model framework: what a plug-in may read, how outputs are written, and what the registry refuses."""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest
import yaml

from data_platform.models import framework as fw
from data_platform.models import registry


def _manifest(**over) -> fw.Manifest:
    body = {"name": "toy", "market": "lk_bonds", "title_key": "x.title", "summary_key": "x.summary",
            "disclaimer_key": "general", "requires_datasets": ["bonds.trades_current"],
            "outputs": ["models.bond_execution_gap"],
            "versions": [{"method_version": "1.0.0", "status": "current"}]}
    body.update(over)
    return fw.Manifest.model_validate(body)


# --- manifest -------------------------------------------------------------------------------------------------

def test_manifest_needs_exactly_one_current_version():
    with pytest.raises(ValueError, match="exactly one"):
        _manifest(versions=[{"method_version": "1.0.0", "status": "reference"}])
    with pytest.raises(ValueError, match="exactly one"):
        _manifest(versions=[{"method_version": "1.0.0", "status": "current"},
                            {"method_version": "2.0.0", "status": "current"}])


def test_manifest_rejects_bad_versions_and_outputs_outside_models():
    with pytest.raises(ValueError, match="MAJOR.MINOR.PATCH"):
        _manifest(versions=[{"method_version": "1.0", "status": "current"}])
    with pytest.raises(ValueError, match="not in the models schema"):
        _manifest(outputs=["bonds.quotes"])
    with pytest.raises(ValueError):
        _manifest(minimum_tier="free")             # tiers live in config/entitlements.yaml, not in a manifest


# --- registry -------------------------------------------------------------------------------------------------

def test_the_repositorys_registry_is_valid():
    assert registry.check() == []


def test_dependency_order_puts_dependencies_first():
    order = registry.order(registry.load_all())
    assert order.index("bond_identity") < order.index("bond_ns_curve") < order.index("bond_rv_zscores")
    assert order.index("bond_execution_gap") < order.index("bond_carry")


def test_a_cycle_is_refused():
    a = _manifest(name="a", versions=[{"method_version": "1.0.0", "status": "current",
                                       "requires_models": {"b": "1.0.0"}}])
    b = _manifest(name="b", versions=[{"method_version": "1.0.0", "status": "current",
                                       "requires_models": {"a": "1.0.0"}}])
    with pytest.raises(ValueError, match="cycle"):
        registry.order({"a": a, "b": b})


def test_registry_reports_a_broken_plugin(tmp_path: Path):
    good = Path(fw.MODELS_DIR / "bond_execution_gap")
    broken = tmp_path / "bond_execution_gap"
    broken.mkdir()
    manifest = yaml.safe_load((good / "manifest.yaml").read_text())
    manifest["title_key"] = "models.nope.title"
    manifest["outputs"] = ["models.no_such_table"]
    manifest["requires_datasets"] = ["bonds.no_such_view"]
    (broken / "manifest.yaml").write_text(yaml.safe_dump(manifest))
    (broken / "compute.py").write_text("def something_else():\n    pass\n")   # no compute(), no METHOD.md
    problems = "\n".join(registry.check(tmp_path))
    for expected in ("compute.py must define", "METHOD.md is missing", "models.nope.title",
                     "models.no_such_table", "bonds.no_such_view"):
        assert expected in problems


def test_web_export_is_up_to_date():
    """web/lib/generated/registry.json is what the site's tier check reads; it must match the manifests."""
    assert registry.WEB_EXPORT.read_text() == registry.web_export_text(registry.load_all())


# --- inputs ---------------------------------------------------------------------------------------------------

@pytest.mark.db
def test_a_model_can_read_only_what_it_declares(conn):
    m = _manifest()
    inputs = fw.Inputs(conn, m, m.current, owners={"models.bond_curve_fit": "bond_ns_curve"})
    assert inputs.rows("bonds.trades_current") == []
    with pytest.raises(fw.UndeclaredInput):
        inputs.rows("bonds.quotes")
    with pytest.raises(fw.UndeclaredInput):                    # another model's output, not pinned
        inputs.rows("models.bond_curve_fit")


@pytest.mark.db
def test_a_model_sees_only_the_pinned_version_of_another_models_outputs(conn):
    run_id = conn.execute("insert into models.runs (model, method_version, code_version) values "
                          "('bond_ns_curve', '1.0.0', 'test') returning run_id").fetchone()["run_id"]
    for version, beta0 in (("1.0.0", 10.0), ("2.0.0", 20.0)):
        conn.execute("""insert into models.bond_curve_fit (method_version, obs_date, beta0, beta1, beta2, lambda_years,
                        n_quotes, rmse_bp, n_trades, run_id) values (%s, '2026-10-01', %s, 0, 0, 2.8, 10, 1, 0, %s)""",
                     (version, beta0, run_id))
    m = _manifest(versions=[{"method_version": "1.0.0", "status": "current",
                             "requires_models": {"bond_ns_curve": "2.0.0"}}])
    inputs = fw.Inputs(conn, m, m.current, owners={"models.bond_curve_fit": "bond_ns_curve"})
    assert [r["beta0"] for r in inputs.rows("models.bond_curve_fit")] == [20.0]
    first = inputs.fingerprint
    inputs.rows("models.bond_curve_fit")
    assert inputs.fingerprint != first                          # every read is fingerprinted


# --- writing --------------------------------------------------------------------------------------------------

def _run(conn) -> int:
    return conn.execute("insert into models.runs (model, method_version, code_version) values "
                        "('toy', '1.0.0', 'test') returning run_id").fetchone()["run_id"]


def _gap(day: str, gap: float) -> dict:
    return {"obs_date": day, "gap_bp": gap, "n": 10, "window_days": 20}


@pytest.mark.db
def test_writes_are_idempotent_and_every_change_is_kept(conn):
    table = "models.bond_execution_gap"
    first = fw.write_table(conn, table, [_gap("2026-10-01", 5.0), _gap("2026-10-02", 6.0)],
                           method_version="1.0.0", run_id=_run(conn))
    assert (first.inserted, first.updated, first.deleted) == (2, 0, 0)
    again = fw.write_table(conn, table, [_gap("2026-10-01", 5.0 + 1e-13), _gap("2026-10-02", 6.0)],
                           method_version="1.0.0", run_id=_run(conn))
    assert (again.inserted, again.updated, again.unchanged) == (0, 0, 2)      # last-bit noise is not a change
    changed = fw.write_table(conn, table, [_gap("2026-10-01", 7.5)], method_version="1.0.0", run_id=_run(conn))
    assert (changed.updated, changed.deleted) == (1, 1)
    revisions = conn.execute("select row_key, old_row, new_row from models.revisions order by revision_id").fetchall()
    assert revisions[0]["old_row"]["gap_bp"] == 5.0 and revisions[0]["new_row"]["gap_bp"] == 7.5
    assert revisions[1]["row_key"] == {"method_version": "1.0.0", "obs_date": "2026-10-02"}
    assert revisions[1]["new_row"] is None
    with pytest.raises(Exception, match="append-only"):
        conn.execute("delete from models.revisions")


@pytest.mark.db
def test_versions_never_mix(conn):
    table = "models.bond_execution_gap"
    fw.write_table(conn, table, [_gap("2026-10-01", 5.0)], method_version="1.0.0", run_id=_run(conn))
    fw.write_table(conn, table, [_gap("2026-10-01", 9.0)], method_version="2.0.0", run_id=_run(conn))
    fw.write_table(conn, table, [], method_version="2.0.0", run_id=_run(conn))
    rows = conn.execute(f"select method_version, gap_bp from {table}").fetchall()
    assert rows == [{"method_version": "1.0.0", "gap_bp": 5.0}]


@pytest.mark.db
def test_duplicate_keys_and_unknown_columns_are_refused(conn):
    with pytest.raises(fw.DuplicateOutputKey):
        fw.write_table(conn, "models.bond_execution_gap", [_gap("2026-10-01", 1.0), _gap("2026-10-01", 2.0)],
                       method_version="1.0.0", run_id=_run(conn))
    with pytest.raises(KeyError, match="unknown column"):
        fw.write_table(conn, "models.bond_execution_gap", [{**_gap("2026-10-01", 1.0), "advice": "x"}],
                       method_version="1.0.0", run_id=_run(conn))


def test_values_are_coerced_to_the_column_type():
    import numpy as np
    import pandas as pd
    assert fw._coerce(np.float64(1.5), "double precision") == 1.5
    assert fw._coerce(float("nan"), "double precision") is None
    assert fw._coerce(pd.Timestamp("2026-10-01"), "date") == dt.date(2026, 10, 1)
    assert fw._coerce("2026-10-01", "date") == dt.date(2026, 10, 1)
    assert fw._coerce(np.int64(3), "integer") == 3
    with pytest.raises(ValueError):
        fw._coerce(2.5, "integer")


@pytest.mark.db
def test_a_failed_run_is_recorded_and_writes_nothing(conn, monkeypatch):
    m = _manifest()

    def boom(inputs, as_of):
        raise RuntimeError("bad input")

    monkeypatch.setattr(fw, "compute_function", lambda name: boom)
    with pytest.raises(RuntimeError):
        fw.run_version(conn, m, m.current, code_version="test", owners={})
    run = conn.execute("select status, message from models.runs").fetchone()
    assert run["status"] == "failed" and "bad input" in run["message"]


@pytest.mark.db
def test_a_model_returning_undeclared_tables_fails(conn, monkeypatch):
    m = _manifest()
    monkeypatch.setattr(fw, "compute_function", lambda name: lambda inputs, as_of: {"models.bond_carry": []})
    with pytest.raises(fw.OutputMismatch):
        fw.run_version(conn, m, m.current, code_version="test", owners={})


@pytest.mark.db
def test_same_inputs_different_outputs_is_flagged_as_nondeterministic(conn, monkeypatch):
    m = _manifest()
    values = iter([1.0, 2.0])
    monkeypatch.setattr(fw, "compute_function",
                        lambda name: lambda inputs, as_of: {"models.bond_execution_gap": [_gap("2026-10-01", next(values))]})
    fw.run_version(conn, m, m.current, code_version="test", owners={})
    fw.run_version(conn, m, m.current, code_version="test", owners={})
    last = conn.execute("select message from models.runs order by run_id desc limit 1").fetchone()
    assert last["message"].startswith("NONDETERMINISTIC")


@pytest.mark.db
def test_an_as_of_run_never_writes(conn):
    m = _manifest()
    with pytest.raises(ValueError, match="compute-only"):
        fw.run_version(conn, m, m.current, code_version="test", owners={}, as_of=dt.date(2026, 10, 1))
    assert conn.execute("select count(*) n from models.runs").fetchone()["n"] == 0


@pytest.mark.db
def test_one_failing_model_does_not_stop_the_others(conn, monkeypatch):
    from data_platform.jobs import models as job

    def compute_for(name):
        if name == "bond_identity":
            def boom(inputs, as_of):
                raise RuntimeError("identity broke")
            return boom
        return original(name)

    original = fw.compute_function
    monkeypatch.setattr(fw, "compute_function", compute_for)
    with pytest.raises(job.ModelRunFailed) as caught:
        job.run(conn, ["bond_identity", "bond_ns_curve", "cse_market_tape"])
    text = " ".join(caught.value.failures)
    assert "identity broke" in text and "bond_ns_curve 2.0.0: skipped" in text
    ran = {(r.model, r.method_version) for r in caught.value.results}
    assert ("cse_market_tape", "1.0.0") in ran               # an unrelated model still ran
    order = [r["model"] + " " + r["method_version"] for r in conn.execute(
        "select model, method_version from models.runs where model = 'bond_identity' order by run_id")]
    assert order[0] == "bond_identity 2.0.0"                 # the version the site shows runs first
