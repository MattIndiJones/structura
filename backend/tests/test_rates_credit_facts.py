"""Point-in-time checks for the separate synthetic July credit-event recipe."""

from datetime import date, datetime

import pytest
from pydantic import TypeAdapter, ValidationError

from backend.app.core.product.cds_schedule import cds_default_accrued_days, resolve_cds_schedule
from backend.app.core.product.credit_facts import (
    SyntheticCreditFact, SyntheticCreditSelection, SyntheticDefaultFact, SyntheticRecoveryFact,
    SyntheticSettlementFact, select_synthetic_credit_facts,
)
from backend.tests.test_rates_credit_cds_schedule import cds_terms  # noqa: F401


_DEFAULT_ID = "synthetic-july-2021-default"


def _at(day, clock):
    return datetime.fromisoformat(f"2021-07-{day:02d}T{clock}+02:00")


@pytest.fixture
def july_facts():
    # The plan fixes the dates; the publication and validation hours are synthetic.
    return (
        SyntheticDefaultFact(
            default_id=_DEFAULT_ID, fact_id="default-notice-v1", version=1, effect_date=date(2021, 7, 15),
            available_at=_at(15, "09:00:00"), validated_at=_at(15, "10:00:00"),
        ),
        SyntheticRecoveryFact(
            default_id=_DEFAULT_ID, fact_id="recovery-v1", version=1, effect_date=date(2021, 7, 19),
            available_at=_at(19, "11:00:00"), validated_at=_at(19, "12:00:00"), recovery_fraction=0.35,
        ),
        SyntheticSettlementFact(
            default_id=_DEFAULT_ID, fact_id="settlement-v1", version=1, effect_date=date(2021, 7, 20),
            available_at=_at(20, "15:00:00"), validated_at=_at(20, "14:00:00"),
        ),
    )


def test_july_default_recovery_and_confirmation_enter_at_the_cutoff(july_facts, cds_terms):
    before_default = select_synthetic_credit_facts(_DEFAULT_ID, july_facts, _at(15, "09:59:59"))
    assert before_default.state == "alive"
    assert before_default.default is before_default.recovery is before_default.settlement is None

    after_default = select_synthetic_credit_facts(_DEFAULT_ID, july_facts, _at(15, "10:00:00"))
    assert after_default.state == "recovery_pending"
    assert after_default.default == july_facts[0]
    assert after_default.recovery is after_default.settlement is None
    premium, _, _ = resolve_cds_schedule(cds_terms)
    assert premium.periods[1].accrual_start == date(2021, 6, 21)
    assert cds_default_accrued_days(premium.periods[1], after_default.default.effect_date) == 24

    before_recovery = select_synthetic_credit_facts(_DEFAULT_ID, july_facts, _at(19, "11:59:59"))
    assert before_recovery == after_default
    after_recovery = select_synthetic_credit_facts(_DEFAULT_ID, july_facts, _at(19, "12:00:00"))
    assert after_recovery.state == "settlement_pending"
    assert after_recovery.recovery.recovery_fraction == 0.35
    assert after_recovery.settlement is None

    before_settlement = select_synthetic_credit_facts(_DEFAULT_ID, july_facts, _at(20, "14:59:59"))
    assert before_settlement == after_recovery
    after_settlement = select_synthetic_credit_facts(_DEFAULT_ID, july_facts, _at(20, "15:00:00"))
    assert after_settlement.state == "settled"
    assert after_settlement.settlement.effect_date == date(2021, 7, 20)
    assert SyntheticCreditSelection.model_validate_json(after_settlement.model_dump_json()) == after_settlement


def test_late_correction_keeps_historical_recovery_and_accepts_zero(july_facts):
    correction = july_facts[1].model_copy(update={
        "fact_id": "recovery-v2", "version": 2, "recovery_fraction": 0.0,
        "available_at": _at(21, "11:00:00"), "validated_at": _at(21, "12:00:00"),
    })
    candidates = (correction, *july_facts, july_facts[1])
    original = select_synthetic_credit_facts(_DEFAULT_ID, july_facts, _at(20, "16:00:00"))
    assert select_synthetic_credit_facts(_DEFAULT_ID, candidates, _at(20, "16:00:00")) == original
    latest = select_synthetic_credit_facts(_DEFAULT_ID, candidates, _at(21, "12:00:00"))
    assert (latest.recovery.version, latest.recovery.recovery_fraction) == (2, 0.0)
    assert latest.settlement == original.settlement
    assert original.recovery.recovery_fraction == 0.35


def test_effect_date_and_validation_are_required_independently(july_facts):
    early_notice = july_facts[0].model_copy(update={
        "available_at": _at(14, "09:00:00"), "validated_at": _at(14, "10:00:00"),
    })
    before_effect = select_synthetic_credit_facts(_DEFAULT_ID, [early_notice], _at(14, "12:00:00"))
    assert before_effect.state == "alive"
    at_effect = select_synthetic_credit_facts(
        _DEFAULT_ID, [early_notice], datetime.fromisoformat("2021-07-14T22:00:00+00:00"),
    )
    assert at_effect.state == "recovery_pending"
    unvalidated = july_facts[0].model_copy(update={"validated_at": None})
    assert select_synthetic_credit_facts(_DEFAULT_ID, [unvalidated], _at(16, "12:00:00")).state == "alive"
    late_notice = july_facts[0].model_copy(update={"validated_at": _at(16, "10:00:00")})
    assert select_synthetic_credit_facts(_DEFAULT_ID, [late_notice], _at(15, "12:00:00")).state == "alive"
    assert select_synthetic_credit_facts(_DEFAULT_ID, [late_notice], _at(16, "10:00:00")).default.effect_date == date(2021, 7, 15)


def test_fact_scope_and_duplicate_version_are_checked(july_facts):
    assert select_synthetic_credit_facts("other-default", july_facts, _at(20, "16:00:00")).state == "alive"
    duplicate = july_facts[1].model_copy(update={"fact_id": "conflicting-notice", "recovery_fraction": 0.36})
    with pytest.raises(ValueError, match="même version"):
        select_synthetic_credit_facts(_DEFAULT_ID, (*july_facts, duplicate), _at(20, "16:00:00"))
    with pytest.raises(ValueError, match="fuseau"):
        select_synthetic_credit_facts(_DEFAULT_ID, july_facts, _at(20, "16:00:00").replace(tzinfo=None))
    payload = july_facts[0].model_dump(mode="json")
    payload["available_at"] = "2021-07-15T09:00:00"
    with pytest.raises(ValidationError):
        TypeAdapter(SyntheticCreditFact).validate_python(payload)
