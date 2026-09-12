import json

import pytest
from fastapi import HTTPException

from backend.app.api.deals import DealCreate, _apply_pricing_receipt
from backend.app.core.payscript.parser import parse_script
from backend.app.core.schemas import PricingRequest
from backend.app.core.valuation_context import (
    ValuationContext,
    build_pricing_receipt,
    funding_from_market_snapshot,
    run_valuation,
    verify_pricing_receipt,
)


UL = [{"name": "S1", "ticker": "", "ccy": "EUR", "sigma": 0.2, "q": 0.0}]


def _request(**over):
    base = dict(
        script="AT MATURITY\n  PAY 1\n", underlyings=UL,
        corr_matrix=[[1.0]], r=0.03, T=1.0, N=2000, seed=17,
        funding_spread=0.015, barrier_monitoring="continuous",
        strike_date="2026-09-11", value_date="2026-09-15",
        payment_date="2027-09-17", settlement_ccy="EUR",
    )
    base.update(over)
    return PricingRequest(**base)


def test_preuve_pricing_fige_funding_seed_globale_monitoring_et_unites():
    receipt = build_pricing_receipt(_request(), 0.975)
    market = receipt["market_snapshot"]

    assert market["funding"]["level"] == pytest.approx(1.5)
    assert market["funding_spread"] == pytest.approx(0.015)
    assert market["seed"] == 42
    assert market["N"] == 2000
    assert market["barrierMonitoring"] == "continuous"
    assert market["underlyings"][0]["sigma"] == pytest.approx(20.0)
    assert receipt["price_pct"] == pytest.approx(97.5)
    assert verify_pricing_receipt(receipt)["input_fingerprint"] == receipt["input_fingerprint"]


def test_preuve_modifiee_est_refusee():
    receipt = build_pricing_receipt(_request(), 0.975)
    receipt = json.loads(json.dumps(receipt))
    receipt["pricing_input"]["funding_spread"] = 0.02

    with pytest.raises(ValueError, match="empreinte"):
        verify_pricing_receipt(receipt)


def test_ancien_deal_sans_funding_devient_explicitement_zero():
    assert funding_from_market_snapshot({"r": 3.0}) == ([], 0.0)


def test_courbe_funding_prolonge_son_dernier_niveau_apres_son_dernier_pilier():
    market = {"funding_curve": [[1.0, 0.01], [2.0, 0.015]]}
    assert funding_from_market_snapshot(market, elapsed=2.5) == ([], 0.015)


def test_run_valuation_transmet_tout_le_contexte(monkeypatch):
    captured = {}

    def fake_run_mc(**kwargs):
        captured.update(kwargs)
        return {"price": 1.0}

    monkeypatch.setattr("backend.app.core.payscript.engine.run_mc", fake_run_mc)
    context = ValuationContext(
        underlyings=UL, corr_matrix=[[1.0]], r=0.03, T=1.0, N=2000,
        model="constant", seed=17, antithetic=False,
        funding_spread=0.015, maturity_payment_t=1.02,
        value_date_t=0.01, strike_set_t=0.05,
        state={"spot_mult": [0.9], "spot_base": [0.9]},
    )

    run_valuation(parse_script("AT MATURITY\n  PAY 1\n"), context, dr=0.01)

    assert captured["seed"] == 17
    assert captured["antithetic"] is False
    assert captured["funding_spread"] == pytest.approx(0.015)
    assert captured["maturity_payment_t"] == pytest.approx(1.02)
    assert captured["value_date_t"] == pytest.approx(0.01)
    assert captured["strike_set_t"] == pytest.approx(0.05)
    assert captured["spot_mult"] == [0.9]
    assert captured["dr"] == pytest.approx(0.01)


def test_un_scenario_ne_peut_pas_remplacer_le_calendrier_du_contexte():
    context = ValuationContext(
        underlyings=UL, corr_matrix=[[1.0]], r=0.03, T=1.0, N=2000,
        model="constant", maturity_payment_t=1.02,
    )
    with pytest.raises(ValueError, match="contexte de valorisation"):
        run_valuation(
            parse_script("AT MATURITY\n  PAY 1\n"), context,
            maturity_payment_t=2.0,
        )


def _deal_body(receipt, **over):
    base = dict(
        contrepartie="Banque", nominal=1_000_000, fair_value=97.5,
        price_traded=98.0, trade_date="2026-09-11",
        strike_date="2026-09-11", value_date="2026-09-15",
        maturity_date="2027-09-11", payment_date="2027-09-17", T=1.0,
        devise="EUR", underlyings=[{"name": "S1", "ticker": "", "ccy": "EUR"}],
        observation_times=[1.0], script_snapshot="AT MATURITY\n  PAY 1\n",
        market_snapshot={"r": 99}, pricing_receipt=receipt,
    )
    base.update(over)
    return DealCreate(**base)


def test_booking_utilise_le_snapshot_serveur_identifie():
    receipt = build_pricing_receipt(_request(), 0.975)
    body = _deal_body(receipt)

    _apply_pricing_receipt(body)

    assert body.market_snapshot["r"] == pytest.approx(3.0)
    assert body.market_snapshot["funding"]["level"] == pytest.approx(1.5)
    assert body.market_snapshot["pricing_input"] == receipt["pricing_input"]
    assert body.market_snapshot["pricing_price_pct"] == pytest.approx(97.5)


def test_booking_refuse_un_script_different_du_pricing():
    receipt = build_pricing_receipt(_request(), 0.975)
    body = _deal_body(receipt, script_snapshot="AT MATURITY\n  PAY 0\n")

    with pytest.raises(HTTPException) as caught:
        _apply_pricing_receipt(body)

    assert caught.value.status_code == 409
    assert caught.value.detail["code"] == "PRICING_RESULT_STALE"


def test_booking_refuse_une_maturite_numerique_differente_du_pricing():
    receipt = build_pricing_receipt(_request(), 0.975)
    body = _deal_body(receipt, T=2.0)

    with pytest.raises(HTTPException) as caught:
        _apply_pricing_receipt(body)

    assert caught.value.status_code == 409
