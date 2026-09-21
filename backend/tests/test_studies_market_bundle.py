"""Portable, hand-calculable regressions for per-study market inputs."""
import datetime as dt
import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from backend.app.core.amc_market_bundle import MarketBundle, active_bundle, market_bundle
from backend.app.core.amc_controls import price_at, input_provenance
from backend.app.core.amc_manifest import ManualParams
from backend.app.core import amc_prices, amc_engine, amc_bh, amc_stockpicking


@pytest.fixture
def data():
    dates = ["2025-01-01", "2025-01-02", "2025-01-03"]
    return {"schema_version": "1.0", "assets": {"TEST": {"name": "Asset", "currency": "EUR",
        "sector": "Industrie", "adjustment_date": dates[-1], "splits": {dates[-1]: 2},
        "rows": [{"date": d, "close": c, "price_close": p} for d, c, p in zip(dates, [100, 110, 121], [50, 55, 59])]}},
        "fx_usd_per_local": {ccy: [{"date": d, "rate": r} for d, r in zip(dates, rates)]
            for ccy, rates in [("USD", [1, 1, 1]), ("EUR", [1.2, 1.25, 1.3])]},
        "benchmark": {"ticker": "LOCAL", "rows": [{"date": d, "close": v} for d, v in zip(dates, [100, 102, 103])]},
        "factors": {"series": "TEST", "columns": ["Mkt-RF", "RF"],
            "rows": [{"date": d, "Mkt-RF": -.01, "RF": 0} for d in dates]}}


def write(tmp_path, data, name="market.json"):
    (tmp_path / name).write_text(json.dumps(data), encoding="utf-8")
    return name


