"""API qualification for the isolated CDS and CLN pilots, from inputs to archives."""

from copy import deepcopy
from math import exp

import pytest

from backend.app.db.models import ProductCalculationRun, ProductRecord
from backend.app.services.product_repository import load_product
from backend.tests.test_products import _browser_json_roundtrip, product_client  # noqa: F401
from backend.tests.test_rates_credit_isda_market import request_data  # noqa: F401
from backend.tests.test_rates_credit_market_integration import _count
from backend.tests.test_rates_credit_native_writes import native_recipe_client  # noqa: F401


_PRICER = "/api/products/credit"


@pytest.fixture(autouse=True)
def signing_key(monkeypatch):
    monkeypatch.setattr("backend.app.api.credit_pricer.receipt_signing_secret", lambda: "isolated-credit-receipts-only")


def _json(response, status=200):
    assert response.status_code == status, response.text
    return response.json()


@pytest.fixture
def catalogue(product_client):
    products = _json(product_client.get(f"{_PRICER}/pilots"))["products"]
    return {product["instrument_type"]: {case["id"]: case for case in product["cases"]} for product in products}


def _draft_price(client, case):
    response = _json(client.post(f"{_PRICER}/price", json={
        "case": case["id"], "terms": case["terms"], "intent": case["intent"],
    }))
    assert response["result"]["scenario_id"] == case["id"]
    assert response["result"]["mode"] == case["mode"]
    assert response["result"]["valuation_date"] == case["valuation_date"]
    assert "warnings" in response
    assert response["context"]["product_id"] is None
    assert response["context"]["terms_version"] is None
    return response


def _metrics(result, key="metrics"):
    rows = result[key]
    indexed = {metric["key"]: metric for metric in rows}
    assert len(indexed) == len(rows)
    return indexed


def test_credit_catalogue_and_three_isda_prices_match_the_workbook(product_client, catalogue, request_data):
    client = product_client
    assert set(catalogue) == {"CDS", "CLN"}
    for instrument, cases in catalogue.items():
        assert {"SURVIVAL-PAR", "SURVIVAL-UPFRONT", "JULY-BEFORE", "JULY-PENDING", "JULY-DUE", "JULY-PAID", "JULY-ZERO"} <= set(cases)
        assert all(case["terms"]["instrument_type"] == instrument and case["label"] and case["cutoff"] for case in cases.values())
    assert {case_id for case_id in catalogue["CDS"] if case_id.startswith("ISDA")} == {"ISDA-50", "ISDA-100", "ISDA-150"}
    assert not any(case_id.startswith("ISDA") for case_id in catalogue["CLN"])

    tolerance = request_data["comparison_tolerances"]
    for scenario in request_data["scenarios"]:
        spread = scenario["market_inputs"]["quoted_spread_bp"]
        priced = _draft_price(client, catalogue["CDS"][f"ISDA-{spread}"])
        result = priced["result"]
        oracle = scenario["workbook_results"]
        assert (result["state"], result["market_quality"]) == ("alive", "published_historical_benchmark")
        assert (result["measure"]["kind"], result["measure"]["unit"]) == ("cds_clean_price", "per_100_notional")
        assert result["measure"]["value"] == pytest.approx(
            oracle["clean_price_per_100"], rel=0, abs=tolerance["clean_price_per_100_points"],
        )
        metrics = _metrics(result)
        assert metrics["clean_upfront"]["unit"] == "fraction"
        assert 100 * metrics["clean_upfront"]["value"] == pytest.approx(
            100 * oracle["clean_upfront_fraction"], rel=0, abs=tolerance["upfront_pct_of_notional_points"],
        )
        assert metrics["settlement_buyer_to_seller"]["unit"] == "EUR"
        assert metrics["settlement_buyer_to_seller"]["value"] == pytest.approx(
            oracle["cash_settlement_eur_buyer_to_seller"], rel=0, abs=tolerance["cash_eur"],
        )
        assert metrics["initial_accrued_days"]["value"] == 36
        assert metrics["initial_accrued"]["value"] == pytest.approx(
            oracle["accrued_premium_eur"], rel=0, abs=tolerance["cash_eur"],
        )
        assert metrics["protection"]["value"] > 0
        assert result["flows"]
    seller = deepcopy(catalogue["CDS"]["ISDA-150"])
    seller["intent"]["side"] = "SELL"
    sold = _metrics(_draft_price(client, seller)["result"])
    assert sold["settlement_buyer_to_seller"]["value"] == metrics["settlement_buyer_to_seller"]["value"]
    assert sold["position_settlement_cash"]["value"] == -metrics["position_settlement_cash"]["value"]
    assert sold["protection"]["value"] == -metrics["protection"]["value"]
    assert _count(client, ProductRecord) == _count(client, ProductCalculationRun) == 0


