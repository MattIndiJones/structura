import math
from types import SimpleNamespace
import pytest
from backend.app.core.amc_managerskill import compute_manager_skill_score, _vag_score
from backend.app.core.amc_confidence import build_confidence
from backend.app.core.amc_blocks import block_b_attribution
from backend.app.core.amc_synthesize import build_synthesis_payload


def study():
    return {"meta": {"nav_start_date": "2000-01-01", "nav_current_date": "2025-01-01"},
        "block_e": {"available": True, "comparable_costs": False,
            "comparison_basis": "NAV nette / panier brut", "value_added_pct": -20,
            "period_start": "2023-01-01", "period_end": "2024-01-01"},
        "block_a": {"available": True, "net": {"regression": {"n_obs": 250}}},
        "block_i": {"available": True, "score": 50, "coverage_pct": 100, "inference": {"inference_available": True}},
        "block_j": {"available": True, "score": 50, "n_obs": 250},
        "block_h": {"available": True, "global_score_mean": .5, "coverage_pct": 100, "inference": {"inference_available": True}},
        "block_d": {"conviction_matrix": {"counts": {"conviction_winners": 1, "stubborn_losers": 1}}},
        "data_quality": {"status": "ready"}}


def test_negative_vag_included_at_twenty_percent_on_its_own_period():
    result = compute_manager_skill_score(study())
    vag = next(d for d in result["dimensions"] if d["key"] == "vag")
    expected = 50 + 50 * math.tanh((-20 * 365.25 / 365) / 20)
    assert vag["available"] and vag["weight_effective_pct"] == 20
    assert vag["score"] == round(expected, 1)
    assert result["score"] == round(40 + .2 * expected)
    assert result["score"] < 50
    assert vag["limitation"] and "net / panier passif brut" in result["interpretation"]


def test_undocumented_or_invalid_vag_not_silently_scored():
    s = study()
    del s["block_e"]["comparison_basis"]
    assert _vag_score(s) == (None, None)
    s["block_e"]["comparable_costs"] = True
    s["block_e"]["period_end"] = s["block_e"]["period_start"]
    assert _vag_score(s) == (None, None)


def test_brinson_calculated_is_indicative_not_missing():
    result = build_confidence({"G_brinson"}, None, 3, brinson_result={"available": True})
    row, = result["rows"]
    assert row["feasible"] and row["confidence_pct"] == 100
    assert row["status"] == "indicative" and not row["scoring_eligible"]
    assert "non intégrée au scoring" in row["missing_data"]
    missing = build_confidence({"G_brinson"}, None, 3, brinson_result={"available": False, "error": "Cours absents"})["rows"][0]
    assert not missing["feasible"] and missing["confidence_pct"] == 0
    assert missing["missing_data"] == "Cours absents"


@pytest.mark.parametrize("realized,fx,expected", [(100, -20, -20), (-100, -20, 20), (0, -20, None)])
def test_fx_ratio_uses_signed_realized_only(realized, fx, expected):
    recon = SimpleNamespace(round_trips=[{"isin": "X", "name": "X", "ccy": "USD", "pnl_prod": realized,
        "price_pnl": realized - fx, "fx_pnl": fx, "exit_quarter": "2025-Q1"}],
        open_positions=[{"isin": "X", "name": "X", "ccy": "USD", "unreal_pnl_prod": 10000}])
    result = block_b_attribution(recon, {"components": []})
    assert result["totals"]["fx_share_of_realized_pct"] == expected
    payload = build_synthesis_payload({"meta": {"currency": "USD"}, "block_b": result})
    assert "du P&L réalisé net signé, hors latent et dividendes" in payload


def test_drawdown_all_episodes_calendar_duration_and_recovery():
    import pandas as pd
    from backend.app.core.amc_riskmanagement import _compute_drawdown_episodes
    dates = pd.bdate_range("2025-01-03", periods=13)
    dd = pd.Series([-.1, 0] * 6 + [-.2], index=dates)
    episodes = _compute_drawdown_episodes(dd)
    assert len(episodes) == 7
    assert episodes[0]["recovered"] is False
    assert episodes[0]["duration_observations"] == 1
    friday = next(e for e in episodes if e["start_date"] == "2025-01-03")
    assert friday["duration_days"] == 3
    assert friday["duration_observations"] == 1


def test_risk_benchmark_includes_first_observed_return():
    import pandas as pd
    import numpy as np
    from backend.app.core.amc_riskmanagement import _score_risk_adjusted
    dates = pd.bdate_range("2025-01-01", periods=31)
    b = np.array([.1] + [.001, -.001] * 14 + [.002])
    f = b + np.linspace(-.002, .002, 30)
    benchmark = pd.Series(np.r_[100, 100*np.cumprod(1+b)], index=dates)
    result = _score_risk_adjusted(pd.Series(f, index=dates[1:]), benchmark, True, -10, 1)
    expected = (f-b).mean() / (f-b).std(ddof=1) * math.sqrt(252)
    assert result["information_ratio"] == round(expected, 3)


