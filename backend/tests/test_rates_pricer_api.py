"""End-to-end native and scripted rates pricing on the isolated Product store."""

from copy import deepcopy

import pytest

from backend.app.db.models import ProductCalculationRun, ProductRecord
from backend.tests.test_products import _browser_json_roundtrip, product_client  # noqa: F401
from backend.tests.test_rates_credit_market_integration import _count
from backend.tests.test_rates_credit_native_writes import native_recipe_client  # noqa: F401
from backend.tests.test_rates_credit_rates_schedule import abc_reference  # noqa: F401


_PRICER = "/api/products/rates"


@pytest.fixture(autouse=True)
def signing_key(monkeypatch):
    monkeypatch.setattr("backend.app.api.rates_pricer.receipt_signing_secret", lambda: "isolated-rates-receipts-only")


def _json(response, status=200):
    assert response.status_code == status, response.text
    return response.json()


def _draft(pilot, mode):
    terms = dict(pilot["terms"])
    if mode == "scripted":
        terms.update(payoff_mode=mode, rates_script=pilot["script"])
    return {"name": pilot["name"], "terms": terms, "intent": pilot["intent"]}


def _expected(instrument, run, snapshot):
    expected = snapshot[f"{instrument.lower()}_expected_eur"]
    if instrument == "FRN":
        assert run["measure"]["unit"] == "per_100_notional"
        assert run["measure"]["value"] == pytest.approx(float(snapshot["frn_clean_price"]), abs=1e-7)
        assert run["dirty_pv_eur"] == pytest.approx(float(expected["dirty_pv"]), abs=.01)
        assert run["clean_pv_eur"] == pytest.approx(float(expected["clean_pv"]), abs=.01)
        assert run["accrued_eur"] == pytest.approx(float(expected["accrued"]), abs=.01)
    else:
        assert run["measure"]["unit"] == "EUR"
        assert run["net_pv_eur"] == pytest.approx(float(expected["net_pv"]), abs=.01)
        assert run["fixed_pv_eur"] == pytest.approx(float(expected["fixed_pv"]), abs=.01)
        assert run["floating_pv_eur"] == pytest.approx(-float(expected["floating_pv_abs"]), abs=.01)
        assert run["par_rate"] == pytest.approx(float(snapshot["irs_par_rate"]), abs=1e-8)
    for component in ("discount", "projection"):
        assert run["sensitivities"][f"{component}_eur"] == pytest.approx(
            float(snapshot["dv01_eur"][f"{instrument.lower()}_{component}"]), abs=.01,
        )


def test_catalogue_and_both_exploratory_modes_use_the_six_reference_cases(product_client, abc_reference):
    client = product_client
    catalogue = _json(client.get(f"{_PRICER}/pilots"))
    assert [item["id"] for item in catalogue["cases"]] == ["A", "B", "C"]
    assert not catalogue["can_retain"] and catalogue["market_quality"] == "synthetic"
    assert [pilot["instrument_type"] for pilot in catalogue["products"]] == ["FRN", "IRS"]
    for pilot in catalogue["products"]:
        for mode in ("native", "scripted"):
            draft = _draft(pilot, mode)
            if mode == "scripted":
                validated = _json(client.post(f"{_PRICER}/validate-script", json={"terms": draft["terms"]}))
                assert validated["valid"] and validated["profile"] == "rates-deterministic-v1"
            for case, snapshot in abc_reference["snapshots"].items():
                priced = _json(client.post(f"{_PRICER}/price", json={
                    "case": case, "terms": draft["terms"], "intent": draft["intent"],
                }))
                _expected(pilot["instrument_type"], priced["result"], snapshot)
                assert priced["context"]["product_id"] is None
                assert priced["context"]["market"]["market_id"] == snapshot["market_id"]
                assert priced["result"]["flows"][0]["state"] == snapshot["first_payment_state"]
                assert (priced["script"] is not None) == (mode == "scripted")
                assert len(priced["receipt"]["calculation_identity"]["engine_fingerprint"]) == 64
                if case == "C":
                    assert priced["result"]["realized_cash_eur"] == float(
                        abc_reference["first_payment"][f"{pilot['instrument_type'].lower()}_cash_eur"],
                    )
    assert _count(client, ProductRecord) == _count(client, ProductCalculationRun) == 0


