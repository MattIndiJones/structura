"""Exotic research pricing and native valuation attribution through Structura HTTP."""
from copy import deepcopy
from datetime import date
from math import exp

import pytest

from backend.app.core.product.credit_default import CreditDefaultDiscount, prepare_credit_default
from backend.app.core.product.credit_pilot import benchmark_terms, case_cutoff, july_facts, july_prior_payment
from backend.app.core.product.credit_pricing import quarterly_coupons
from backend.app.core.product.models import Product, TradeIntent
from backend.app.core.product.native_schedule import resolve_native_schedule
from backend.app.core.product.rates_pilot import pilot_terms
from backend.tests.test_products import product_client  # noqa: F401
from backend.tests.test_rates_credit_native_writes import native_recipe_client  # noqa: F401


EXOTICS = "/api/products/exotics"


def _json(response, expected=200):
    assert response.status_code == expected, response.text
    return response.json()


def _scenario(family, position):
    return {
        "family": family, "position_id": position,
        "valuation_date": "2026-11-23", "cutoff": "2026-11-23T16:00:00+01:00",
        "market_source": {"source_id": "lot5.synth", "version": 1,
                          "available_at": "2026-11-23T08:00:00+01:00",
                          "validated_at": "2026-11-23T09:00:00+01:00"},
    }


def _curve(rate):
    return {"pillars": [{"time": 0, "factor": 1}, {"time": 6, "factor": exp(-6 * rate)}]}


def _rates():
    return {
        **_scenario("rates", "synthetic.cms-5y"),
        "terms": {"nominal_eur": 1_000_000, "cashflows": [{
            "kind": "rate", "flow_id": "cms", "fixing": 1, "payment": 1.25, "year_fraction": .25,
            "index": {
                "kind": "swap",
                "fixed_periods": [{"payment": year + 1, "year_fraction": 1} for year in range(1, 6)],
                "floating_periods": [{"start": year, "end": year + 1, "year_fraction": 1} for year in range(1, 6)],
            },
        }]},
        "market": {"discount": _curve(.02), "projection": _curve(.02), "mean_reversion": .1, "volatility": .01},
        "settings": {"paths": 4096, "seed": 581},
    }


def _credit():
    return {
        **_scenario("credit", "synthetic.basket"),
        "credit": {
            "contract": {"kind": "basket_cds", "nominal_eur": 1_000_000, "maturity_years": 5,
                         "coupons": [coupon.model_dump(mode="json") for coupon in quarterly_coupons(5)],
                         "coupon_bps": 100, "side": "BUY", "trigger_rank": 1},
            "market": {"source_id": "credit-lot5", "source_version": 1, "discount_rate": .02, "marginals": [
                {"reference_entity_id": name, "curve": {"maturities": [5], "hazards": [.02]}, "recovery_fraction": .4,
                 "source_id": "credit-flat", "source_version": 1}
                for name in ("ALPHA", "BETA", "GAMMA")
            ]},
            "settings": {"paths": 4096, "seed": 117},
        },
    }


def _price(client, body):
    return _json(client.post(f"{EXOTICS}/price", json=body))


def _explain(client, first, second, path="explain", **extra):
    return _json(client.post(f"{EXOTICS}/{path}", json={
        "start_receipt": first["receipt"], "end_receipt": second["receipt"], **extra,
    }))


@pytest.mark.parametrize("profile,event,payoff,observables,unit", [
    ("rates-exotic-coupon-v1", "CMS_COUPON", "(CMS_RATE + MARGIN) * YEAR_FRACTION",
     ["CMS_RATE", "YEAR_FRACTION"], "fraction_of_nominal"),
    ("credit-exotic-payoff-v1", "CLN_COUPON", "COUPON_RATE + MARGIN",
     ["COUPON_RATE"], "annual_fraction_of_nominal"),
    ("credit-exotic-payoff-v1", "CDS_PROTECTION", "1 - RECOVERY_FRACTION - MARGIN",
     ["RECOVERY_FRACTION", "DEFAULT_RANK"], "fraction_of_nominal"),
])
def test_editor_validates_the_profile_event_and_effective_parameters(product_client, profile, event, payoff, observables, unit):
    body = {"profile": profile, "event": event, "source": f"PARAM MARGIN = 1%\nAT {event}:\n  PAY {payoff}",
            "parameters": {"MARGIN": .02}}
    path = f"{EXOTICS}/payscript/validate"
    metadata = _json(product_client.post(path, json=body))["metadata"]
    assert metadata["profile"] == profile
    assert metadata["event"] == event
    assert metadata["observables"] == observables
    assert metadata["output_unit"] == unit
    assert metadata["parameters"] == [{"name": "MARGIN", "value": .02, "unit": "decimal_fraction"}]
    invalid = {**body, "source": f"AT {event}:\n  PAY UNSUPPORTED_OBSERVABLE"}
    assert "PAYSCRIPT" in _json(product_client.post(path, json=invalid), 422)["detail"]["code"]


