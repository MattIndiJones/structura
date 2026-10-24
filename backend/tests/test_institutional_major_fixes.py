"""Financial regressions from the isolated institutional acceptance audit."""
from datetime import date
from types import SimpleNamespace
import json
import math

import numpy as np
import pytest
from fastapi import HTTPException
from sqlmodel import Session, SQLModel, create_engine

from backend.app.core.ccr import service as credit
from backend.app.core.ccr.contracts import CalculationRequest
from backend.app.core.payscript import engine
from backend.app.core.payscript.parser import parse_script
from backend.app.core.payscript.time_grid import times
from backend.app.db.models import Counterparty, Entity, User
from backend.app.db.trading_models import TradingRelationship
from backend.tests.test_rfq_execution import execution_context, booking_body

UL = [{"name": "A", "ticker": "SYNTHETIC", "ccy": "EUR", "sigma": 0., "q": 0.}]


@pytest.mark.parametrize("day", [19, 30, 31, 183])
def test_observed_forward_and_discount_share_exact_contract_date(day):
    t = day / 365.25
    script = parse_script(f"AT {t:.12f}:\n  PAY WOF")
    result = engine.run_mc(script, UL, [[1.]], .03, 1., 8, per_path_flows=True)
    assert result["price"] == pytest.approx(1., abs=5.1e-7)
    assert any(abs(x-t) < 1e-12 for x in result["time_axis"]["grid_times"])
    assert result["path_flows"][0][0][1] == pytest.approx(math.exp(.03*t), abs=1e-10)


def test_distinct_observations_in_one_week_have_distinct_levels_and_window_weights():
    early, late = 30/365.25, 31/365.25
    script = parse_script(f"AT {late}:\n  PAY WOF\nAT {early}:\n  PAY WOF")
    result = engine.run_mc(script, UL, [[1.]], .03, 1., 8, per_path_flows=True)
    flows = result["path_flows"][0]
    assert flows[0][0] == early and flows[1][0] == late
    assert flows[0][1] < flows[1][1]
    assert result["price"] == 2.


@pytest.mark.parametrize("model", ["constant", "heston", "sabr", "localvol", "lsv"])
def test_models_use_each_contract_interval_without_path_interpolation(model):
    from dataclasses import replace
    script = parse_script("AT MATURITY:\n  PAY WOF")
    script = replace(script, events=[replace(script.events[0], type="AT", dates=[19/365.25])])
    ul = [{**UL[0], "sigma": .2, "v0": .04, "theta": .04, "xi": .3, "rho_h": -.5,
           "kappa": 2., "alpha": .2, "beta": 1., "rho": -.3, "nu": .4}]
    first = engine.run_mc(script, ul, [[1.]], .03, 1., 2000, model=model)
    second = engine.run_mc(script, ul, [[1.]], .03, 1., 2000, model=model)
    assert first["price"] == second["price"]
    assert abs(first["price"]-1.) <= (first["ic95"][1]-first["ic95"][0])*2 + .001


def test_nonuniform_gbm_variance_and_correlation_are_contractual():
    ts, dt = engine._simulation_axis(1., parse_script(f"AT {19/365.25}:\n  PAY 1"))
    rng = np.random.default_rng(20261024)
    corr = [[1., .6], [.6, 1.]]
    ul = [{**UL[0], "sigma": .2}, {**UL[0], "sigma": .3}]
    paths = engine._simulate_gbm(ts, 2, 30000, dt, np.sqrt(dt), ul, .03,
                                 np.linalg.cholesky(corr), rng.standard_normal((ts, 2, 30000)))
    step = engine._step_at(dt, 19/365.25)
    observed = np.log(paths[step])
    assert observed.var(axis=1) == pytest.approx(np.array([.2**2, .3**2])*19/365.25, rel=.025)
    assert np.corrcoef(observed)[0, 1] == pytest.approx(.6, abs=.015)


@pytest.mark.parametrize('seed', [42, 117, 901])
def test_off_grid_call_matches_black_scholes_at_observation_maturity(seed):
    from scipy.stats import norm
    t, r, sigma = 19/365.25, .03, .2
    script = parse_script(f'AT {t}:\n  PAY MAX(WOF - 1, 0)')
    d1 = (r+.5*sigma*sigma)*math.sqrt(t)/sigma
    exact = norm.cdf(d1)-math.exp(-r*t)*norm.cdf(d1-sigma*math.sqrt(t))
    result = engine.run_mc(script, [{**UL[0], 'sigma':sigma}], [[1.]], r, 1., 16000, seed=seed)
    se = (result['ic95'][1]-result['ic95'][0])/3.92
    assert abs(result['price']-exact) <= 4*se+1e-6


