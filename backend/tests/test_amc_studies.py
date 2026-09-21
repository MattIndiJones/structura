"""Offline regressions for generic Studies, independent of a real AMC."""
import datetime as dt
import json
from types import SimpleNamespace
import numpy as np
import pandas as pd
import pytest
from backend.app.core import amc_bh, amc_controls, amc_blocks, amc_engine, amc_prices
from backend.app.core import amc_riskmanagement as risk
from backend.app.core import amc_stockpicking as picking
from backend.app.core.amc_manifest import ManualParams, BlockToggles
from backend.app.core.fifo.loader import _order_from_item, load_orders
from backend.app.core.amc_confidence import build_confidence
from backend.app.core.amc_managerskill import compute_manager_skill_score


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    import yfinance
    def forbidden(*args, **kwargs):
        raise AssertionError("Unexpected market network call")
    monkeypatch.setattr(yfinance, "download", forbidden)
    monkeypatch.setattr(yfinance, "Ticker", forbidden)


def nav(values, start="2025-01-01"):
    return [{"date": d.strftime("%Y-%m-%d"), "nav": v} for d, v in zip(pd.bdate_range(start, periods=len(values)), values)]


def item(**overrides):
    return {"id": "trade1", "state": "Done", "executedQuantity": 10,
            "orderedQuantity": 20, "tradeDate": "2025-01-02",
            "executionPrice": {"amount": 100, "currency": "USD"}, "usedFxRate": 1,
            "underlying": {"isin": "TEST_A", "name": "Asset A"}, **overrides}


@pytest.mark.parametrize("field,value", [("management_fee_pct", -1), ("perf_fee_pct", 100),
    ("rolling_window", 0), ("conviction_weight_pct", 101), ("recon_mode", "unknown"), ("txn_cost_pct", float("nan"))])
def test_invalid_manifest_rejected(field, value):
    with pytest.raises(ValueError): ManualParams(**{field: value})


def test_execution_zero_never_uses_ordered_quantity():
    assert _order_from_item(item(executedQuantity=0), "USD") is None
    assert _order_from_item(item(state="Cancelled"), "USD") is None
    assert _order_from_item(item(state="Filled", executedQuantity=-3), "USD").qty == -3


def test_fx_required_only_across_currencies():
    assert _order_from_item(item(usedFxRate=None), "USD").fx == 1
    with pytest.raises(ValueError): _order_from_item(item(usedFxRate=None), "EUR")
    with pytest.raises(ValueError): _order_from_item(item(usedFxRate=float("nan")), "USD")


def test_duplicate_conflicting_execution_rejected(tmp_path):
    paths = []
    for i, trade in enumerate([item(), item(executedQuantity=5)]):
        p = tmp_path / f"{i}.json"
        p.write_text(json.dumps({"data": {"orders": {"items": [trade]}}}))
        paths.append(p)
    with pytest.raises(ValueError, match="contradictoires"): load_orders(paths, "USD")
    assert len(load_orders([paths[0], paths[0]], "USD")) == 1


def test_price_cutoff_and_staleness():
    s = pd.Series([100, 999], index=pd.to_datetime(["2025-01-01", "2025-02-01"]))
    assert amc_controls.price_at(s, "2025-01-03") == 100
    with pytest.raises(ValueError): amc_controls.price_at(s, "2025-01-20")
    with pytest.raises(ValueError): amc_controls.price_at(s, "2024-12-31")


def test_input_paths_confined_and_ambiguous(tmp_path):
    (tmp_path / "a.json").write_text("{}")
    (tmp_path / "b.json").write_text("{}")
    with pytest.raises(ValueError): amc_controls.resolve_file(str(tmp_path), "../secret.json")
    with pytest.raises(ValueError): amc_controls.resolve_file(str(tmp_path), "*.json")
    assert amc_controls.resolve_file(str(tmp_path), "a.json") == str(tmp_path / "a.json")