def test_quotes_are_signed_replayable_and_cutoff_bound(product_client):
    client = product_client
    catalogue = _json(client.get(f"{EXOTICS}/capabilities"))
    assert catalogue["market_quality"] == "synthetic"
    assert catalogue["rates"]["model"] == "hull_white_1f"
    body = {**_rates(), "expected_engine_fingerprint": catalogue["engine_fingerprint"]}
    run = _price(client, body)
    assert run["result"]["pv_eur"] == pytest.approx(4965.56, abs=15)
    assert run["result"]["flows"][0]["flow_id"] == "cms"
    assert run["receipt"]["request"]["market_source"]["source_id"] == "lot5.synth"
    replay = _json(client.post(f"{EXOTICS}/replay", json={"receipt": run["receipt"]}))
    assert replay["matched"] and replay["result"] == run["result"]
    assert replay["result_fingerprint"] == run["receipt"]["result_fingerprint"]

    altered = deepcopy(run["receipt"])
    altered["request"]["market"]["volatility"] = .5
    _json(client.post(f"{EXOTICS}/replay", json={"receipt": altered}), 422)
    client.current["user"] = client.users["bob"]
    assert _json(client.post(f"{EXOTICS}/replay", json={"receipt": run["receipt"]}), 404)["detail"]["code"] == "EXOTIC_RECEIPT_NOT_FOUND"
    stale = {**body, "expected_engine_fingerprint": "0" * 64}
    _json(client.post(f"{EXOTICS}/price", json=stale), 409)
    delayed = {**body, "market_source": {**body["market_source"], "validated_at": "2026-11-23T16:01:00+01:00"}}
    _json(client.post(f"{EXOTICS}/price", json=delayed), 422)
    oversized = {**body, "settings": {"paths": 250_002, "seed": 0}}
    assert _json(client.post(f"{EXOTICS}/price", json=oversized), 422)["detail"]["code"] == "EXOTIC_WORK_LIMIT"


def test_rates_explain_uses_paired_units_and_flags_a_changed_grid_origin(product_client):
    client = product_client
    body = _rates()
    first = _price(client, body)
    changed = {**body, "market": {**body["market"], "projection": _curve(.025)}}
    last = _price(client, changed)
    explained = _explain(client, first, last)
    assert explained["status"] == "attributed", explained
    assert [effect["factor"] for effect in explained["effects"]] == ["projection_basis"]
    assert explained["contractual_pnl_eur"] == pytest.approx(last["result"]["pv_eur"] - first["result"]["pv_eur"])
    assert explained["cash_contractual_eur"] == 0
    assert explained["residual_eur"] == pytest.approx(0)
    assert explained["interval"]["independent_units"] == body["settings"]["paths"] // 2
    assert explained["interval"]["resolved"]

    changed_clock = {**changed, "valuation_date": "2026-11-24", "cutoff": "2026-11-24T16:00:00+01:00"}
    observed = _explain(client, first, _price(client, changed_clock))
    assert observed["status"] == "observed" and observed["reason_code"] == "EXPLAIN_ROLL_UNAVAILABLE"


def test_signed_swaption_calibration_binds_the_model_used_for_pricing(product_client):
    client = product_client
    pricing = _rates()
    market = pricing["market"]
    swaption = {"expiry": 1.0, "swap": pricing["terms"]["cashflows"][0]["index"], "side": "payer",
                "strike": exp(.02) - 1, "nominal_eur": 1_000_000, "quote": {"kind": "normal", "volatility": .008}}
    calibrated = _json(client.post(f"{EXOTICS}/rates/calibration", json={
        **{key: pricing[key] for key in ("valuation_date", "cutoff", "market_source")},
        "calibration": {"discount": market["discount"], "projection": market["projection"],
                        "mean_reversion": market["mean_reversion"], "dataset_id": "calibration.http",
                        "quotes": [{**swaption, "quote_id": "fit", "role": "calibration"},
                                   {**swaption, "quote_id": "holdout", "role": "validation", "strike": .025}]},
    }))
    report = calibrated["result"]
    assert [row["role"] for row in report["residuals"]] == ["calibration", "validation"]
    assert report["calibration_rmse_eur_per_100"] < 1e-6
    pricing.update(market=report["market"], calibration_receipt=calibrated["receipt"])
    priced = _price(client, pricing)
    assert priced["receipt"]["request"]["calibration_receipt"]["result"]["dataset_id"] == "calibration.http"
    assert _json(client.post(f"{EXOTICS}/replay", json={"receipt": priced["receipt"]}))["matched"]
    pricing["market"]["volatility"] *= 1.1
    error = _json(client.post(f"{EXOTICS}/price", json=pricing), 409)
    assert error["detail"]["code"] == "EXOTIC_CALIBRATION_MISMATCH"