def test_daily_window_keeps_each_contractual_fixing_weight():
    from dataclasses import replace
    dates = [19/365.25, 20/365.25, 21/365.25]
    script = parse_script(f"AT {dates[-1]}:\n  PAY WOF")
    script = replace(script, events=[replace(script.events[0], window_dates=[dates], reduction="AVG")])
    result = engine.run_mc(script, UL, [[1.]], .1, 1., 8)
    expected = np.mean(np.exp(.1*np.array(dates))) * math.exp(-.1*dates[-1])
    assert result['price'] == pytest.approx(expected, abs=5.1e-7)
    assert result['constatation_windows'][0]['points_retenus'] == 3


def test_mtf_cut_between_two_dates_does_not_replay_tomorrows_fixing():
    early, late, mark = 30/365.25, 31/365.25, 30.5/365.25
    script = parse_script(f"AT {early}:\n  PAY WOF\nAT {late}:\n  PAY WOF")
    options = dict(r=.03, T_max=1., main_price=200., n_outer=4, n_inner=4, mtm_dates=[mark])
    fan = engine.run_mark_to_future(script, UL, [[1.]], **options)
    row = fan['results'][0]
    assert row['realized_flows'][0] == pytest.approx([(early, math.exp(.03*early))])
    assert row['pvs'] == pytest.approx([100*math.exp(.03*mark)]*4, abs=5.1e-5)
    panel = engine.run_mtf_drilldown(script, UL, [[1.]], t0=mark, scenario_ids=[0], **options)
    scenario = panel['scenarios'][0]
    assert scenario['mtf'] == pytest.approx(row['pvs'][0], abs=5.1e-5)
    assert len(scenario['future_flows']) == 1
    assert scenario['future_flows'][0]['t_abs'] == pytest.approx(late, abs=1e-6)


@pytest.mark.parametrize('a_r', [0., .3])
def test_nonuniform_stochastic_discounted_forward_cancels_on_every_path(a_r):
    script = parse_script(f"AT {19/365.25}:\n  PAY WOF")
    result = engine.run_mc(script, UL, [[1.]], .03, 1., 2000, sigma_r=.02, a_r=a_r)
    assert result['price'] == 1.
    assert result['ic95'] == [1., 1.]


@pytest.fixture
def legal_case(monkeypatch):
    db = create_engine("sqlite://")
    SQLModel.metadata.create_all(db)
    session = Session(db)
    user = User(id=1, username="Synthetic", email="test@example.invalid", role="admin", entity_id=1, password_hash="x")
    session.add_all([Entity(id=1, name="Synthetic"), user, Counterparty(id=1, name="Synthetic bank")])
    session.commit()
    config = {"agreements": [{"id": 1, "data": {"status": "ACTIVE", "effective_date": "2023-01-01"}}],
              "netting-sets": [{"id": 1, "data": {"active": True, "currency": "EUR", "product_scope": ["call"],
                               "master_agreement_id": 1, "csa_id": None}}], "csas": [], "limits": []}
    monkeypatch.setattr(credit, "records", lambda *_: config)
    monkeypatch.setattr(credit, "business_today", lambda: date(2024, 1, 2))
    body = SimpleNamespace(transaction_format="OTC", instrument_family="Option", documentation_reference="FICTIF",
        ccr_netting_set_id=1, counterparty_id=1, devise="EUR", product_type="call", legal_identity_exception=None)
    yield session, user, config, body
    session.close()


@pytest.mark.parametrize("status", ["PENDING", "INACTIVE", "UNKNOWN"])
def test_otc_pending_or_inactive_agreement_refused(legal_case, status):
    session, user, config, body = legal_case
    config["agreements"][0]["data"]["status"] = status
    with pytest.raises(HTTPException) as exc:
        credit.enforce_booking(session, user, body)
    assert exc.value.status_code == 422


@pytest.mark.parametrize("changes", [{"effective_date": "2025-01-01"}, {"expiry_date": "2023-12-31"}])
def test_otc_agreement_must_be_effective_at_business_date(legal_case, changes):
    session, user, config, body = legal_case
    config["agreements"][0]["data"].update(changes)
    with pytest.raises(HTTPException): credit.enforce_booking(session, user, body)


