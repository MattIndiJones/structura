"""Signed civil dates, credit-leg cash flows and native Deal perimeter."""

from copy import deepcopy
from datetime import date, timedelta
from math import fsum

import pytest
from sqlmodel import select

from backend.app.core.valuation_context import canonical_json
from backend.app.db.ccr_models import CCRMasterAgreement, CCRNettingSet
from backend.app.db.models import Counterparty, Deal, Entity, User
from backend.tests.test_exotic_pricer_api import _credit
from backend.tests.test_exotic_product_booking import _conserve, _fact_test_users, _response
from backend.tests.test_products import product_client  # noqa: F401
from backend.tests.test_rates_credit_native_writes import native_recipe_client  # noqa: F401


_EXOTICS = "/api/products/exotics"


def _dated_credit(kind, *, rank=None, side="BUY"):
    body = _credit()
    origin = date.fromisoformat(body["valuation_date"])
    dates = (origin, origin + timedelta(days=93), date(2028, 2, 29))
    principal = dates[-1] + timedelta(days=5) if kind == "cln" else None

    def axis(day):
        return (day - origin).days / 365

    periods = [{"accrual_start_date": start.isoformat(), "accrual_end_date": end.isoformat(),
                "observation_date": end.isoformat(), "payment_date": (end + timedelta(days=2)).isoformat()}
               for start, end in zip(dates, dates[1:])]
    coupons = [{"start": axis(start), "end": axis(end), "payment": axis(end + timedelta(days=2)),
                "year_fraction": (end - start).days / 365}
               for start, end in zip(dates, dates[1:])]
    body["credit"]["contract"].update(kind=kind, side=side, trigger_rank=rank, maturity_years=axis(dates[-1]),
                                      coupons=coupons, default_settlement_delay_years=3 / 365,
                                      principal_payment_years=axis(principal) if principal else None)
    if kind != "basket_cds":
        body["credit"]["market"]["marginals"] = body["credit"]["market"]["marginals"][:1]
    if kind == "cds":
        body["credit"]["settings"]["estimator"] = "conditional_single_name"
    if rank == 2:
        market = body["credit"]["market"]
        market.update(dependence_model="gaussian_one_factor", dependence_source_id="dated-basket-factor",
                      dependence_source_version=1)
        for marginal in market["marginals"]:
            marginal["loading"] = .35
    body["credit_calendar"] = {"convention": "civil_unadjusted_act365f",
                               "protection_start_date": origin.isoformat(), "protection_end_date": dates[-1].isoformat(),
                               "principal_payment_date": principal.isoformat() if principal else None,
                               "default_settlement_lag_days": 3, "coupons": periods}
    return body


@pytest.mark.parametrize(("kind", "rank", "side"), [
    ("cds", None, "BUY"), ("cln", None, "BUY"),
    ("basket_cds", 1, "SELL"), ("basket_cds", 2, "BUY"),
])
def test_dated_cashflows_reconcile_to_signed_monte_carlo_and_replay(product_client, kind, rank, side):
    body = _dated_credit(kind, rank=rank, side=side)
    quote = _response(product_client.post(_EXOTICS + "/price", json=body))
    result = quote["result"]
    schedule = result["contract_schedule"]
    assert quote["receipt"]["request"]["credit_calendar"] == body["credit_calendar"]
    assert schedule["protection_end_date"] == "2028-02-29"
    assert schedule["flows"][1]["payment_date"] == "2028-03-02"
    assert schedule["flows"][0]["year_fraction"] == 93 / 365
    assert schedule["flows"][0]["amount_if_payable_eur"] == pytest.approx(
        (1 if kind == "cln" or side == "SELL" else -1) * 1_000_000 * .01 * 93 / 365,
    )
    assert "payment_date" not in schedule["contingent_flows"][0]
    assert schedule["contingent_flows"][0]["latest_payment_date"] == "2028-03-03"
    assert schedule["contingent_flows"][0]["trigger_rank"] == (rank or 1)
    assert fsum(row["pv_eur"] for row in schedule["flows"] + schedule["contingent_flows"]) == pytest.approx(
        result["estimate"]["dirty_pv_eur"]["mean"], abs=1e-8,
    )
    if kind == "cln":
        assert schedule["flows"][-1]["kind"] == "principal"
        assert schedule["flows"][-1]["payment_date"] == "2028-03-05"
    replay = _response(product_client.post(_EXOTICS + "/replay", json={"receipt": quote["receipt"]}))
    assert replay["result"] == result


def test_calendar_and_prorata_are_bound_and_legacy_omits_new_fields(product_client):
    for field, value in (("payment_date", "2028-03-01"), ("observation_date", "2028-02-28")):
        body = _dated_credit("cds")
        body["credit_calendar"]["coupons"][-1][field] = value
        assert product_client.post(_EXOTICS + "/price", json=body).status_code == 422
    non_act365f = _dated_credit("cds")
    non_act365f["credit"]["contract"]["coupons"][0]["year_fraction"] = .25
    assert product_client.post(_EXOTICS + "/price", json=non_act365f).status_code == 422
    legacy = _response(product_client.post(_EXOTICS + "/price", json=_credit()))
    assert "contract_schedule" not in legacy["result"]
    assert "credit_calendar" not in legacy["receipt"]["request"]