def test_credit_live_cases_reconcile_cds_and_cln_under_both_quote_formats(product_client, catalogue):
    expected = {
        "CDS": {"dirty_pv": 235_400.21, "protection": 688_145.26},
        "CLN": {"dirty_pv": 1_020_860.38, "coupon_pv": 180_525.78},
    }
    for instrument, expected_metrics in expected.items():
        results = {}
        for case_id in ("SURVIVAL-PAR", "SURVIVAL-UPFRONT"):
            priced = _draft_price(product_client, catalogue[instrument][case_id])
            result = priced["result"]
            assert result["state"] == "alive"
            assert result["market_quality"] == "synthetic"
            metrics = _metrics(result)
            for key, value in expected_metrics.items():
                assert metrics[key]["unit"] == "EUR"
                assert metrics[key]["value"] == pytest.approx(value, rel=0, abs=.01)
            calibration = result["calibration"]
            assert [item["maturity_years"] for item in calibration] == [1, 3, 5]
            assert [item["hazard_rate"] for item in calibration] == pytest.approx([.01, .02, .04], rel=0, abs=1e-10)
            assert [item["survival"] for item in calibration] == pytest.approx(
                [exp(-.01), exp(-.05), exp(-.13)], rel=0, abs=1e-10,
            )
            assert max(abs(item["reprice_error_eur"]) for item in calibration) <= .01
            assert all(item["source_unit"] == ("bp" if case_id == "SURVIVAL-PAR" else "fraction") for item in calibration)
            results[case_id] = result
        stored_spread = _metrics(results["SURVIVAL-PAR"], "sensitivities")
        stored_upfront = _metrics(results["SURVIVAL-UPFRONT"], "sensitivities")
        assert "cs01" in stored_spread and "upfront01" in stored_upfront
        assert stored_spread["cs01"]["value"] == pytest.approx(
            4430.8 if instrument == "CDS" else -465.22, rel=0, abs=.06,
        )
        assert stored_spread["jump_to_default"]["value"] == pytest.approx(
            5_764_599.8 if instrument == "CDS" else -621_517.38, rel=0, abs=.06,
        )
        if instrument == "CLN":
            assert results["SURVIVAL-PAR"]["measure"]["unit"] == "per_100_notional"
            assert _metrics(results["SURVIVAL-PAR"])["par_coupon"]["value"] == pytest.approx(.035377860308, rel=0, abs=1e-8)
            assert stored_spread["funding100"]["value"] == pytest.approx(-44_639.23, rel=0, abs=.01)
            case = catalogue["CLN"]["SURVIVAL-PAR"]
            funded = _json(product_client.post(f"{_PRICER}/price", json={
                "case": case["id"], "terms": case["terms"], "intent": case["intent"], "assumptions": {"funding_bps": 100},
            }))["result"]
            assert funded["calibration"] == results["SURVIVAL-PAR"]["calibration"]
            assert _metrics(funded)["dirty_pv"]["value"] == pytest.approx(976_221.15, rel=0, abs=.01)