@pytest.mark.parametrize("mode", ["native", "scripted"])
def test_archive_round_trip_preserves_terms_result_and_measure_per_case(native_recipe_client, abc_reference, mode):
    client = native_recipe_client
    catalogue = _json(client.get(f"{_PRICER}/pilots"))
    assert catalogue["can_retain"]
    for pilot in catalogue["products"]:
        instrument = pilot["instrument_type"]
        dossier = _json(client.post("/api/products/native", json={
            "command_key": f"create-rates-{instrument}", **_draft(pilot, mode),
        }), 201)
        product_id = dossier["product_id"]
        archive_url = f"/api/products/{product_id}/rates/calculations"
        for case, snapshot in abc_reference["snapshots"].items():
            priced = _json(client.post(f"{_PRICER}/price", json={
                "case": case, "product_id": product_id, "expected_revision": dossier["revision"],
                "expected_terms_version": dossier["terms_version"],
            }))
            _expected(instrument, priced["result"], snapshot)
            assert priced["context"]["product_id"] == product_id
            body = _browser_json_roundtrip({
                "command_key": f"archive-rates-{instrument}-{case}", "expected_revision": dossier["revision"],
                "receipt": priced["receipt"],
            })
            if case == "A":
                tampered = deepcopy(body)
                tampered["receipt"]["result"]["measure"]["value"] += 1
                assert client.post(archive_url, json=tampered).status_code == 422
            archived = _json(client.post(archive_url, json=body), 201)
            assert _json(client.post(archive_url, json=body), 201) == archived
            dossier = archived["product"]
            reopened = _json(client.get(f"{archive_url}/{archived['calculation_id']}"))
            assert {key: value for key, value in reopened.items() if key != "calculation_id"} == priced
        limited = _json(client.get(f"/api/products/{product_id}?view=mixed&calculations_limit=2"))
        assert len(limited["calculations"]) == 2 and limited["calculation_page"]["has_more"]
        unit = "EUR" if instrument == "IRS" else "per_100_notional"
        assert all(ref["price_unit"] == unit for ref in limited["calculations"])
        second = _json(client.get(f"/api/products/{product_id}?view=mixed&calculations_limit=1&calculations_offset=1"))
        assert second["calculations"] == [dossier["calculations"][-2]]
        assert second["latest_price"] == dossier["calculations"][-1]["price"]
        summary = next(row for row in _json(client.get("/api/products?view=mixed")) if row["id"] == product_id)
        assert summary["latest_price_unit"] == unit
        assert summary["latest_price"] == dossier["calculations"][-1]["price"]
    assert _count(client, ProductCalculationRun) == 6


def test_modified_case_c_keeps_the_detached_coupon_open(product_client):
    client = product_client
    pilot = _json(client.get(f"{_PRICER}/pilots"))["products"][0]
    draft = _draft(pilot, "scripted")
    draft["terms"]["floating_leg"]["margin_bps"] = 110
    response = _json(client.post(f"{_PRICER}/price", json={
        "case": "C", "terms": draft["terms"], "intent": draft["intent"],
    }))
    result = response["result"]
    assert response["warnings"] and not response["context"]["market"]["payments"]
    assert result["realized_cash_eur"] == 0
    assert result["flows"][0]["state"] == "due_open"
    assert result["detached_pv_eur"] == pytest.approx(1_000_000 * (.031 + .011) * 91 / 360)