def test_dated_payscript_flows_use_effective_amounts_but_booking_stays_closed(native_recipe_client):
    client = native_recipe_client
    body = _dated_credit("cln")
    body["credit"]["contract"]["payscript"] = {
        "profile": "credit-exotic-payoff-v1",
        "coupon": {"source": "AT CLN_COUPON:\n  PAY COUPON_RATE * 2"},
    }
    quote = _response(client.post(_EXOTICS + "/price", json=body))
    dates = quote["result"]["contract_schedule"]
    assert dates["flows"][0]["amount_if_payable_eur"] == pytest.approx(1_000_000 * .02 * 93 / 365)
    assert dates["flows"][0]["payment_date"] == body["credit_calendar"]["coupons"][0]["payment_date"]
    kept = _conserve(client, quote)
    assert kept["transaction_format"] == "NOTE" and not kept["booking_eligible"]
    assert any("défaut qualifiée" in item for item in kept["booking_diagnostics"])


def _legal_otc_scope(client, *, scope):
    session = client.session
    session.add(Entity(id=1, name="Entité de recette"))
    session.flush()
    user = session.get(User, 1)
    user.entity_id = 1
    session.add(Counterparty(id=1, name="Contrepartie de recette", active=True))
    session.flush()
    session.add(CCRMasterAgreement(id=1, entity_id=1, counterparty_id=1, updated_by=user.id, payload_json=canonical_json(
        {"status": "ACTIVE", "effective_date": "2020-01-01"},
    )))
    session.add(CCRNettingSet(id=1, entity_id=1, counterparty_id=1, updated_by=user.id, payload_json=canonical_json(
        {"active": True, "currency": "EUR", "product_scope": [scope], "master_agreement_id": 1},
    )))
    session.commit()
    client.current["user"] = user


@pytest.mark.parametrize(("kind", "rank"), [("cds", None), ("basket_cds", 2)])
def test_dated_protection_books_as_otc_with_legal_scope_and_frozen_dates(native_recipe_client, kind, rank):
    client = native_recipe_client
    _legal_otc_scope(client, scope="EXOTIC_CREDIT")
    body = _dated_credit(kind, rank=rank)
    quote = _response(client.post(_EXOTICS + "/price", json=body))
    kept = _conserve(client, quote)
    product = kept["product"]
    assert kept["booking_eligible"] and kept["transaction_format"] == "OTC"
    path = f"/api/products/{product['product_id']}/exotics"
    assert _response(client.get(f"{path}/calculations/{kept['calculation_id']}"))["receipt"] == quote["receipt"]
    book = {"command_key": "book-exotic-credit-date-otc", "expected_revision": product["revision"],
            "expected_terms_version": product["terms_version"], "calculation_id": kept["calculation_id"], "counterparty_id": 1,
            "trade_date": body["valuation_date"], "value_date": body["valuation_date"],
            "execution_price_eur": quote["result"]["estimate"]["dirty_pv_eur"]["mean"]}
    assert client.post(path + "/book", json=book).status_code == 422
    assert not client.session.exec(select(Deal)).all()
    booked = _response(client.post(path + "/book", json={
        **book, "ccr_netting_set_id": 1, "documentation_reference": "Convention OTC de recette",
    }), 201)
    deal = _response(client.get(f"/api/deals/{booked['deal_id']}"))
    assert deal["transaction_format"] == "OTC"
    assert deal["maturity_date"] == "2028-02-29" and deal["payment_date"] == "2028-03-02"
    assert deal["frozen_schedule"]["schedule"] == product["native_schedule"]
    ledger = _response(client.get(f"/api/deals/{booked['deal_id']}/exotics/facts"))
    assert not ledger["can_propose"] and not ledger["can_decide"]


def test_dated_cln_books_as_note_and_fractional_default_lag_stays_closed(native_recipe_client, monkeypatch):
    client = native_recipe_client
    _fact_test_users(client, monkeypatch)
    dated = _dated_credit("cln")
    kept = _conserve(client, _response(client.post(_EXOTICS + "/price", json=dated)))
    assert kept["booking_eligible"] and kept["transaction_format"] == "NOTE"
    product = kept["product"]
    book = {"command_key": "book-exotic-credit-date-note", "expected_revision": product["revision"],
            "expected_terms_version": product["terms_version"], "calculation_id": kept["calculation_id"], "counterparty_id": 1,
            "trade_date": dated["valuation_date"], "value_date": dated["valuation_date"], "execution_price_eur": 995_000}
    booked = _response(client.post(f"/api/products/{product['product_id']}/exotics/book", json=book), 201)
    deal = _response(client.get(f"/api/deals/{booked['deal_id']}"))
    assert deal["transaction_format"] == "NOTE"
    assert deal["maturity_date"] == "2028-02-29" and deal["payment_date"] == "2028-03-05"
    ledger = _response(client.get(f"/api/deals/{booked['deal_id']}/exotics/facts"))
    assert ledger["can_propose"] and ledger["credit_targets"]

    legacy = deepcopy(dated)
    legacy.pop("credit_calendar")
    legacy["credit"]["contract"]["default_settlement_delay_years"] = 3.5 / 365
    blocked = _conserve(client, _response(client.post(_EXOTICS + "/price", json=legacy)), key="fractional-credit-default-lag")
    assert not blocked["booking_eligible"]
    assert any("jours civils" in reason for reason in blocked["booking_diagnostics"])
