"""Native drafts keep diagnostics without changing terms or frozen dates."""

import pytest
from pydantic import ValidationError

from backend.app.core.product.models import Product
from backend.app.core.product.native_schedule import (
    native_draft_diagnostics, read_native_schedule, resolve_native_schedule,
)
from backend.tests.test_rates_credit_cds_schedule import cds_terms
from backend.tests.test_rates_credit_rates_schedule import abc_reference, abc_terms


@pytest.fixture
def native_terms(abc_terms, cds_terms):
    frn, irs = abc_terms
    return {"FRN": frn, "IRS": irs, "CDS": cds_terms}


@pytest.mark.parametrize(
    ("instrument", "leg", "field", "label"),
    [
        ("FRN", "floating_leg", "margin_bps", "marge contractuelle de la jambe flottante (pb)"),
        ("IRS", "fixed_leg", "coupon_rate", "taux de la jambe fixe"),
        ("CDS", "premium_leg", "coupon_bps", "coupon du CDS (pb)"),
    ],
)
def test_nullable_economics_do_not_prevent_a_frozen_schedule(native_terms, instrument, leg, field, label):
    complete = native_terms[instrument]
    payload = complete.model_dump(mode="json")
    payload[leg][field] = None
    draft = Product.model_validate({"product_id": 101, "terms_version": 1, "terms": payload})
    resolution = resolve_native_schedule(draft.terms, product_id=101, terms_version=1)
    baseline = resolve_native_schedule(complete, product_id=101, terms_version=1)
    assert resolution.status == "ready"
    assert resolution.diagnostics == ()
    assert resolution.schedule.legs == baseline.schedule.legs
    assert resolution.schedule.terms_fingerprint != baseline.schedule.terms_fingerprint

    archived = draft.model_copy(update={"native_schedule": resolution.schedule})
    reopened = Product.model_validate_json(archived.model_dump_json())
    projection = read_native_schedule(reopened)
    assert projection.status == "ready"
    assert projection.schedule == archived.native_schedule
    assert projection.diagnostics == native_draft_diagnostics(reopened) == (
        "À préciser : nominal.", f"À préciser : {label}.",
    )

    payload[leg][field] = 0
    zero = Product.model_validate({"terms": payload, "intent": {"nominal": 1_000_000}})
    assert native_draft_diagnostics(zero) == ()


@pytest.mark.parametrize(
    ("instrument", "date_field", "label"),
    [
        ("FRN", "effective_date", "date d’effet"),
        ("IRS", "maturity_date", "date de maturité"),
        ("CDS", "trade_date", "date de transaction"),
    ],
)
def test_missing_dates_reopen_as_a_draft(native_terms, instrument, date_field, label):
    payload = native_terms[instrument].model_dump(mode="json")
    del payload[date_field]
    nominal = 10_000_000 if instrument == "CDS" else 1_000_000
    draft = Product.model_validate({"terms": payload, "intent": {"nominal": nominal}})
    reopened = Product.model_validate_json(draft.model_dump_json())
    assert getattr(reopened.terms, date_field) is None
    temporary = resolve_native_schedule(reopened.terms)
    assert temporary.status == "incomplete"
    assert temporary.schedule is None
    assert temporary.diagnostics == (f"À préciser : {label}.",)
    assert read_native_schedule(reopened) == temporary


def test_complete_dates_without_archive_stay_not_prepared(native_terms):
    draft = Product(terms=native_terms["IRS"])
    projection = read_native_schedule(draft)
    assert projection.status == "not_prepared"
    assert projection.schedule is None
    assert projection.diagnostics == ("Échéancier figé indisponible.", "À préciser : nominal.")


def test_draft_does_not_fill_structural_fields(native_terms):
    frn = native_terms["FRN"].model_dump(mode="json")
    del frn["floating_leg"]["fixing_calendar"]
    with pytest.raises(ValidationError, match="fixing_calendar"):
        Product.model_validate({"terms": frn})
    cds = native_terms["CDS"].model_dump(mode="json")
    del cds["reference_entity_id"]
    with pytest.raises(ValidationError, match="reference_entity_id"):
        Product.model_validate({"terms": cds})