def test_bh_cutoff_and_cash_not_renormalized(monkeypatch):
    dates = pd.to_datetime(["2025-01-01", "2025-01-02", "2025-04-01"])
    frame = pd.DataFrame({"close": [100, 110, 150]}, index=dates)
    frame.attrs["currency"] = "USD"
    monkeypatch.setattr(amc_bh, "load_prices", lambda key: frame)
    ts = [{"isin": "TEST_A", "name": "A", "weight_pct": 50, "qty_per_cert": 1, "ccy": "USD"}]
    result = amc_bh.compute_bh(nav([100, 105]), "USD", ts, 10)
    assert result["available"]
    assert result["bh_nav"] == pytest.approx(105)
    assert result["value_added_pct"] == pytest.approx(0)
    assert result["cash_weight_pct"] == 50
    assert not result["comparable_costs"]


def test_full_redemption_zero_outstanding():
    rows = [{"date": "2025-01-01", "nav": 100, "outstanding": 10},
            {"date": "2025-01-02", "nav": 110, "outstanding": 0}]
    result = amc_blocks._nav_reconciliation(rows, None, "2025-01-02")
    assert result["nav_value_prod"] == 0
    assert result["nav_implied_pnl_prod"] == 100
    assert result["net_subscriptions_prod"] == -100


def test_missing_initial_outstanding_not_backfilled():
    rows = [{"date": "2025-01-01", "nav": 100}, {"date": "2025-01-02", "nav": 110, "outstanding": 10}]
    assert amc_blocks._nav_reconciliation(rows, None, "2025-01-02") is None


def test_drawdown_includes_first_loss():
    returns = risk._nav_to_returns(nav([100, 50, 50]))
    assert risk._drawdown_series(returns).min() == -.5


def test_downside_uses_zero_target_and_compounds_weeks():
    returns = pd.Series([-.1, -.1, .2, .1, .1])
    result = risk._score_downside_risk(returns)
    assert result["semi_deviation_ann_pct"] == pytest.approx(round(np.sqrt(.02 / 5 * 252) * 100, 2))
    assert result["worst_week_pct"] == pytest.approx(round((.9*.9*1.2*1.1*1.1-1)*100, 2))
    assert np.isfinite(result["sortino_ratio"])


def test_monthly_nav_not_annualized_as_daily():
    with pytest.raises(ValueError): risk._nav_to_returns([{"date": "2025-01-01", "nav": 100}, {"date": "2025-02-01", "nav": 110}])


def test_missing_benchmark_never_called_alpha(monkeypatch):
    monkeypatch.setattr(picking, "_get_benchmark_series", lambda ticker: None)
    result = picking.compute_stockpicking_score([{"state": "Done", "side": "BUY", "executed_qty": 1, "date": dt.datetime(2025, 1, 1)}])
    assert not result["available"]
    assert result.get("score") is None


def test_overlapping_trades_not_independent_samples():
    result = amc_controls.clustered_mean_test([.01, .03] * 50, ["A"] * 100)
    assert result["n_independent_groups"] == 1
    assert not result["inference_available"]
    assert result["pvalue"] == 1


def test_timing_only_cannot_publish_manager_skill():
    result = compute_manager_skill_score({"block_h": {"available": True, "global_score_mean": 1, "coverage_pct": 100}})
    assert not result["available"]


def test_empty_book_no_fixed_ninety_percent_confidence():
    result = build_confidence({"B_attribution"}, None, 0, block_b_result={"totals": {}}, data_quality={"status": "ready"})
    assert result["overall_pct"] == 0
    assert result["metric"] == "data_coverage"