def test_gateways_use_only_declared_inputs(tmp_path, data, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Unexpected shared cache/network access")
    monkeypatch.setattr(amc_prices, "_parquet_path", forbidden)
    monkeypatch.setattr(amc_prices.yf, "Ticker", forbidden)
    with market_bundle(str(tmp_path), write(tmp_path, data)):
        assert amc_prices.load_prices("Asset").close.iloc[-1] == 121
        assert amc_prices.get_currency("TEST") == "EUR"
        assert amc_prices.get_fx_series("USD", "EUR").iloc[-1] == pytest.approx(1 / 1.3)
        assert amc_prices.execution_series("TEST", "Asset", "2025-01-03").iloc[-1] == 59
        assert amc_prices.split_factor_between("TEST", "Asset", dt.date(2025, 1, 1), dt.date(2025, 1, 3)) == 2
        assert amc_engine._load_ff_data("TEST")["Mkt-RF"].iloc[0] == -.01
        assert amc_engine._download_benchmark("LOCAL", "2025-01-01", "2025-01-03").iloc[0] == pytest.approx(.02)
        assert amc_stockpicking._get_benchmark_series("LOCAL").iloc[-1] == 103
        for call in [lambda: amc_prices.load_prices("MISSING"), lambda: amc_prices.get_fx_series("JPY", "USD"),
                     lambda: amc_stockpicking._get_benchmark_series("OTHER"), lambda: amc_engine._load_ff_data("OTHER")]:
            with pytest.raises(ValueError): call()
    assert active_bundle() is None


def test_causal_fx_and_staleness(tmp_path, data):
    with market_bundle(str(tmp_path), write(tmp_path, data)):
        fx = amc_prices.get_fx_series("EUR", "USD")
        assert price_at(fx, "2025-01-02") == 1.25
        assert price_at(fx, "2025-01-04") == 1.3
        with pytest.raises(ValueError): price_at(fx, "2024-12-31")
        with pytest.raises(ValueError): price_at(fx, "2025-01-11")
        with pytest.raises(ValueError): price_at(fx, "2025-01-04", max_age_days=0)


def test_reference_is_not_an_initial_fifo_position(tmp_path, data):
    params = ManualParams(reference_portfolio={"start_date": "2025-01-02", "positions": [
        {"isin": "TEST", "name": "Asset", "ccy": "EUR", "weight_pct": 80, "qty_per_cert": 1}]})
    assert params.termsheet_positions == []
    with market_bundle(str(tmp_path), write(tmp_path, data)):
        result = amc_bh.compute_bh([{"date": "2025-01-02", "nav": 100}, {"date": "2025-01-03", "nav": 105}],
            "USD", [p.model_dump() for p in params.reference_portfolio.positions])
    # 20% cash + 80% * 1.10 local return * 1.04 FX = 1.1152.
    assert result["bh_nav"] == 111.52
    assert result["value_added_pct"] == -6.52


@pytest.mark.parametrize("mutation", ["duplicate", "nan", "zero", "usd", "split"])
def test_invalid_bundle_rejected(data, mutation):
    if mutation == "duplicate": data["assets"]["TEST"]["rows"].append(data["assets"]["TEST"]["rows"][0])
    if mutation == "nan": data["assets"]["TEST"]["rows"][0]["close"] = float("nan")
    if mutation == "zero": data["fx_usd_per_local"]["EUR"][0]["rate"] = 0
    if mutation == "usd": data["fx_usd_per_local"]["USD"][0]["rate"] = 2
    if mutation == "split": data["assets"]["TEST"]["splits"]["2025-01-03"] = -2
    with pytest.raises(ValueError): MarketBundle(data)


def test_context_isolation_and_reset_on_failure(tmp_path, data):
    name = write(tmp_path, data)
    with market_bundle(str(tmp_path), name) as first:
        with ThreadPoolExecutor() as pool:
            assert pool.submit(active_bundle).result() is None
        with pytest.raises(RuntimeError):
            with market_bundle(str(tmp_path), ""):
                assert active_bundle() is None
                raise RuntimeError("stop")
        assert active_bundle() is first
    assert active_bundle() is None


def test_market_file_is_hashed_and_cannot_escape_folder(tmp_path, data):
    name = write(tmp_path, data)
    before = input_provenance(str(tmp_path), {"market_data": name}, {})
    data["assets"]["TEST"]["rows"][0]["close"] = 101
    write(tmp_path, data)
    assert before["input_hashes"] != input_provenance(str(tmp_path), {"market_data": name}, {})["input_hashes"]
    with pytest.raises(ValueError, match="appartenir"):
        with market_bundle(str(tmp_path), "../elsewhere.json"): pass


def test_brinson_period_must_match_declared_reference(data):
    data["brinson"] = {"start": "2025-01-02", "end": "2025-01-03", "weights": {"Industrie": 1}, "returns": {"Industrie": .1}}
    bundle = MarketBundle(data)
    assert bundle.sector_data("2025-01-02", "2025-01-03")["returns"]["Industrie"] == .1
    with pytest.raises(ValueError): bundle.sector_data("2025-01-01", "2025-01-03")


def test_secondary_endpoints_keep_bundle_reference_and_sync_coverage(tmp_path, data, monkeypatch):
    from backend.app.api import amc_prices as api
    from backend.app.core import amc_brinson
    name = write(tmp_path, data)
    manifest = {"files": {"market_data": name}}
    study = {"manifest": manifest, "meta": {"nav_start_date": "2025-01-01", "nav_start_value": 100},
        "reference_portfolio": {"start_date": "2025-01-02", "positions": [{"name": "Asset", "weight_pct": 80}]},
        "source_nav": [{"date": "2025-01-02", "nav": 105}],
        "provenance": input_provenance(str(tmp_path), manifest["files"], manifest)}
    monkeypatch.setattr(api, "study_folder", lambda folder, current: folder)
    def brinson(s, prices, **kwargs):
        assert active_bundle() is not None
        assert s["meta"]["nav_start_date"] == "2025-01-02"
        assert s["meta"]["nav_start_value"] == 105
        assert s["termsheet_basket"][0]["weight_pct"] == 80
        assert prices
        return {"available": True, "allocation_pct": -10}
    monkeypatch.setattr(amc_brinson, "compute_brinson", brinson)
    monkeypatch.setattr(amc_brinson, "save_price_cache", lambda *a: pytest.fail("Unexpected shared cache write"))
    response = api.compute_brinson_endpoint(api.BrinsonRequest(study_result=study, price_keys=[], folder=str(tmp_path)), None)
    assert response["study_result"]["confidence"]["rows"][0]["status"] == "indicative"
    assert active_bundle() is None
    def attribution(*args, **kwargs):
        assert active_bundle() is not None
        return {"available": True}
    monkeypatch.setattr(api, "compute_attribution", attribution)
    assert api.compute_attribution_endpoint(api.AttributionRequest(study_result=study, folder=str(tmp_path)), None)["available"]
    data["assets"]["TEST"]["rows"][0]["close"] = 999
    write(tmp_path, data)
    with pytest.raises(api.HTTPException) as exc:
        api.compute_brinson_endpoint(api.BrinsonRequest(study_result=study, price_keys=[], folder=str(tmp_path)), None)
    assert exc.value.status_code == 422
    assert "Sources modifiées" in exc.value.detail