def test_existing_archive_does_not_depend_on_the_active_receipt_key(native_recipe_client, monkeypatch):
    client = native_recipe_client
    pilot = _json(client.get(f"{_PRICER}/pilots"))["products"][0]
    dossier = _json(client.post("/api/products/native", json={
        "command_key": "create-receipt-rotation", **_draft(pilot, "native"),
    }), 201)
    product_id = dossier["product_id"]
    archive_url = f"/api/products/{product_id}/rates/calculations"
    pricing = _json(client.post(f"{_PRICER}/price", json={
        "case": "A", "product_id": product_id, "expected_revision": 1, "expected_terms_version": 1,
    }))
    command = {"command_key": "archive-key-rotation", "expected_revision": 1, "receipt": pricing["receipt"]}
    archived = _json(client.post(archive_url, json=command), 201)
    monkeypatch.setattr("backend.app.api.rates_pricer.receipt_signing_secret", lambda: "new-isolated-secret")
    assert _json(client.post(archive_url, json=command), 201) == archived
    reopened = _json(client.get(f"{archive_url}/{archived['calculation_id']}"))
    assert reopened["receipt"] == pricing["receipt"]
    assert reopened["result"] == pricing["result"]


def test_archived_market_price_respects_rights_and_current_position_and_keeps_old_calculation(
    native_recipe_client, abc_reference, monkeypatch,
):
    from backend.app.services.product_repository import load_product
    from backend.tests.test_rates_credit_market_integration import _body, _create_context, _read_context
    from backend.tests.test_rates_credit_mixed_reader import _assert_error
    from backend.tests.test_rates_credit_native_writes import _revision_body, _revision_url
    from backend.tests.test_rates_credit_rates_market import build_rates_market

    client = native_recipe_client
    frn = _json(client.get(f"{_PRICER}/pilots"))["products"][0]
    initial = _json(client.post("/api/products/native", json={
        "command_key": "context-rate-frn-create", **_draft(frn, "native"),
    }), 201)
    product_id = initial["product_id"]
    product = load_product(client.session, product_id, allow_native=True)
    snapshot = abc_reference["snapshots"]["B"]
    sent = build_rates_market(abc_reference, (product,), "B").model_dump(mode="json")
    context_request = _body(
        product, "context-rate-frn-original", snapshot["cutoff_local"], snapshot["valuation_date"], sent,
    )
    prepared = _create_context(client, product, context_request)

    def no_synthetic_market(*args, **kwargs):
        pytest.fail("Archived context pricing must use its stored market")

    monkeypatch.setattr("backend.app.api.rates_pricer._synthetic_context", no_synthetic_market)
    price_request = {
        "product_id": product_id, "context_id": prepared["context_id"],
        "expected_revision": initial["revision"], "expected_terms_version": initial["terms_version"],
    }
    priced = _json(client.post(f"{_PRICER}/price", json=price_request))
    assert priced["context"] == prepared["context"]
    assert priced["receipt"]["context_id"] == prepared["context_id"]
    _expected("FRN", priced["result"], snapshot)

    archive_url = f"/api/products/{product_id}/rates/calculations"
    archive_request = {"command_key": "context-rate-frn-archive", "expected_revision": initial["revision"],
                       "receipt": priced["receipt"]}
    archived = _json(client.post(archive_url, json=archive_request), 201)
    archived_url = f"{archive_url}/{archived['calculation_id']}"
    historical = _json(client.get(archived_url))
    assert {key: historical[key] for key in priced} == priced

    with_new_position = _json(client.post(_revision_url(product_id), json={
        **_revision_body(archived["product"], key="context-rate-frn-intent", terms=initial["terms"]),
        "intent": {"nominal": 2_000_000, "side": "SELL"},
    }))
    assert with_new_position["terms_version"] == initial["terms_version"]
    _assert_error(client.post(f"{_PRICER}/price", json=price_request), "PRODUCT_REVISION_STALE")
    new_position_request = {**price_request, "expected_revision": with_new_position["revision"]}
    _assert_error(client.post(f"{_PRICER}/price", json=new_position_request), "RATES_CONTEXT_STALE")
    _assert_error(client.post(archive_url, json={
        **archive_request, "command_key": "context-rate-frn-outdated-proof",
        "expected_revision": with_new_position["revision"],
    }), "RATES_RECEIPT_MISMATCH")

    fresh = _create_context(client, product, {**context_request, "command_key": "context-rate-frn-fresh"})
    fresh_request = {**new_position_request, "context_id": fresh["context_id"]}
    repriced = _json(client.post(f"{_PRICER}/price", json=fresh_request))
    assert repriced["result"]["perspective"] == "short"
    assert repriced["result"]["nominal_eur"] == 2_000_000
    assert repriced["result"]["dirty_pv_eur"] == pytest.approx(-2 * priced["result"]["dirty_pv_eur"], rel=0, abs=.01)

    new_terms = deepcopy(with_new_position["terms"])
    new_terms["floating_leg"]["margin_bps"] = 110
    amended = _json(client.post(_revision_url(product_id), json=_revision_body(
        with_new_position, key="context-rate-frn-new-terms", terms=new_terms,
    )))
    assert amended["terms_version"] == initial["terms_version"] + 1
    _assert_error(client.post(f"{_PRICER}/price", json={
        **fresh_request, "expected_revision": amended["revision"], "expected_terms_version": amended["terms_version"],
    }), "RATES_PRICE_CONTEXT_MISMATCH", 422)
    assert _read_context(client, product, prepared["context_id"]) == prepared
    assert _json(client.get(archived_url)) == historical
    assert _count(client, ProductCalculationRun) == 1

    client.current["user"] = client.users["bob"]
    assert client.post(f"{_PRICER}/price", json=fresh_request).status_code == 404
    assert client.get(archived_url).status_code == 404
    client.current["user"] = client.users["alice"]
    assert _json(client.get(archived_url)) == historical