def test_benchmark_regression_does_not_fill_missing_returns(monkeypatch):
    dates = pd.bdate_range("2025-01-01", periods=80)
    rng = np.random.default_rng(32)
    factors = pd.DataFrame({"Mkt-RF": rng.normal(0, .01, 80), "SMB": rng.normal(0, .005, 80), "HML": rng.normal(0, .005, 80), "RF": .0001}, index=dates)
    rows = [{"date": str(d.date()), "nav": v} for d, v in zip(dates, 100*np.cumprod(1+rng.normal(.0002,.01,80)))]
    monkeypatch.setattr(amc_engine, "_load_ff_data", lambda key: factors)
    monkeypatch.setattr(amc_engine, "_download_benchmark", lambda *args: pd.Series(rng.normal(0,.01,30), index=dates[-30:]))
    result = amc_engine.run_analysis(rows, [], [], {}, "US_3F", ["Mkt-RF", "SMB", "HML"], "SPY", 20)
    assert result["benchmark_regression"]["n_obs"] == 30


def test_nav_only_study_has_no_fifo_dependency(tmp_path, monkeypatch):
    from backend.app.core import amc_study, amc_orderbook
    csv = tmp_path / "nav.csv"
    csv.write_text("date,nav\n2025-01-01,100\n2025-01-02,101\n")
    monkeypatch.setattr(amc_orderbook, "load_nav", lambda _: nav([100, 101]))
    monkeypatch.setattr(amc_prices, "auto_populate_store", lambda *a: None)
    monkeypatch.setattr(amc_prices, "build_marks", lambda *a, **k: {})
    monkeypatch.setattr(amc_study, "run_fifo_recon", lambda *a, **k: pytest.fail("FIFO called for NAV-only study"))
    blocks = {key: False for key in BlockToggles.model_fields}
    result = amc_study.run_study({"product": {"isin": "GENERIC", "currency": "EUR"}, "files": {"nav_timeseries": "nav.csv"}, "blocks": blocks}, str(tmp_path))
    assert result["meta"]["as_of"] == "2025-01-02"
    assert result["provenance"]["input_hashes"]["nav.csv"]
    assert all(v == "skipped" for v in result["block_status"].values())
    json.dumps(result, allow_nan=False)


def test_frozen_orders_do_not_rescan_directory():
    study = {"meta": {"as_of": "2025-01-02"}, "source_orders": [{"date": "2025-01-01", "id": "old"}, {"date": "2025-01-03", "id": "future"}]}
    assert [o["id"] for o in amc_controls.source_orders(study)] == ["old"]
    with pytest.raises(ValueError): amc_controls.source_orders({})


def test_price_mark_missing_fx_is_not_one(tmp_path, monkeypatch):
    path = tmp_path / "prices.parquet"
    frame = pd.DataFrame({"close": [110.]}, index=pd.to_datetime(["2025-01-02"]))
    frame.attrs["currency"] = "JPY"
    frame.to_parquet(path)
    monkeypatch.setattr(amc_prices, "_parquet_path", lambda key: path)
    monkeypatch.setattr(amc_prices, "get_fx_series", lambda *a: pd.Series(dtype=float))
    with pytest.raises(ValueError):
        amc_prices.build_marks([{"isin": "TEST_JP", "currency": "JPY"}], "2025-01-02", "USD")


def test_t0_allocations_and_fx_decomposition(monkeypatch):
    from backend.app.core.fifo.nav import build_initial_orders
    monkeypatch.setattr(amc_prices, "build_marks", lambda *a, **k: {"JP": 2.})
    monkeypatch.setattr(amc_prices, "get_fx_series", lambda *a: pd.Series([.01], index=pd.to_datetime(["2025-01-01"])))
    orders = build_initial_orders([{"isin": "JP", "name": "Japan", "ccy": "JPY", "weight_pct": 50, "qty_per_cert": 2}],
                                  10, 100, dt.date(2025,1,1), "USD")
    assert orders[0].qty == 250
    assert orders[0].price_local == 200
    assert orders[0].price_prod == 2
    assert orders[0].fx == .01
    assert orders[0].qty * orders[0].price_prod == 500


