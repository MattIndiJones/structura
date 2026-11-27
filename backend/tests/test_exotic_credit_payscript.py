"""Scripted credit amounts stay consistent across MC, references and archives."""

from copy import deepcopy
from datetime import date

import numpy as np
import pytest
from pydantic import ValidationError

from backend.app.core.product.credit_default import CreditDefaultDiscount, prepare_credit_default
from backend.app.core.product.credit_pilot import benchmark_terms, case_cutoff, july_facts
from backend.app.core.product.exotic_credit_mc import simulate_credit_mc
from backend.app.core.product.exotic_credit_payscript import CreditScriptSource, ExoticCreditScriptError, compile_credit_event
from backend.app.core.product.models import Product, TradeIntent
from backend.app.core.product.native_schedule import resolve_native_schedule
from backend.app.services.exotic_contract_profile import exotic_contract_profile
from backend.app.services.exotic_mtf import mark_exotic_to_future
from backend.app.services.exotic_valuation import read_scenario
from backend.tests.test_exotic_pricer_api import EXOTICS, _credit, _json, _price, native_recipe_client, product_client  # noqa: F401


def _scripts(coupon, default, *, cln=False):
    return {
        "profile": "credit-exotic-payoff-v1",
        "coupon": {"source": f"AT {'CLN_COUPON' if cln else 'CDS_PREMIUM'}:\n  PAY {coupon}"},
        "default": {"source": f"AT {'CLN_DEFAULT_REDEMPTION' if cln else 'CDS_PROTECTION'}:\n  PAY {default}"},
    }


def test_equivalent_native_and_scripted_paths_and_references_match():
    payload = _credit()
    original = read_scenario(payload).credit
    payload["credit"]["contract"]["payscript"] = _scripts("COUPON_RATE", "1 - RECOVERY_FRACTION")
    scripted = read_scenario(payload).credit
    native, script = (simulate_credit_mc(request, retain_samples=True) for request in (original, scripted))
    np.testing.assert_array_equal(native.dirty_samples, script.dirty_samples)
    assert native.result.reference == script.result.reference.model_copy(update={"payoff_basis": None})
    assert native.result.provenance.draw_fingerprint == script.result.provenance.draw_fingerprint
    assert native.result.provenance.market_fingerprint == script.result.provenance.market_fingerprint
    assert native.result.provenance.request_fingerprint != script.result.provenance.request_fingerprint
    assert "payscript" not in original.contract.model_dump(mode="json")
    assert "payscript_metadata" not in native.result.model_dump(mode="json")
    assert script.result.payscript_metadata.coupon.output_unit == "annual_fraction_of_nominal"
    assert script.result.payscript_metadata.default.output_unit == "fraction_of_nominal"


def test_scripted_coefficients_transform_pv_accrual_reference_and_profile_without_changing_survival():
    payload = _credit()
    payload["credit"]["contract"].update(trigger_rank=2, initial_accrued_fraction=.02, default_settlement_delay_years=.02)
    names = payload["credit"]["market"]["marginals"]
    for row, recovery in zip(names, (.2, .4, .7), strict=True):
        row["recovery_fraction"] = recovery
    native_payload = deepcopy(payload)
    payload["credit"]["contract"]["payscript"] = _scripts("COUPON_RATE", "0.5*(1-RECOVERY_FRACTION)*DEFAULT_RANK/2")
    payload["credit"]["contract"]["payscript"]["coupon"] = {
        "source": 'PARAM EXTRA = 0.3%\nAT CDS_PREMIUM:\n  PAY COUPON_RATE + EXTRA "Prime calculée"',
        "parameters": {"EXTRA": .005},
    }
    native_payload["credit"]["contract"]["coupon_bps"] = 150
    for row in native_payload["credit"]["market"]["marginals"]:
        row["recovery_fraction"] = 1 - .5 * (1 - row["recovery_fraction"])
    scripted, equivalent = (read_scenario(body) for body in (payload, native_payload))
    priced, oracle = (simulate_credit_mc(item.credit, retain_samples=True) for item in (scripted, equivalent))
    assert priced.result.provenance.draw_fingerprint == oracle.result.provenance.draw_fingerprint
    assert priced.result.survival == oracle.result.survival
    assert priced.result.default_count_at_maturity == oracle.result.default_count_at_maturity
    np.testing.assert_allclose(priced.dirty_samples, oracle.dirty_samples, rtol=0, atol=1e-9)
    assert priced.result.reference.dirty_pv_eur == pytest.approx(oracle.result.reference.dirty_pv_eur, abs=1e-9)
    assert priced.result.reference.accrual_on_default_pv_eur == pytest.approx(
        oracle.result.reference.accrual_on_default_pv_eur, abs=1e-9,
    )
    assert priced.result.reference.payoff_basis == "payscript_effective_amounts"
    assert priced.result.payscript_metadata.effective_coupon_rate == .015
    assert priced.result.payscript_metadata.coupon.parameters[0].value == .005
    assert [item.recovery_fraction for item in priced.result.payscript_metadata.member_amounts] == [.2, .4, .7]
    assert [item.payout_fraction for item in priced.result.payscript_metadata.member_amounts] == pytest.approx([.4, .3, .15])
    profile = exotic_contract_profile(scripted, points=(0., .40, 1.))
    assert profile.selected.calculation == "payscript"
    assert [point.amount_eur for point in profile.points] == pytest.approx([500_000, 300_000, 0])
    assert mark_exotic_to_future(scripted, horizons_years=(1.,), paths=64).horizons == (
        mark_exotic_to_future(equivalent, horizons_years=(1.,), paths=64).horizons
    )