def test_edited_rates_script_is_sealed_exactly_and_remains_readable_after_another_edit(
    native_recipe_client, monkeypatch,
):
    from hashlib import sha256

    from backend.tests.test_rates_credit_native_writes import _revision_body, _revision_url

    client = native_recipe_client
    frn = _json(client.get(f"{_PRICER}/pilots"))["products"][0]
    draft = _draft(frn, "scripted")
    terms = deepcopy(draft["terms"])
    label = "Coupon Euribor, version éditée"
    source = ("# Référence de recette exacte\n" + terms["rates_script"]["source"].replace("Coupon Euribor", label)).replace("\n", "\r\n")
    terms["rates_script"]["source"] = source + "\r\n"
    source = terms["rates_script"]["source"]
    dossier = _json(client.post("/api/products/native", json={
        **draft, "terms": terms, "command_key": "exact-script-rates-create",
    }), 201)
    product_id = dossier["product_id"]
    priced = _json(client.post(f"{_PRICER}/price", json={
        "case": "B", "product_id": product_id, "expected_revision": dossier["revision"],
        "expected_terms_version": dossier["terms_version"],
    }))
    assert priced["result"]["flows"][0]["label"] == label
    assert priced["receipt"]["terms"]["rates_script"]["source"] == source
    assert priced["script"]["source_hash"] == sha256(source.replace("\r\n", "\n").rstrip("\n").encode("utf-8")).hexdigest()

    archive_url = f"/api/products/{product_id}/rates/calculations"
    request = _browser_json_roundtrip({
        "command_key": "exact-script-rates-archive", "expected_revision": dossier["revision"], "receipt": priced["receipt"],
    })
    tampered = deepcopy(request)
    tampered["receipt"]["terms"]["rates_script"]["source"] = source.replace("\r\n", "\n")
    assert client.post(archive_url, json=tampered).status_code == 422
    assert _count(client, ProductCalculationRun) == 0
    archived = _json(client.post(archive_url, json=request), 201)

    amended_terms = deepcopy(terms)
    amended_terms["rates_script"]["source"] = source.replace(label, "Coupon Euribor, deuxième version")
    amended = _json(client.post(_revision_url(product_id), json=_revision_body(
        archived["product"], key="exact-script-rates-amend", terms=amended_terms,
    )))
    assert amended["terms_version"] == dossier["terms_version"] + 1
    assert amended["terms"]["rates_script"]["source"] != source

    def no_repricing(*args, **kwargs):
        pytest.fail("Reopening a retained calculation must use its stored result")

    monkeypatch.setattr("backend.app.api.rates_pricer.price_rates", no_repricing)
    client.restore_archive()
    reopened = _json(client.get(f"{archive_url}/{archived['calculation_id']}"))
    assert reopened["receipt"]["terms"]["rates_script"]["source"] == source
    assert {key: reopened[key] for key in priced} == priced