def test_execution_series_undoes_only_future_splits(monkeypatch):
    frame = pd.DataFrame({"close": [8, 9], "price_close": [10, 11]}, index=pd.to_datetime(["2025-01-01", "2025-01-02"]))
    frame.attrs["adjustment_date"] = "2025-03-01"
    monkeypatch.setattr(amc_prices, "load_prices", lambda key: frame)
    monkeypatch.setattr(amc_prices, "get_split_calendar", lambda *a: {dt.date(2025,2,1): 10})
    prices = amc_prices.execution_series("A", "A", "2025-01-02")
    assert prices.tolist() == [100,110]


def test_fifo_exact_lots_and_price_fx_identity():
    from backend.app.core.fifo.engine import reconstruct
    from backend.app.core.fifo.schema import Order
    from backend.app.core.amc_fifo_adapter import fifo_to_legacy_recon
    buy = Order("buy", dt.date(2025,1,1), "A", "A", 10, 100, "JPY", .01, 1)
    sell = Order("sell", dt.date(2025,1,2), "A", "A", -4, 120, "JPY", .02, 2.4)
    result = reconstruct([buy, sell], {"A": 2.4}, dt.date(2025,1,2), "USD", recon_mode="strict")
    assert result.open_positions[0].open_qty == 6
    assert result.round_trips[0].pnl_prod == pytest.approx(5.6)
    adapted = fifo_to_legacy_recon(result, [buy, sell], dt.date(2025,1,2), "USD")
    row = adapted.round_trips[0]
    assert row["price_pnl"] + row["fx_pnl"] == pytest.approx(row["pnl_prod"])


def test_brinson_reconciles_its_proxy_and_preserves_cash(monkeypatch):
    from backend.app.core import amc_brinson as brinson
    dates = pd.bdate_range("2025-01-01", periods=30)
    prices = {}
    rows, termsheet = [], []
    for name in ("A", "B"):
        frame = pd.DataFrame({"close": np.linspace(100,120,30)}, index=dates)
        frame.attrs["currency"] = "USD"
        prices[amc_prices._slug(name)] = frame
        rows.append({"isin": name, "name": name, "weight": .25})
        termsheet.append({"isin": name, "name": name, "weight_pct": 25})
    monkeypatch.setattr(brinson, "_series_total_return", lambda *a: .1)
    monkeypatch.setattr(brinson, "_get_benchmark_sector_weights", lambda *a: ({"Technology": 1.}, "test"))
    monkeypatch.setattr(brinson, "_get_sector_etf_returns", lambda *a: {"Technology": .2})
    monkeypatch.setattr(amc_prices, "_load_ticker_map", lambda: {})
    study = {"meta": {"nav_start_date": str(dates[0].date()), "as_of": str(dates[-1].date())},
             "block_b": {"per_name": rows}, "termsheet_basket": termsheet}
    result = brinson.compute_brinson(study, prices, "SPY", "USD", cached_sectors={"A": "Technology", "B": "Technology"})
    assert result["available"]
    assert result["port_return_pct"] == 10
    assert result["check_pct"] == result["active_return_pct"] == -10
    assert result["actual_benchmark_return_pct"] == 10
    assert result["benchmark_proxy_gap_pct"] == 10


def test_study_files_scope_and_concurrency(tmp_path, monkeypatch):
    from backend.app.api.amc_access import study_folder, study_slot
    from fastapi import HTTPException
    root = tmp_path / "studies"
    mine = root / "42"
    mine.mkdir(parents=True)
    monkeypatch.setenv("STRUCTURA_STUDIES_ROOT", str(root))
    user = SimpleNamespace(id=42, role="user")
    assert study_folder(str(mine), user) == str(mine)
    with pytest.raises(HTTPException) as error: study_folder(str(tmp_path), user)
    assert error.value.status_code == 403
    with study_slot(), study_slot():
        with pytest.raises(HTTPException) as error:
            with study_slot(): pass
        assert error.value.status_code == 429
    with study_slot(): pass


