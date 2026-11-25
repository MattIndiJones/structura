from datetime import timedelta

import pytest
from pydantic import ValidationError

from backend.app.core.structured_indices.athena import price_athena_issue
from backend.app.core.structured_indices.pricing_catalogue import athena_pricing_catalogue
from backend.app.core.structured_indices.schemas import AthenaFixedCoupon, AthenaIssueRequest, AthenaTerms
from backend.tests.test_structured_indices_athena import (
    FINAL, FIRST, PRICING, SEMIANNUAL, STEP_DOWN_DATES, STRIKE, _fixing, _market, _mark, _terms, _vintage,
)
from backend.tests.test_structured_indices_phoenix import _lifecycle, _phoenix_terms, _principal_discounted


def _memory_terms(**kwargs):
    return AthenaTerms.model_validate({**_phoenix_terms(**kwargs).model_dump(), 'coupon_memory': True})


def test_memory_capability_and_typed_contract_keep_legacy_terms_identical():
    models = {row.id: row for row in athena_pricing_catalogue().payoffs}
    capability = models['phoenix-memory-sx5e']
    assert capability.version == 'phoenix-memory-sx5e-v1'
    assert capability.issue_models == capability.mtm_models == ['constant']
    assert 'coupon_memory' not in _phoenix_terms().model_dump()
    assert 'coupon_memory' not in _terms().model_dump()
    assert _memory_terms().model_dump()['coupon_memory'] is True
    for value in (False, 1, 'true'):
        with pytest.raises(ValidationError):
            AthenaTerms.model_validate({**_phoenix_terms().model_dump(), 'coupon_memory': value})
    with pytest.raises(ValidationError):
        AthenaTerms.model_validate({**_terms().model_dump(), 'coupon_memory': True})


def test_two_missed_coupons_are_paid_once_and_reset_the_live_memory():
    note = _vintage(_memory_terms(days=STEP_DOWN_DATES, months=6))
    recover_day = STEP_DOWN_DATES[2]
    fixings = (_fixing(SEMIANNUAL, 3300.), _fixing(FIRST, 3350.))
    prior = _mark(note, recover_day - timedelta(days=1), fixings, spot=5200.)
    assert prior['claims'] == []
    assert prior['next_call']['probability'] == 1.
    assert prior['next_call']['memory_periods'] == 2
    assert prior['next_call']['redemption_amount'] == pytest.approx(109.)
    paid = (*fixings, _fixing(recover_day, 3500.))
    recover = _mark(note, recover_day, paid, spot=4500.)
    [claim] = recover['claims']
    assert not recover['terminated']
    assert claim['amount'] == 9.
    assert claim['memory_periods'] == 2
    assert claim['pv'] == pytest.approx(_principal_discounted(9., recover_day, note.terms.observations[2].payment_date))
    assert recover['residual_pv'] == pytest.approx(
        _principal_discounted(103., recover_day, note.terms.observations[-1].payment_date), abs=.0002,
    )
    assert recover['next_call']['memory_periods'] == 0
    collection_day = note.terms.observations[2].payment_date
    assert _mark(note, collection_day, paid, spot=4500.)['claims'] == []
    assert _lifecycle(note, collection_day, *paid)['coupon_claims'] == [
        {key: value for key, value in claim.items() if key != 'pv'},
    ]


def test_memory_recalled_at_equality_pays_principal_and_all_coupons_at_target_date():
    note = _vintage(_memory_terms(days=(SEMIANNUAL, FIRST, FINAL), months=6))
    missed = _fixing(SEMIANNUAL, 3400.)
    next_call = _mark(note, FIRST - timedelta(days=1), (missed,), spot=5100.)['next_call']
    assert next_call['probability'] == 1.
    assert next_call['redemption_amount'] == 106.
    assert next_call['memory_periods'] == 1
    mark = _mark(note, FIRST, (missed, _fixing(FIRST, 5000.)))
    assert mark['status'] == 'called' and mark['residual_pv'] == 0.
    coupon, principal = mark['claims']
    assert (coupon['amount'], coupon['memory_periods']) == (6., 1)
    assert principal['amount'] == 100. and 'memory_periods' not in principal
    assert coupon['payment_date'] == principal['payment_date'] == note.terms.observations[1].payment_date.isoformat()
    assert coupon['event_id'] != principal['event_id']


def test_missed_coupons_expire_when_the_last_coupon_barrier_fails():
    note = _vintage(_memory_terms())
    inputs = (_fixing(FIRST, 3300.), _fixing(FINAL, 3400.))
    mark = _mark(note, FINAL, inputs)
    assert mark['status'] == 'matured'
    assert [(flow['kind'], flow['amount']) for flow in mark['claims']] == [('redemption', 100.)]
    assert _lifecycle(note, FINAL, *inputs)['coupon_claims'] == []


def test_coupon_catchup_and_capital_loss_can_coexist_at_maturity():
    note = _vintage(_memory_terms(coupon_barrier=.50))
    mark = _mark(note, FINAL, (_fixing(FIRST, 2400.), _fixing(FINAL, 2750.)))
    assert mark['status'] == 'matured'
    coupon, principal = mark['claims']
    assert (coupon['amount'], coupon['memory_periods']) == (12., 1)
    assert principal['amount'] == pytest.approx(55.)


def test_each_coupon_at_the_barrier_reduces_memory_pricing_to_the_regular_phoenix():
    market = _market(STRIKE, 4500.)
    note = _vintage()
    values = dict(note_id=note.note_id, market=market, initial_fixing=5000., initial_fixing_reference='official',
                  pricing=PRICING, coupon=AthenaFixedCoupon(mode='fixed', fixed_coupon=.06))
    ordinary = price_athena_issue(AthenaIssueRequest(terms=_phoenix_terms(), **values))
    memory = price_athena_issue(AthenaIssueRequest(terms=_memory_terms(), **values))
    assert ordinary['price'] == memory['price']
    assert ordinary['terms_reference'] != memory['terms_reference']