@pytest.mark.parametrize("expression", ["RECOVERY_FRACTION", "MAX(0, RECOVERY_FRACTION-.25)"])
def test_cln_uses_scripted_default_redemption_and_principal_at_par_on_survival(expression):
    payload = _credit()
    payload["credit"]["contract"].update(kind="cln", trigger_rank=None, coupon_bps=200, side="SELL",
                                         payscript=_scripts("COUPON_RATE * 2", expression, cln=True))
    payload["credit"]["market"]["marginals"] = payload["credit"]["market"]["marginals"][:1]
    payload["credit"]["settings"]["estimator"] = "conditional_single_name"
    reference_payload = deepcopy(payload)
    del reference_payload["credit"]["contract"]["payscript"]
    reference_payload["credit"]["contract"]["coupon_bps"] = 400
    if expression.startswith("MAX"):
        reference_payload["credit"]["market"]["marginals"][0]["recovery_fraction"] = .15
    scripted, equivalent = (simulate_credit_mc(read_scenario(body).credit, retain_samples=True)
                             for body in (payload, reference_payload))
    np.testing.assert_allclose(scripted.dirty_samples, equivalent.dirty_samples, rtol=0, atol=1e-9)
    assert scripted.result.reference.survival_principal_pv_eur == equivalent.result.reference.survival_principal_pv_eur
    assert scripted.result.reference.default_redemption_pv_eur == pytest.approx(
        equivalent.result.reference.default_redemption_pv_eur, abs=1e-9,
    )


@pytest.mark.parametrize("source", [
    "AT CDS_PROTECTION:\n  PAY CMS_RATE",
    "AT CDS_PROTECTION:\n  PAY DEFAULT_TIME",
    "AT CDS_PROTECTION:\n  PAY 1\n  PAY 1",
    "PARAM RECOVERY_FRACTION = 40%\nAT CDS_PROTECTION:\n  PAY 1",
    "AT CLN_DEFAULT_REDEMPTION:\n  PAY RECOVERY_FRACTION",
])
def test_restricted_event_language_forbids_unqualified_observables_and_state(source):
    with pytest.raises(ExoticCreditScriptError):
        compile_credit_event(CreditScriptSource(source=source), "CDS_PROTECTION")


@pytest.mark.parametrize("payoff", ["1.001", "-0.1", "1/0", "RECOVERY_FRACTION > 0"])
def test_out_of_domain_outputs_fail_before_simulation(payoff):
    payload = _credit()
    payload["credit"]["contract"]["payscript"] = _scripts("COUPON_RATE", payoff)
    with pytest.raises(ExoticCreditScriptError):
        simulate_credit_mc(read_scenario(payload).credit)


def test_realized_credit_script_never_falls_back_to_template():
    terms = benchmark_terms("CLN", "JULY-DUE")
    product = Product(terms=terms, native_schedule=resolve_native_schedule(terms).schedule,
                      intent=TradeIntent(nominal=1_000_000))
    default_id, facts = july_facts("JULY-DUE")
    cutoff = case_cutoff("JULY-DUE")
    context = prepare_credit_default(
        product, valuation_date=cutoff.date(), cutoff=cutoff, default_id=default_id, facts=facts,
        reference_entity_id=terms.reference_entity_id, settlement_date=date(2021, 7, 20),
        discount=CreditDefaultDiscount(ois_rate=.02, cln_funding_bps=0),
    )
    body = _credit()
    body["credit"]["market"]["marginals"] = body["credit"]["market"]["marginals"][:1]
    body["credit"]["contract"].update(kind="cln", trigger_rank=None, coupon_bps=400,
                                      payscript=_scripts("COUPON_RATE", "RECOVERY_FRACTION", cln=True))
    body["credit"]["realized"] = {"product": product.model_dump(mode="json"), "context": context.model_dump(mode="json")}
    with pytest.raises(ValidationError, match="sans défaut déjà constaté"):
        read_scenario(body)


def test_http_replays_and_conserves_exact_source_but_refuses_booking(native_recipe_client):
    client = native_recipe_client
    body = _credit()
    body["credit"]["contract"].update(maturity_years=1, coupons=[{"start": 0, "end": 1, "payment": 1, "year_fraction": 1}])
    source = _scripts("COUPON_RATE * 2", "0.3 + RECOVERY_FRACTION * 0.1")
    body["credit"]["contract"]["payscript"] = source
    quote = _price(client, body)
    replayed = _json(client.post(f"{EXOTICS}/replay", json={"receipt": quote["receipt"]}))
    assert replayed["matched"] and replayed["result"] == quote["result"]
    assert quote["receipt"]["request"]["credit"]["contract"]["payscript"]["default"]["source"] == source["default"]["source"]
    retained = _json(client.post(f"{EXOTICS}/conserve", json={
        "receipt": quote["receipt"], "name": "Crédit scripté", "command_key": "credit-script-reference-witness",
    }), 201)
    product = retained["product"]
    assert product["terms"]["payoff_mode"] == "scripted"
    assert product["terms"]["contract"]["payscript"]["coupon"]["source"] == source["coupon"]["source"]
    assert not retained["booking_eligible"]
    assert any("défaut qualifiée" in reason for reason in retained["booking_diagnostics"])
    product_id, calculation_id = product["product_id"], retained["calculation_id"]
    reopened = _json(client.get(f"/api/products/{product_id}/exotics/calculations/{calculation_id}"))
    assert reopened["receipt"] == quote["receipt"] and reopened["result"] == quote["result"]