def test_complete_generic_study_uses_only_manifest_and_nav_cutoff(tmp_path, monkeypatch):
    from backend.app.core.amc_study import run_study
    (tmp_path / "nav.csv").write_text("Date,Price,Outstanding quantity\n01.01.2025,100,10\n02.01.2025,110,10\n")
    sell = item(executedQuantity=-4, orderedQuantity=-4, executionPrice={"amount": 110, "currency": "USD"})
    future = item(id="future", tradeDate="2025-03-01", executedQuantity=-100)
    (tmp_path / "selected.json").write_text(json.dumps({"data": {"orders": {"items": [sell, future]}}}))
    (tmp_path / "ignored Data.json").write_text("invalid json intentionally outside manifest")
    product = {"isin": "GENERIC", "name": "Generic AMC", "currency": "USD", "outstandingQuantity": 10,
        "netAssetValue": {"date": "2025-01-02", "value": 110},
        "components": [{"underlying": {"isin": "TEST_A", "name": "Asset A", "currency": "USD"}, "position": 6, "weight": .6},
                       {"underlying": {"name": "USD", "currency": "USD"}, "position": 440, "weight": .4}]}
    (tmp_path / "Def.txt").write_text(json.dumps({"data": {"products": {"items": [product]}}}))
    (tmp_path / "termsheet_positions.json").write_text("[]")
    monkeypatch.setattr(amc_prices, "split_factor_between", lambda *a: 1.)
    monkeypatch.setattr(amc_prices, "auto_populate_store", lambda *a: None)
    monkeypatch.setattr(amc_prices, "build_marks", lambda components, as_of_date, prod_ccy, **k:
                        {c["isin"]: 100. if as_of_date == "2025-01-01" else 110. for c in components if c.get("isin")})
    frame = pd.DataFrame({"close": [100.,110.,900.]}, index=pd.to_datetime(["2025-01-01","2025-01-02","2025-03-01"]))
    frame.attrs["currency"] = "USD"
    monkeypatch.setattr(amc_bh, "load_prices", lambda *a: frame)
    blocks = {key: key in ["B_attribution", "C_trading", "D_behaviour", "E_bh"] for key in BlockToggles.model_fields}
    manifest = {"product": {"isin": "GENERIC", "currency": "USD"},
        "files": {"composition": "Def.txt", "nav_timeseries": "nav.csv", "orders": ["selected.json"]},
        "params": {"recon_mode": "strict", "n_certs": 10, "termsheet_positions": [{"isin": "TEST_A", "name": "Asset A", "weight_pct": 100, "qty_per_cert": 1, "ccy": "USD"}]}, "blocks": blocks}
    result = run_study(manifest, str(tmp_path))
    assert result["meta"]["n_orders"] == 1
    assert result["meta"]["fifo"]["as_of"] == "2025-01-02"
    assert result["meta"]["fifo"]["initial_orders"] == 1
    assert result["block_b"]["totals"]["reconciliation"]["gap_aum_bps"] == 0
    assert result["block_e"]["value_added_pct"] == 0
    assert result["data_quality"]["status"] == "ready"
    assert result["synthetic_report"] == []
    assert len(result["source_orders"]) == 1
    json.dumps(result, allow_nan=False)


def test_saved_snapshot_archive_and_ownership(tmp_path):
    from sqlmodel import SQLModel, Session, create_engine
    from backend.app.api.amc_studies import create_study, get_study, export_study_archive, AmcStudyCreate
    from fastapi import HTTPException
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    user = SimpleNamespace(id=41, role="user")
    other = SimpleNamespace(id=42, role="user")
    result = {"meta": {"isin": "GENERIC"}, "_artifacts": {"brinson": {"check_pct": 1.25}, "ai": {"generation_id": "test"}}}
    with Session(engine) as session:
        saved = create_study(AmcStudyCreate(isin="GENERIC", result=result, synthese="Conclusion"), user, session)
        loaded = get_study(saved["id"], user, session)
        assert loaded["result"]["_artifacts"] == result["_artifacts"]
        assert loaded["result"]["_snapshot_integrity"]
        archive = export_study_archive(saved["id"], user, session)
        assert json.loads(archive.body)["synthese"] == "Conclusion"
        assert len(archive.headers["x-content-sha256"]) == 64
        with pytest.raises(HTTPException) as error: get_study(saved["id"], other, session)
        assert error.value.status_code == 404