@pytest.mark.parametrize("changes", [{"ccr_netting_set_id": None}, {"documentation_reference": None},
    {"transaction_format": None}, {"instrument_family": "Note"}, {"counterparty_id": None}])
def test_otc_missing_assignment_documentation_or_classification_refused(legal_case, changes):
    session, user, _, body = legal_case
    for key, value in changes.items(): setattr(body, key, value)
    with pytest.raises(HTTPException): credit.enforce_booking(session, user, body)


def test_effective_otc_and_note_without_isda_are_accepted(legal_case):
    session, user, config, body = legal_case
    credit.enforce_booking(session, user, body)
    body.transaction_format, body.instrument_family, body.ccr_netting_set_id = "EMTN", "Note", None
    config["agreements"] = []
    credit.enforce_booking(session, user, body)


def test_required_csa_cannot_be_bypassed_by_selecting_uncollateralised_set(legal_case):
    session, user, config, body = legal_case
    terms = {"master_agreement_id": 1, "currency": "EUR", "otc_allowed": True, "status": "ACTIVE",
             "effective_date": "2023-01-01", "csa_required": True, "csa_id": 2}
    session.add(TradingRelationship(entity_id=1, counterparty_id=1, reference="FICTIF", updated_by=1, terms_json=json.dumps(terms)))
    session.commit()
    with pytest.raises(HTTPException): credit.enforce_booking(session, user, body)
    config["csas"] = [{"id": 2, "data": {"active": True, "master_agreement_id": 1, "base_currency": "EUR"}}]
    config["netting-sets"][0]["data"]["csa_id"] = 2
    credit.enforce_booking(session, user, body)
    config["csas"][0]["data"]["active"] = False
    with pytest.raises(HTTPException): credit.enforce_booking(session, user, body)


def test_ccr_default_date_and_booking_limit_selection_follow_business_clock(legal_case, monkeypatch, tmp_path):
    session, user, config, body = legal_case
    clock = tmp_path / "clock.json"
    clock.write_text('{"now":"2024-01-02T10:00:00"}')
    monkeypatch.setenv("STRUCTURA_BUSINESS_CLOCK", str(clock))
    assert CalculationRequest().as_of_date == date(2024, 1, 2)
    assert CalculationRequest(as_of_date="2023-01-02").as_of_date == date(2023, 1, 2)
    body.pricing_receipt = None
    config["limits"] = [{"data": {"active": True, "effective_date": "2025-01-01", "expiry_date": None, "action": "HARD_BLOCK"}}]
    credit.enforce_booking(session, user, body)  # future policy must not block
    config["limits"][0]["data"].update(effective_date="2023-01-01", expiry_date="2023-12-31")
    credit.enforce_booking(session, user, body)  # expired policy must not block
    config["limits"][0]["data"]["expiry_date"] = "2024-01-02"
    with pytest.raises(HTTPException) as exc: credit.enforce_booking(session, user, body)
    assert exc.value.status_code == 409


def test_direct_booking_cannot_bypass_pending_otc_agreement(execution_context):
    from backend.app.api import deals
    from backend.app.db.models import Deal, AuditEvent
    from sqlmodel import select
    db, rfq, _ = execution_context
    with Session(db) as session:
        user = session.get(User, 1)
        agreement = credit.save_record(session, user, 1, 'agreements', {
            'agreement_id': 'FICTIF PENDING', 'effective_date': '2023-01-01',
            'governing_law': 'Fictif', 'status': 'PENDING'})
        netting = credit.save_record(session, user, 1, 'netting-sets', {
            'netting_set_id': 'FICTIF', 'master_agreement_id': agreement['id'], 'currency': 'EUR',
            'product_scope': [''], 'our_legal_entity': 'ClientTech', 'counterparty_legal_entity': 'BNP juridique'})
        body = booking_body(rfq).model_copy(update={'rfq_id': None, 'product_id': None,
            'product_terms_version': None, 'transaction_format': 'OTC', 'instrument_family': 'Option',
            'documentation_reference': 'Confirmation FICTIVE', 'ccr_netting_set_id': netting['id']})
        with pytest.raises(HTTPException) as exc: deals._book_deal(body, user, session)
        assert exc.value.status_code == 422 and 'effectif' in exc.value.detail
        assert not session.exec(select(Deal)).all()
        assert session.exec(select(AuditEvent).where(AuditEvent.action == 'BOOKING_REJECTED')).all()