def test_scripted_cms_uses_same_trajectories_and_replays_exactly(product_client):
    client = product_client
    body = _rates()
    template = _price(client, body)
    body["terms"]["cashflows"][0]["payscript"] = {
        "profile": "rates-exotic-coupon-v1",
        "source": 'AT CMS_COUPON:\n  PAY CMS_RATE * YEAR_FRACTION "Coupon CMS"',
    }
    scripted = _price(client, body)
    assert scripted["result"]["pv_eur"] == pytest.approx(template["result"]["pv_eur"], abs=1e-9)
    assert scripted["result"]["draw_fingerprint"] == template["result"]["draw_fingerprint"]
    proof, = scripted["result"]["payscript_metadata"]
    assert proof["output_unit"] == "fraction_of_nominal" and proof["observables"] == ["CMS_RATE", "YEAR_FRACTION"]
    assert _json(client.post(f"{EXOTICS}/replay", json={"receipt": scripted["receipt"]}))["result"] == scripted["result"]


def test_credit_reference_replay_and_market_attribution(product_client):
    client = product_client
    body = _credit()
    first = _price(client, body)
    assert first["result"]["reference"]["dirty_pv_eur"] == pytest.approx(107248.67, abs=.01)
    assert first["result"]["provenance"]["independent_samples"] == 4096
    replay = _json(client.post(f"{EXOTICS}/replay", json={"receipt": first["receipt"]}))
    assert replay["result"] == first["result"]

    bumped = deepcopy(body)
    bumped["credit"]["market"]["discount_rate"] = .025
    last = _price(client, bumped)
    explained = _explain(client, first, last)
    assert explained["status"] == "attributed", explained
    assert [effect["factor"] for effect in explained["effects"]] == ["ois"]
    assert not explained["effects"][0]["credit_rebootstrap"]
    assert explained["interval"]["independent_units"] == 4096
    assert explained["residual_eur"] == pytest.approx(0.0)


@pytest.mark.parametrize(("body", "measure"), [(_rates, "hw_factor_bp"), (_credit, "credit_default_count")])
def test_path_preview_is_bound_to_the_receipt_and_repeatable(product_client, body, measure):
    client = product_client
    priced = _price(client, body())
    request = {"receipt": priced["receipt"]}
    preview = _json(client.post(f"{EXOTICS}/paths", json=request))
    assert _json(client.post(f"{EXOTICS}/paths", json=request)) == preview
    assert preview["result_fingerprint"] == priced["receipt"]["result_fingerprint"]
    assert preview["path_count"] == len(preview["paths"]) == 48
    assert preview["measure"] == measure
    for path in preview["paths"]:
        assert path["points"][0] == {"time": 0.0, "value": 0.0}
        assert path["points"][-1]["time"] == preview["horizon_years"]
        if measure == "credit_default_count":
            assert path["triggered"] == (path["points"][-1]["value"] >= 1)
    client.current["user"] = client.users["bob"]
    _json(client.post(f"{EXOTICS}/paths", json=request), 404)