@pytest.mark.parametrize(
    ("instrument", "due_cash", "due_pv", "accrued_days", "zero_recovery_cash"),
    [
        ("CDS", 6_493_333.33, 6_492_977.54, 24, 9_993_333.33),
        ("CLN", 350_000.00, 349_980.82, 0, 0),
    ],
)
def test_credit_july_cutoffs_switch_from_live_through_pending_to_single_payment(
    product_client, catalogue, instrument, due_cash, due_pv, accrued_days, zero_recovery_cash,
):
    states = {"BEFORE": "alive", "PENDING": "recovery_pending", "DUE": "settlement_pending", "PAID": "settled", "ZERO": "settled"}
    results = {}
    markets = {}
    for suffix, state in states.items():
        priced = _draft_price(product_client, catalogue[instrument][f"JULY-{suffix}"])
        result = priced["result"]
        assert result["state"] == state
        results[suffix] = result
        markets[suffix] = priced["context"]["market"]

    assert results["BEFORE"]["measure"]["value"] is not None
    pending = _metrics(results["PENDING"])
    assert results["PENDING"]["measure"]["value"] is None
    assert pending["net_due"]["value"] is None and pending["contingent_pv"]["value"] == 0
    for scenario in ("DUE", "PAID", "ZERO"):
        metrics = _metrics(results[scenario])
        assert metrics["accrued_days"]["value"] == accrued_days
        assert metrics["contingent_pv"]["value"] == 0
        assert results[scenario]["events"]
    due = _metrics(results["DUE"])
    assert due["net_due"]["value"] == pytest.approx(due_cash, rel=0, abs=.01)
    assert due["claim_pv"]["value"] == pytest.approx(due_pv, rel=0, abs=.01)
    assert due["cash_on_value_date"]["value"] == 0
    paid = _metrics(results["PAID"])
    assert paid["net_due"]["value"] == paid["claim_pv"]["value"] == 0
    assert paid["cash_on_value_date"]["value"] == pytest.approx(due_cash, rel=0, abs=.01)
    zero = _metrics(results["ZERO"])
    assert zero["cash_on_value_date"]["value"] == pytest.approx(zero_recovery_cash, rel=0, abs=.01)

    due_flow, paid_flow = (markets[scenario]["settlement_flow"] for scenario in ("DUE", "PAID"))
    assert due_flow["flow_id"] == paid_flow["flow_id"]
    assert due_flow["scheduled_date"] == paid_flow["paid_date"] == "2021-07-20"
    assert due_flow["amount_eur"] == paid_flow["amount_eur"] == due_cash
    assert (due_flow["state"], paid_flow["state"], paid_flow["pv_eur"]) == ("due", "paid", 0)


