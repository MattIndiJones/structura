"""Resource admission controls for PayScript and Monte Carlo calculations."""

import pytest

from backend.app.core.compute_budget import (
    MAX_EXPANDED_DATES,
    MAX_SCRIPT_CHARS,
    MAX_SCRIPT_LINES,
    SYNC_MEMORY_LIMIT_BYTES,
    SYNC_WORK_LIMIT,
    ensure_budget,
    estimate_mc,
    estimate_mc_batch,
    estimate_pricing_request,
    validate_compiled_dates,
)
from backend.app.core.payscript.engine import run_mc, run_mc_paths, run_mc_proba
from backend.app.core.payscript.parser import parse_script
from backend.app.core.schemas import AnalysisBase, PricingRequest, UnderlyingParams


def test_parser_rejects_non_positive_date_range_steps_without_looping():
    for step in ("0", "0.0", "-0.25"):
        with pytest.raises(ValueError, match="strictement positif"):
            parse_script(f"AT 1..2:{step}:\n  PAY 1")


def test_parser_rejects_descending_and_non_progressing_date_ranges():
    with pytest.raises(ValueError, match="précède"):
        parse_script("AT 2..1:0.25:\n  PAY 1")
    with pytest.raises(ValueError, match="trop petit"):
        parse_script("AT 1..1.000000001:0.00000000001:\n  PAY 1")


def test_parser_caps_expanded_dates_and_source_size():
    with pytest.raises(ValueError, match=f"{MAX_EXPANDED_DATES:,}"):
        parse_script(f"AT 0.001..{MAX_EXPANDED_DATES + 1}:1:\n  PAY 1")
    with pytest.raises(ValueError, match="caractères"):
        parse_script("#" * (MAX_SCRIPT_CHARS + 1))
    with pytest.raises(ValueError, match="lignes"):
        parse_script("\n" * MAX_SCRIPT_LINES)


def test_resolved_script_caps_dates_across_multiple_events():
    compiled = parse_script(
        "AT 0.001..3:0.001:\n  PAY 1\n"
        "AT 3.001..6:0.001:\n  PAY 1"
    )
    with pytest.raises(ValueError, match="Calendrier trop volumineux"):
        validate_compiled_dates(compiled)


def test_pricing_estimate_includes_greek_reprices_without_stacking_memory():
    base = estimate_pricing_request(
        maturity_years=3,
        underlyings=2,
        paths=20_000,
        model="constant",
        antithetic=True,
        continuous_monitoring=False,
        stochastic_rates=False,
    )
    with_greeks = estimate_pricing_request(
        maturity_years=3,
        underlyings=2,
        paths=20_000,
        model="constant",
        antithetic=True,
        continuous_monitoring=False,
        stochastic_rates=False,
        selected_greeks=["delta", "gamma", "vega", "theta", "rho", "corr"],
    )
    assert with_greeks.work_units > base.work_units
    assert with_greeks.estimated_peak_bytes == base.estimated_peak_bytes
    assert with_greeks.repricings > 1


def test_pricing_estimate_includes_expanded_event_cost():
    without_events = estimate_pricing_request(
        maturity_years=3, underlyings=1, paths=20_000, model="constant",
        antithetic=True, continuous_monitoring=False, stochastic_rates=False,
    )
    with_events = estimate_pricing_request(
        maturity_years=3, underlyings=1, paths=20_000, model="constant",
        antithetic=True, continuous_monitoring=False, stochastic_rates=False,
        expanded_dates=100,
    )
    assert with_events.expanded_dates == 100
    assert with_events.work_units > without_events.work_units


def test_budget_rejects_memory_and_work_independently():
    memory_heavy = estimate_mc(
        operation="price", maturity_years=30, underlyings=12, paths=200_000,
        model="lsv", antithetic=False,
    )
    assert memory_heavy.estimated_peak_bytes > SYNC_MEMORY_LIMIT_BYTES
    with pytest.raises(ValueError, match="mémoire estimée"):
        ensure_budget(memory_heavy)

    work_heavy = estimate_mc(
        operation="price", maturity_years=10, underlyings=6, paths=100_000,
        model="constant", antithetic=True, repricings=10,
    )
    assert work_heavy.work_units > SYNC_WORK_LIMIT
    with pytest.raises(ValueError, match="coût estimé"):
        ensure_budget(work_heavy, memory_limit_bytes=10**15)


def test_batch_estimate_accounts_for_parallel_worker_memory():
    one = estimate_mc_batch(
        operation="grid", maturity_years=3, underlyings=1,
        paths_per_run=20_000, total_runs=10, model="constant",
        concurrent_runs=1,
    )
    four = estimate_mc_batch(
        operation="grid", maturity_years=3, underlyings=1,
        paths_per_run=20_000, total_runs=10, model="constant",
        concurrent_runs=4,
    )
    assert four.estimated_peak_bytes == 4 * one.estimated_peak_bytes
    assert four.work_units == one.work_units


def _pricing_payload(**overrides):
    payload = {
        "script": "AT MATURITY:\n  PAY 1",
        "underlyings": [{"name": "SX5E"}],
        "corr_matrix": [[1.0]],
    }
    payload.update(overrides)
    return payload


def test_request_schema_caps_maturity_assets_and_script_size():
    with pytest.raises(ValueError):
        PricingRequest(**_pricing_payload(T=30.01))
    with pytest.raises(ValueError):
        PricingRequest(**_pricing_payload(
            underlyings=[{"name": str(i)} for i in range(13)],
            corr_matrix=[[1.0]],
        ))
    with pytest.raises(ValueError):
        PricingRequest(**_pricing_payload(script="x" * (MAX_SCRIPT_CHARS + 1)))


def test_request_schema_rejects_non_finite_or_invalid_market_inputs():
    with pytest.raises(ValueError):
        PricingRequest(**_pricing_payload(r=float("nan")))
    with pytest.raises(ValueError):
        UnderlyingParams(sigma=-0.01)
    with pytest.raises(ValueError):
        AnalysisBase(**_pricing_payload(yield_curve=[[2, 0.03], [1, 0.02]]))


def test_engine_rejects_oversized_run_before_random_allocation(monkeypatch):
    compiled = parse_script("AT MATURITY:\n  PAY 1")

    def allocation_must_not_start(*_args, **_kwargs):
        raise AssertionError("Le générateur aléatoire ne doit pas être créé")

    monkeypatch.setattr(
        "backend.app.core.payscript.engine.default_rng", allocation_must_not_start)
    underlyings = [{"name": str(i), "sigma": 0.2, "q": 0.0} for i in range(12)]
    corr = [[1.0 if i == j else 0.0 for j in range(12)] for i in range(12)]
    with pytest.raises(ValueError, match="mémoire estimée"):
        run_mc(compiled, underlyings, corr, 0.03, 30, 200_000)


@pytest.mark.parametrize("runner", [run_mc_paths, run_mc_proba])
def test_analytic_engines_do_not_fall_back_to_gbm_for_unknown_model(runner):
    compiled = parse_script("AT MATURITY:\n  PAY 1")
    with pytest.raises(ValueError, match="Modèle inconnu"):
        runner(compiled, [{"name": "SX5E", "sigma": 0.2, "q": 0.0}],
               [[1.0]], 0.03, 1.0, model="typo")