@pytest.mark.parametrize("scenario", [_rates, _credit])
def test_indicative_reports_use_the_pricing_receipt(product_client, scenario):
    client = product_client
    priced = _price(client, scenario())
    receipt = priced["receipt"]
    response = _json(client.post(f"{EXOTICS}/reports", json={
        "receipt": receipt, "report": "kid", "upfront_eur": 50_000, "entry_cost_eur": 25,
    }))
    report = response["report"]
    assert report["status"] == "INDICATIVE_NON_PRIIPS"
    assert response["pricing_fingerprint"] == receipt["result_fingerprint"]
    assert response["receipt"]["profile"] == "eur-exotic-indicative-report-v1"
    assert report["independent_paths"] == 4096
    assert [row["percentile"] for row in report["percentiles"]] == [1, 10, 50, 90]
    for row in report["percentiles"]:
        assert row["net_present_difference_eur"] == pytest.approx(row["pv_eur"] - 50_025)

    decision = {"client_type": "professional", "channel": "advice", "experience": "advanced",
                "max_loss_fraction": 1, "tolerance": "high", "objective": "hedging",
                "horizon_years": 0.1, "negative_market": "Investisseur sans capacité de perte"}
    emt = _json(client.post(f"{EXOTICS}/reports", json={"receipt": receipt, "report": "emt", "decision": decision}))
    assert emt["report"]["status"] == "INDICATIVE_NON_FINDATEX"
    assert emt["report"]["decision"] == decision
    assert len(emt["report"]["matters_to_review"]) == 3
    _json(client.post(f"{EXOTICS}/reports", json={
        "receipt": {**receipt, "user_id": 999_999}, "report": "emt", "decision": decision,
    }), 404)


def test_mark_to_future_requires_the_original_signed_run(product_client):
    client = product_client
    receipt = _price(client, _rates())["receipt"]
    request = {"receipt": receipt, "horizons_years": [0.05, 0.1], "paths": 64}
    result = _json(client.post(f"{EXOTICS}/mtf", json=request))
    assert result["position_id"] == receipt["request"]["position_id"]
    assert [row["horizon_years"] for row in result["horizons"]] == [0.05, 0.1]
    assert _json(client.post(f"{EXOTICS}/mtf", json=request)) == result
    _json(client.post(f"{EXOTICS}/mtf", json={**request, "receipt": {**receipt, "user_id": 999_999}}), 404)


def test_indicative_draft_attaches_to_exact_conserved_product(native_recipe_client, monkeypatch):
    from backend.app.api import documents
    from backend.app.runtime import data_path

    client = native_recipe_client
    monkeypatch.setattr(documents, "_DOCS_DIR", data_path("documents"))
    quote = _price(client, _rates())
    archived = _json(client.post(f"{EXOTICS}/conserve", json={
        "name": "Témoin brouillon KID", "receipt": quote["receipt"], "command_key": "exotic-draft-product",
    }), 201)
    report = _json(client.post(f"{EXOTICS}/reports", json={"receipt": quote["receipt"], "report": "kid"}))
    body = {"receipt": report["receipt"], "product_id": archived["product"]["product_id"],
            "calculation_id": archived["calculation_id"], "expected_revision": archived["product"]["revision"],
            "command_key": "exotic-draft-report"}
    retained = _json(client.post(f"{EXOTICS}/reports/retain", json=body), 201)
    assert retained == _json(client.post(f"{EXOTICS}/reports/retain", json=body), 201)
    snapshot, = retained["product"]["documents"]
    assert snapshot["record_id"] == retained["document_id"] and snapshot["doc_type"] == "exotic_kid_draft"
    downloaded = _json(client.get(f"/api/documents/{retained['document_id']}/download"))
    assert downloaded["receipt"] == report["receipt"]
    assert downloaded["report"]["pricing_fingerprint"] == quote["receipt"]["result_fingerprint"]
    different = _price(client, {**_rates(), "position_id": "different"})
    another = _json(client.post(f"{EXOTICS}/reports", json={"receipt": different["receipt"], "report": "kid"}))
    rejected = _json(client.post(f"{EXOTICS}/reports/retain", json={**body, "receipt": another["receipt"]}), 422)
    assert rejected["detail"]["code"] == "EXOTIC_REPORT_MISMATCH"


