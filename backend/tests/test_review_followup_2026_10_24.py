"""Calendar-origin, settlement wording and CCR metric contract regressions."""
from copy import deepcopy
from datetime import date, timedelta

import numpy as np
import pytest
from fastapi import HTTPException

from backend.app.api import pricing
from backend.app.core.ccr.contracts import CreditProfile
from backend.app.core.ccr.exposure import summarize
from backend.app.core.ccr.service import evaluate_inputs
from backend.app.core.deal_valuation import mtm_core
from backend.app.core.payscript import engine
from backend.app.core.payscript.parser import parse_script, resolve_constats
from backend.app.core.product.calendar import freeze_calendar, restore_calendar
from backend.tests.test_ccr import inputs, proposed
from backend.tests.test_market_data_lot4 import _deal, _session


ORIGIN = date(2026, 1, 5)
SCRIPT = "CONSTAT OBS\nAT OBS:\n  PAY MAX(S[1] - 1, 0)"
UL = [{"name": "A", "ticker": "A", "ccy": "EUR", "sigma": .2, "q": 0.}]


@pytest.mark.parametrize("observed", ["2026-01-04", "2026-01-05"])
@pytest.mark.parametrize("schedule", [False, True])
def test_named_observations_at_or_before_origin_are_refused(observed, schedule):
    source = SCRIPT.replace("CONSTAT OBS", "CONSTAT() OBS") if schedule else SCRIPT
    values = ({"first_observation_date": observed, "end_date": "2026-02-05",
               "roll_date": observed, "frequency": "1M"} if schedule else {"date": observed})
    with pytest.raises(ValueError, match="strictement positives"):
        resolve_constats(parse_script(source), {"OBS": values}, anchor=ORIGIN, currency="EUR")


@pytest.mark.parametrize("convention", ["following", "preceding"])
def test_named_observation_is_validated_after_business_day_adjustment(convention):
    # Saturday rolls onto the Monday origin or the preceding Friday.
    with pytest.raises(ValueError, match="strictement positives"):
        resolve_constats(parse_script(SCRIPT), {"OBS": {"date": "2026-01-03",
            "convention": convention}}, anchor=ORIGIN, currency="EUR")


def test_selected_window_fixing_cannot_bypass_origin_validation():
    source = "CONSTAT() OBS AVG\nAT OBS[1][1]:\n  PAY S[1]"
    with pytest.raises(ValueError, match="strictement positives"):
        resolve_constats(parse_script(source), {"OBS": {
            "first_observation_date": "2026-01-07", "end_date": "2026-01-07",
            "frequency": "1M", "window_length": "3D", "window_frequency": "1D",
        }}, anchor=ORIGIN, currency="EUR")


def test_only_executed_observations_are_checked_not_unused_calendar_dates():
    source = "CONSTAT() OBS\nAT OBS.last:\n  PAY 1"
    compiled = resolve_constats(parse_script(source), {"OBS": {
        "first_observation_date": ORIGIN.isoformat(), "end_date": "2026-02-05",
        "frequency": "1M"}}, anchor=ORIGIN, currency="EUR")
    assert compiled.events[0].dates == [round(31 / 365.25, 6)]
    result = engine.run_mc(compiled, UL, [[1.]], .03, 1., 4, antithetic=False)
    assert result["price"] == pytest.approx(np.exp(-.03 * round(31 / 365.25, 6)))


@pytest.mark.parametrize("when", [0., -1 / 365.25])
def test_frozen_calendars_cannot_restore_nonfuture_observations(when):
    compiled = resolve_constats(parse_script(SCRIPT), {"OBS": "2026-01-06"}, anchor=ORIGIN)
    frozen = deepcopy(freeze_calendar(compiled))
    frozen["events"][0]["dates"] = [when]
    frozen["schedule"]["constatations"][0]["t"] = when
    with pytest.raises(ValueError, match="strictement positives"):
        restore_calendar(parse_script(SCRIPT), frozen)


@pytest.mark.parametrize("when", [0., -.01])
def test_engine_refuses_invalid_compiled_dates_before_simulation(monkeypatch, when):
    compiled = parse_script("AT 1:\n  PAY MAX(S[1] - 1, 0)")
    compiled.events[0].dates = [when]
    def forbidden(*args, **kwargs):
        pytest.fail("An invalid observation must not start a diffusion")
    monkeypatch.setattr(engine, "_simulate_gbm", forbidden)
    with pytest.raises(ValueError, match="strictement positives"):
        engine.run_mc(compiled, UL, [[1.]], 0., 1., 4)


@pytest.mark.parametrize("frozen", [False, True])
def test_price_http_refuses_origin_observation_before_mc(authenticated_client, monkeypatch, frozen):
    authenticated_client.app.include_router(pricing.router)
    def forbidden(*args, **kwargs):
        raise AssertionError("The API must reject invalid dates before Monte Carlo")
    monkeypatch.setattr(pricing, "run_valuation", forbidden)
    body = dict(script=SCRIPT, underlyings=UL, corr_matrix=[[1.]], r=0., T=1., N=1000,
                strike_date=ORIGIN.isoformat(), constats={"OBS": ORIGIN.isoformat()})
    if frozen:
        valid = resolve_constats(parse_script(SCRIPT), {"OBS": "2026-01-06"}, anchor=ORIGIN)
        body["frozen_schedule"] = freeze_calendar(valid)
        body["frozen_schedule"]["events"][0]["dates"] = [0.]
        body["frozen_schedule"]["schedule"]["constatations"][0]["t"] = 0.
    response = authenticated_client.post("/api/price", json=body)
    assert response.status_code == 422, response.text
    assert "strictement positives" in response.json()["detail"]


@pytest.mark.parametrize("days_after_payment", [0, 5])
def test_contractual_payment_date_does_not_claim_bank_settlement(days_after_payment):
    with _session() as session:
        payment = date.today() - timedelta(days=days_after_payment)
        deal = _deal(session, status="en_reglement", maturity=payment - timedelta(days=2), payment=payment)
        deal.settlement_amount = 1.
        session.add(deal)
        session.commit()
        with pytest.raises(HTTPException) as exc:
            mtm_core(deal, session, 4)
        assert exc.value.status_code == 422
        assert "contractuelle" in exc.value.detail
        assert "bancaire" in exc.value.detail
        assert "soldée" not in exc.value.detail
        session.refresh(deal)
        assert deal.status == "en_reglement" and deal.settlement_amount == 1.


def test_ccr_distinguishes_current_ee_profile_and_time_average():
    exposure = np.array([[100., 100.], [60., 60.], [0., 0.]])
    result = summarize(exposure, exposure, [0., .5, 2.], 0., CreditProfile())
    assert result["current_exposure"] == 100.
    assert [row["ee"] for row in result["profile"]] == [100., 60., 0.]
    assert result["epe"] == 70.  # (100 * 0.5 + 60 * 1.5) / 2
    assert "ee" not in result


@pytest.mark.parametrize("mode", ["FULL", "FAST"])
def test_ccr_new_results_never_publish_ambiguous_scalar_ee(mode):
    snapshot = inputs([proposed()])
    snapshot["request"]["mode"] = mode
    result = evaluate_inputs(snapshot)
    for block in [result["before"], result["after"], result["standalone"], *result["deals"]]:
        assert "ee" not in block
        assert "current_exposure" in block and "epe" in block
    if mode == "FAST":
        assert result["after"]["epe"] is None
    else:
        assert result["after"]["epe"] > 0