def test_rates_calculation_conservation_rolls_back_before_commit_and_profile_can_be_closed(
    native_recipe_client, monkeypatch,
):
    from sqlmodel import Session, select

    from backend.app.db.models import AuditEvent, ProductCommand, ProductRevision
    from backend.tests.test_rates_credit_mixed_reader import _assert_error

    client = native_recipe_client
    pilot = _json(client.get(f"{_PRICER}/pilots"))["products"][1]
    dossier = _json(client.post("/api/products/native", json={
        "command_key": "atomic-rates-create", **_draft(pilot, "native"),
    }), 201)
    product_id = dossier["product_id"]
    price_request = {"case": "A", "product_id": product_id, "expected_revision": dossier["revision"],
                     "expected_terms_version": dossier["terms_version"]}
    priced = _json(client.post(f"{_PRICER}/price", json=price_request))
    archive_request = {"command_key": "atomic-rates-retain", "expected_revision": dossier["revision"],
                       "receipt": priced["receipt"]}
    archive_url = f"/api/products/{product_id}/rates/calculations"
    models = (ProductCalculationRun, ProductRevision, AuditEvent, ProductCommand)
    counts = [_count(client, model) for model in models]

    def interrupt_commit():
        row = client.session.exec(select(ProductCalculationRun)).one()
        assert (row.product_id, row.input_revision, row.kind) == (product_id, dossier["revision"], "RATES_PRICING")
        assert [_count(client, model) for model in models] == [count + 1 for count in counts]
        with Session(client.session.get_bind()) as observer:
            assert observer.exec(select(ProductCalculationRun)).all() == []
        raise RuntimeError("injected rates commit failure")

    with monkeypatch.context() as fault:
        fault.setattr(client.session, "commit", interrupt_commit)
        with pytest.raises(RuntimeError, match="injected rates commit failure"):
            client.post(archive_url, json=archive_request)
    assert [_count(client, model) for model in models] == counts
    assert _json(client.get(f"/api/products/{product_id}?view=mixed")) == dossier

    archived = _json(client.post(archive_url, json=archive_request), 201)
    assert _json(client.post(archive_url, json=archive_request), 201) == archived
    assert [_count(client, model) for model in models] == [count + 1 for count in counts]
    _assert_error(client.post(f"{_PRICER}/price", json=price_request), "PRODUCT_REVISION_STALE")

    monkeypatch.setenv("STRUCTURA_NATIVE_WRITES", "0")
    _assert_error(client.post(archive_url, json=archive_request), "NATIVE_PRODUCT_WRITES_CLOSED", 403)
    assert _json(client.get(f"{archive_url}/{archived['calculation_id']}"))["receipt"] == priced["receipt"]
    current = _json(client.get(f"/api/products/{product_id}?view=mixed"))
    assert current["revision"] == archived["product"]["revision"]
    assert not current["capabilities"]["write"]
    assert [_count(client, model) for model in models] == [count + 1 for count in counts]