def test_credit_price_uses_the_t4_context_and_archives_it_across_a_product_revision(
    native_recipe_client, request_data,
):
    from backend.app.core.product.isda_market import IsdaMarket
    from backend.tests.test_rates_credit_market_integration import _body, _create_context, _read_context
    from backend.tests.test_rates_credit_mixed_reader import _assert_error
    from backend.tests.test_rates_credit_native_writes import _revision_body, _revision_url

    client = native_recipe_client
    cds = _json(client.get(f"{_PRICER}/pilots"))["products"][0]
    selected = next(case for case in cds["cases"] if case["id"] == "ISDA-150")
    dossier = _json(client.post("/api/products/native", json={
        "command_key": "credit-context-create", "name": cds["name"],
        "terms": selected["terms"], "intent": selected["intent"],
    }), 201)
    product_id = dossier["product_id"]
    product = load_product(client.session, product_id, allow_native=True)
    request_data["scenario_id"] = request_data["scenarios"][2]["id"]
    market = IsdaMarket.model_validate(request_data).model_dump(mode="json")
    retained_market = _create_context(client, product, _body(
        product, "credit-context-prepare", selected["cutoff"], selected["valuation_date"], market,
    ))

    request = {"product_id": product_id, "expected_revision": dossier["revision"],
               "expected_terms_version": dossier["terms_version"], "context_id": retained_market["context_id"]}
    priced = _json(client.post(f"{_PRICER}/price", json=request))
    assert priced["result"]["scenario_id"] == "ISDA-150"
    assert priced["context"]["product_id"] == product_id
    assert priced["context"]["terms_version"] == dossier["terms_version"]
    assert priced["context"]["schedule_fingerprint"] == retained_market["context"]["schedule_fingerprint"]
    assert _metrics(priced["result"])["settlement_buyer_to_seller"]["value"] == pytest.approx(238_235.61, rel=0, abs=.01)

    archive_url = f"/api/products/{product_id}/credit/calculations"
    body = _browser_json_roundtrip({
        "command_key": "credit-context-archive", "expected_revision": dossier["revision"], "receipt": priced["receipt"],
    })
    tampered = deepcopy(body)
    tampered["receipt"]["result"]["measure"]["value"] += 1
    assert client.post(archive_url, json=tampered).status_code == 422
    assert _count(client, ProductCalculationRun) == 0
    saved = _json(client.post(archive_url, json=body), 201)
    assert _json(client.post(archive_url, json=body), 201) == saved
    _assert_error(client.post(f"{_PRICER}/price", json=request), "PRODUCT_REVISION_STALE")

    new_terms = deepcopy(dossier["terms"])
    new_terms["maturity_date"] = "2026-09-20"
    changed = _json(client.post(_revision_url(product_id), json=_revision_body(
        saved["product"], key="credit-context-amend", terms=new_terms,
    )))
    assert changed["terms_version"] == dossier["terms_version"] + 1
    new_request = {**request, "expected_revision": changed["revision"], "expected_terms_version": changed["terms_version"]}
    _assert_error(client.post(f"{_PRICER}/price", json=new_request), "CREDIT_CONTEXT_STALE")

    client.restore_archive()
    archive_detail = f"{archive_url}/{saved['calculation_id']}"
    reopened = _json(client.get(archive_detail))
    assert {key: reopened[key] for key in priced} == priced
    assert _read_context(client, product, retained_market["context_id"]) == retained_market
    assert _count(client, ProductCalculationRun) == 1
    client.current["user"] = client.users["bob"]
    assert client.get(archive_detail).status_code == 404
    assert client.post(f"{_PRICER}/price", json=new_request).status_code == 404


def test_credit_archive_preserves_a_settled_cln_at_zero_and_reads_when_writes_are_closed(
    native_recipe_client, monkeypatch,
):
    client = native_recipe_client
    catalogue = _json(client.get(f"{_PRICER}/pilots"))["products"]
    cln = next(product for product in catalogue if product["instrument_type"] == "CLN")
    selected = next(case for case in cln["cases"] if case["id"] == "JULY-ZERO")
    dossier = _json(client.post("/api/products/native", json={
        "command_key": "credit-cln-zero-create", "name": cln["name"],
        "terms": selected["terms"], "intent": selected["intent"],
    }), 201)
    product_id = dossier["product_id"]
    priced = _json(client.post(f"{_PRICER}/price", json={
        "case": selected["id"], "product_id": product_id, "expected_revision": dossier["revision"],
        "expected_terms_version": dossier["terms_version"],
    }))
    assert priced["result"]["state"] == "settled"
    assert priced["result"]["measure"] == {"kind": "credit_pv", "unit": "EUR", "value": 0}
    archive_url = f"/api/products/{product_id}/credit/calculations"
    body = {"command_key": "credit-cln-zero-archive", "expected_revision": dossier["revision"],
            "receipt": priced["receipt"]}
    with monkeypatch.context() as closed:
        closed.setenv("STRUCTURA_NATIVE_WRITES", "0")
        assert client.post(archive_url, json=body).status_code == 403
    assert _count(client, ProductCalculationRun) == 0
    retained = _json(client.post(archive_url, json=body), 201)
    monkeypatch.setenv("STRUCTURA_NATIVE_WRITES", "0")
    assert client.post(archive_url, json=body).status_code == 403
    reopened = _json(client.get(f"{archive_url}/{retained['calculation_id']}"))
    assert reopened["result"] == priced["result"]
    assert _count(client, ProductCalculationRun) == 1