def test_realized_single_name_uses_native_credit_facts_without_resimulation(product_client):
    client = product_client
    terms = benchmark_terms("CLN", "JULY-DUE")
    product = Product(
        name="Excluded commercial label", terms=terms, native_schedule=resolve_native_schedule(terms).schedule,
        intent=TradeIntent(nominal=1_000_000),
    )
    runs = []
    for case in ("JULY-DUE", "JULY-PAID"):
        cutoff = case_cutoff(case)
        default_id, facts = july_facts(case)
        context = prepare_credit_default(
            product, valuation_date=cutoff.date(), cutoff=cutoff, default_id=default_id, facts=facts,
            reference_entity_id=terms.reference_entity_id, settlement_date=date(2021, 7, 20),
            prior_payments=(july_prior_payment(product),), discount=CreditDefaultDiscount(ois_rate=.02, cln_funding_bps=0),
        )
        day = cutoff.date().isoformat()
        clock = f"{day}T08:00:00+02:00"
        body = _credit()
        body.update(position_id="synthetic.cln.july", valuation_date=day, cutoff=cutoff.isoformat(),
                    market_source={"source_id": "lot5.credit.july", "version": 1, "available_at": clock, "validated_at": clock})
        body["credit"]["contract"].update(kind="cln", trigger_rank=None, coupon_bps=400, coupons=[])
        single = body["credit"]["market"]["marginals"][:1]
        single[0]["reference_entity_id"] = terms.reference_entity_id
        body["credit"]["market"]["marginals"] = single
        body["credit"]["realized"] = {"product": product.model_dump(mode="json"), "context": context.model_dump(mode="json")}
        priced = _price(client, body)
        assert priced["result"]["estimate"] is None
        assert priced["result"]["provenance"]["independent_samples"] == 0
        assert priced["receipt"]["request"]["credit"]["realized"]["product"]["name"] == ""
        runs.append(priced)

    explain = _explain(client, *runs)
    assert explain["status"] == "attributed", explain
    assert explain["cash_contractual_eur"] == 350_000
    assert explain["contractual_pnl_eur"] == pytest.approx(19.18, abs=.01)
    assert explain["interval"] is None


@pytest.mark.parametrize(("family", "instrument", "cases", "expected"), [
    ("rates", "FRN", ("B", "C"), (-6763.54, 10363.89, 3600.35)),
    ("rates", "IRS", ("B", "C"), (7010.53, -7836.11, -825.58)),
    ("credit", "CLN", ("JULY-DUE", "JULY-PAID"), (-349980.82, 350000, 19.18)),
])
def test_native_explain_reuses_frozen_pricer_receipts(product_client, family, instrument, cases, expected):
    client = product_client
    terms = (benchmark_terms("CLN", cases[0]) if family == "credit"
             else next(item for item in pilot_terms() if item.instrument_type == instrument))
    first, last = (_json(client.post(f"/api/products/{family}/price", json={
        "case": case, "terms": terms.model_dump(mode="json"), "intent": {"nominal": 1_000_000, "side": "BUY"},
    })) for case in cases)
    explanation = _explain(client, first, last, path="explain-native", mode="receipts", family=family)
    assert explanation["status"] == "attributed", explanation
    assert [explanation[field] for field in ("observed_dirty_change_eur", "cash_contractual_eur", "contractual_pnl_eur")
            ] == pytest.approx(expected, abs=.01)
    assert explanation["residual_eur"] == pytest.approx(0, abs=.01)


def test_native_explain_from_product_archive_survives_key_rotation(native_recipe_client, monkeypatch):
    client = native_recipe_client
    terms = pilot_terms()[0].model_dump(mode="json")
    dossier = _json(client.post("/api/products/native", json={
        "command_key": "explain-archive-frn", "name": "FRN Explain", "terms": terms,
        "intent": {"side": "BUY", "nominal": 1_000_000},
    }), 201)
    product_id = dossier["product_id"]
    calculation_ids = []
    for case in ("B", "C"):
        run = _json(client.post("/api/products/rates/price", json={
            "case": case, "product_id": product_id, "expected_revision": dossier["revision"],
            "expected_terms_version": dossier["terms_version"],
        }))
        retained = _json(client.post(f"/api/products/{product_id}/rates/calculations", json={
            "command_key": f"explain-retain-{case}", "expected_revision": dossier["revision"], "receipt": run["receipt"],
        }), 201)
        dossier = retained["product"]
        calculation_ids.append(retained["calculation_id"])

    monkeypatch.setattr("backend.app.api.exotic_pricer.receipt_signing_secret", lambda: "rotated-test-key-unrelated")
    body = {"mode": "archive", "family": "rates", "product_id": product_id,
            "start_calculation_id": calculation_ids[0], "end_calculation_id": calculation_ids[1]}
    explanation = _json(client.post(f"{EXOTICS}/explain-native", json=body))
    assert explanation["status"] == "attributed", explanation
    assert [explanation[key] for key in ("start_archive_id", "end_archive_id")] == calculation_ids
    assert explanation["contractual_pnl_eur"] == pytest.approx(3600.35, abs=.01)
    client.current["user"] = client.users["bob"]
    _json(client.post(f"{EXOTICS}/explain-native", json=body), 404)