def test_brinson_current_weights_keep_cash_and_reject_missing_holdings():
    from backend.app.core.amc_brinson import _build_inception_weights
    rows = [{"name": "A", "weight": .6}, {"name": "USD", "weight": .4}]
    weights, method = _build_inception_weights(["A"], rows, "")
    assert weights.sum() == .6
    assert method == "current_composition"
    with pytest.raises(ValueError, match="incomplète"):
        _build_inception_weights(["A"], rows + [{"name": "B", "weight": .1}], "")


def test_secondary_brinson_updates_saved_coverage_and_identity_without_losing_other_rows():
    from backend.app.core.amc_confidence import attach_brinson
    old = {"confidence": {"rows": [{"dimension": "Dividendes", "confidence_pct": 100},
        {"dimension": "Brinson sur proxies (Bloc G)", "confidence_pct": 0}]},
        "provenance": {"result_hash": "before"}, "manager_skill_score": {"score": 50}}
    result = attach_brinson(old, {"available": True, "allocation_pct": -10})
    assert old["provenance"]["result_hash"] == "before"
    assert result["provenance"]["result_hash"] != "before"
    assert result["confidence"]["overall_pct"] == 100
    assert len(result["confidence"]["rows"]) == 2
    assert result["confidence"]["rows"][1]["status"] == "indicative"
    assert result["manager_skill_score"] == old["manager_skill_score"]


def test_descriptive_score_does_not_claim_significant_skill():
    result = compute_manager_skill_score(study())
    assert "ne démontre pas" in result["interpretation"]
    assert next(d for d in result["dimensions"] if d["key"] == "conviction")["label"] == "Taux de titres gagnants (D)"


def test_factor_drawdown_is_relative_to_peak_and_keeps_first_loss(monkeypatch):
    import pandas as pd
    import numpy as np
    from backend.app.core import amc_engine
    dates = pd.bdate_range("2025-01-01", periods=80)
    rng = np.random.default_rng(10)
    factors = pd.DataFrame({"Mkt-RF": rng.normal(0, .01, 80), "RF": 0}, index=dates)
    nav = np.array([100, 50, 100, 200, 150] + list(150 * np.cumprod(1+rng.normal(0,.001,75))))
    rows = [{"date": str(d.date()), "nav": float(v)} for d, v in zip(dates, nav)]
    monkeypatch.setattr(amc_engine, "_load_ff_data", lambda key: factors)
    monkeypatch.setattr(amc_engine, "_download_benchmark", lambda *args: pd.Series(dtype=float))
    result = amc_engine.run_analysis(rows, [], [], {}, "US_3F", ["Mkt-RF"], "NONE", 20)
    perf = result["performance"]
    assert perf["full_drawdown"][1] == -.5
    assert perf["full_drawdown"][4] == -.25
    assert perf["drawdown"][0] == -.5


def test_replicant_uses_unrounded_coefficients_and_rounds_gap_once():
    from backend.app.core.amc_replicability import compute_replicability
    result = compute_replicability({"available": True, "net": {
        "regression": {"factors": [{"name": "Mkt-RF", "beta": 0}],
                       "calculation": {"betas": {"Mkt-RF": .00004}, "r2": .3, "alpha_tstat": 0}},
        "data_used": [{"date": "2025-01-01", "Mkt-RF": 1, "RF": 0, "amc_ret": .00006}]}})
    assert result["replicant_nav"][0]["value"] == 100.004
    assert result["alpha_gap_pct"] == 0
    assert result["score_ci_kind"] == "sensitivity_r2_only"


def test_market_shocks_keep_multiple_orders_for_same_title_and_date():
    from backend.app.core.amc_marketshocks import compute_market_shocks
    orders = [{"state": "Done", "date": "2020-03-10", "isin": "X", "side": side, "notional_prod": 100} for side in ["BUY", "SELL"]]
    timing = {"available": True, "trades": [
        {"available": True, "date": "2020-03-10", "isin": "X", "score": score} for score in [.1, .9]]}
    result = compute_market_shocks(orders, {"nav_start_date": "2020-01-01", "as_of": "2020-12-31"}, timing)
    event = next(e for e in result["events"] if e["n_trades"] == 2)
    assert event["avg_timing_score"] == .5


@pytest.mark.parametrize("fund,replica,expected", [(10,-10,0), (-10,10,0), (0,10,0), (10,0,0), (0,0,100), (-10,-10,100)])
def test_factor_performance_matching_is_symmetric(fund, replica, expected):
    from backend.app.core.amc_replicability import _score
    _, components = _score(.5, replica, fund, 1)
    assert components["perf_coverage"] == expected