def test_public_registration_requires_explicit_enable(monkeypatch):
    from backend.app.api.auth import register, RegisterRequest
    from fastapi import HTTPException
    monkeypatch.delenv("STRUCTURA_ALLOW_REGISTRATION", raising=False)
    with pytest.raises(HTTPException) as error:
        register(RegisterRequest(username="testuser", password="password123", email="test@example.test"), None)
    assert error.value.status_code == 403


def test_timing_incomplete_future_window_excluded(monkeypatch):
    from backend.app.core.amc_timing import compute_timing_score
    dates = pd.bdate_range("2024-11-01", "2025-03-01")
    series = pd.Series(np.linspace(100,120,len(dates)), index=dates)
    monkeypatch.setattr(amc_prices, "execution_series", lambda *a: series)
    order = {"isin": "A", "name": "A", "state": "Done", "side": "BUY", "executed_qty": 1,
             "date": dt.datetime(2025,1,1), "price_local": 110}
    before = compute_timing_score([order], as_of="2025-01-10")
    assert not before["available"]
    after = compute_timing_score([order], as_of="2025-02-20")
    assert after["available"]
    assert not after["inference"]["inference_available"]
    assert "0,5" in after["interpretation"]


def test_backup_restore_integrity_and_no_overwrite(tmp_path):
    import sqlite3
    from backend.scripts.studies_backup import backup, restore
    db = tmp_path / "source.db"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE example(value INTEGER)")
        conn.execute("INSERT INTO example VALUES (42)")
    source = tmp_path / "manifest.json"
    source.write_text('{"isin":"GENERIC"}')
    archive = tmp_path / "backup.zip"
    backup(db, archive, [source])
    restored = tmp_path / "restored"
    restore(archive, restored)
    with sqlite3.connect(restored / "database/structura.db") as conn:
        assert conn.execute("SELECT value FROM example").fetchone()[0] == 42
    assert (restored / "sources/0/manifest.json").read_text() == source.read_text()
    with pytest.raises(ValueError): restore(archive, restored)
    with pytest.raises(ValueError): backup(db, archive)


def test_pdf_uses_saved_confidence_without_recomputing(monkeypatch):
    from backend.app.core import amc_pdf, amc_confidence
    monkeypatch.setattr(amc_confidence, "build_confidence", lambda *a, **k: pytest.fail("Confidence recomputed at export"))
    observed = []
    real_append = amc_pdf._append_confidence
    def capture(story, confidence, space):
        observed.append(confidence)
        return real_append(story, confidence, space)
    monkeypatch.setattr(amc_pdf, "_append_confidence", capture)
    confidence = build_confidence({"B_attribution"}, None, 0)
    data = {"meta": {"isin": "GENERIC", "currency": "EUR", "as_of": "2025-01-02"}, "confidence": confidence}
    pdf = amc_pdf.generate_study_pdf(data, company_name="Cabinet Test", client_name="Client Test")
    assert pdf.startswith(b"%PDF")
    assert observed == [confidence]


@pytest.mark.parametrize("currency", ["USD", "EUR"])
def test_provided_returns_cannot_override_nav_levels(currency):
    rows = nav([100,101,102,103,104])
    for row in rows: row["return"] = .5
    with pytest.raises(ValueError, match="contredisent"):
        amc_engine.run_analysis(rows, [], [], {}, "US_3F", ["Mkt-RF"], "SPY", 20, nav_currency=currency)
