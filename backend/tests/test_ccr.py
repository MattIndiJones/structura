"""Offline CCR invariants, including the actual PayScript nested engine."""
from copy import deepcopy
from datetime import date

import numpy as np
import pytest
from sqlmodel import SQLModel, Session, create_engine
from sqlalchemy.pool import StaticPool
from fastapi import HTTPException

from backend.app.core.ccr.contracts import CreditProfile, CreditLimit, CSAAgreement, CalculationRequest
from backend.app.core.ccr.exposure import eligible_set, collateral_profile, limit_check, decision, cva
from backend.app.core.ccr.service import evaluate_inputs, save_record, records
from backend.app.db.models import Entity, User, Counterparty, AuditEvent

DAY = date(2026, 9, 28)


def limit(**kw):
    return CreditLimit(metric="pfe95", amount=100, effective_date=DAY, **kw)


@pytest.mark.parametrize("value,status", [(70, "OK"), (80, "WARNING"), (90, "WARNING"), (100, "LIMIT_REACHED"), (110, "BREACH"), (None, "MISSING_DATA")])
def test_limit_boundaries(value, status):
    assert limit_check(limit(), value, "EUR", DAY)["status"] == status


def test_no_limit_never_ok_and_currency_not_assumed():
    assert limit_check(None, 0, "EUR", DAY)["status"] == "NO_LIMIT"
    assert limit_check(limit(), 1, "USD", DAY)["status"] == "MISSING_DATA"
    assert not decision([limit_check(limit(action="HARD_BLOCK"), 101, "EUR", DAY)])["booking_allowed"]
    assert decision([limit_check(limit(action="WARNING"), 101, "EUR", DAY)])["booking_allowed"]
    assert not decision([limit_check(limit(action="HARD_BLOCK"), None, "EUR", DAY)])["booking_allowed"]


def legal_config():
    return {"agreements": [{"id": 1, "data": {"status": "ACTIVE", "close_out_netting_enforceable": True,
              "effective_date": str(DAY), "cross_product_netting_allowed": True}}],
            "netting-sets": [{"id": 1, "data": {"active": True, "enforceable_netting": True,
              "master_agreement_id": 1, "currency": "EUR", "product_scope": ["Option"], "csa_id": None}}]}


def proposed(sens="vente"):
    return {"key": "proposed", "reference": "proposed", "deal_id": None, "product_type": "Option",
            "currency": "EUR", "nominal": 1_000_000, "sens": sens, "netting_set_id": 1,
            "pricing": {"script": 'AT MATURITY\n  PAY MAX(S[1] - 1, 0) "call"',
            "underlyings": [{"name": "S", "ticker": "S", "sigma": .2, "q": 0}],
            "corr_matrix": [[1]], "T": 1, "r": 0, "strike_date": str(DAY)}}


def inputs(trades, config=None):
    req = CalculationRequest(as_of_date=DAY, n_outer=32, n_inner=32, n_dates=3, counterparty_id=1)
    return {"request": req.model_dump(mode="json"), "trades": trades, "configuration": config or {}}


def test_isda_alone_never_nets_and_different_sets_never_net():
    trade = proposed()
    assert eligible_set(trade, {}, {}, DAY) == "trade:proposed"
    cfg = legal_config()
    sets = {1: cfg["netting-sets"][0]["data"]}
    agreements = {1: cfg["agreements"][0]["data"]}
    assert eligible_set(trade, sets, agreements, DAY) == "set:1"
    agreements[1]["close_out_netting_enforceable"] = False
    assert eligible_set(trade, sets, agreements, DAY) == "trade:proposed"
    agreements[1]["close_out_netting_enforceable"] = True
    trade["netting_set_id"] = 2
    assert eligible_set(trade, sets, agreements, DAY) == "trade:proposed"


def test_actual_mc_standalone_and_incremental_hedge_reproducible():
    long = proposed()
    long.update(key="1", deal_id=1, reference="existing")
    short = proposed("achat")
    snapshot = inputs([long, short], legal_config())
    result = evaluate_inputs(snapshot)
    assert result["errors"] == []
    assert result["methodology"] == "NESTED_MONTE_CARLO_GBM"
    assert result["before"]["current_exposure"] > 50_000  # fraction -> cash, not /100 twice
    assert result["after"]["pfe95"] == pytest.approx(0, abs=.001)
    assert result["incremental"]["pfe95"] < 0
    assert result["standalone"]["current_exposure"] == 0
    assert evaluate_inputs(snapshot) == result
    no_netting = evaluate_inputs(inputs([long, short]))
    assert no_netting["after"]["pfe95"] > 0


def test_standalone_without_counterparty_and_new_trade_increases_pfe():
    trade = proposed()
    trade["netting_set_id"] = None
    snapshot = inputs([trade])
    snapshot["request"]["counterparty_id"] = None
    result = evaluate_inputs(snapshot)
    assert result["errors"] == []
    assert result["incremental"]["pfe95"] > 0
    assert all(c["status"] == "NOT_APPLICABLE" for c in result["limits"])


def test_collateral_sign_im_haircut_and_unknown_mpor():
    csa = CSAAgreement(csa_id="CSA", master_agreement_id=1, collateralised=True,
        vm_required=True, im_required=True, mpor_days=10, im_recognised=True)
    position = {"held": 60, "posted": 10, "im_held": 15, "recognised": True,
                "currency": "EUR", "collateral_type": "CASH"}
    margin, details = collateral_profile(np.full((3, 32), 100.), [0, .25, .5], DAY, csa, position)
    assert margin[0, 0] == 65
    assert details["posted"] == 10
    assert np.maximum(100 - margin[0, 0], 0) == 35
    csa.mpor_days = None
    with pytest.raises(ValueError, match="MPOR"):
        collateral_profile(np.ones((3, 32)), [0, .25, .5], DAY, csa, position)


def test_cva_analytic_and_historical_pd_not_labelled_cva():
    p = CreditProfile(recovery=.4, recovery_source="USER_ASSUMPTION", curve_source="MANUAL",
                      pd_measure="RISK_NEUTRAL", pd_curve=[[1, .02]])
    amount, error = cva([0, .5, 1], np.array([100, 100, 100]), 0, p)
    assert amount == pytest.approx(1.2)
    assert error is None
    p.pd_measure = "HISTORICAL"
    assert cva([0, 1], np.array([100, 100]), 0, p)[0] is None


def test_unsupported_model_and_missing_valuation_never_zero_pfe():
    trade = proposed()
    trade["pricing"]["model"] = "heston"
    result = evaluate_inputs(inputs([trade]))
    assert result["status"] == "MISSING_DATA"
    assert result["after"]["pfe95"] is None
    assert result["after"]["current_exposure"] > 0


def test_schema_and_tenant_audit_optimistic_lock():
    engine = create_engine("sqlite://", poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        e = Entity(name="A")
        other = Entity(name="B")
        s.add_all([e, other]); s.flush()
        u = User(username="risk", email="risk@example.test", password_hash="x", role="admin", entity_id=e.id)
        v = User(username="other", email="other@example.test", password_hash="x", role="admin", entity_id=other.id)
        c = Counterparty(name="BANK")
        s.add_all([u, v, c]); s.commit()
        row = save_record(s, u, c.id, "profiles", {})
        assert row["data"]["has_isda"] is None
        assert records(s, v, c.id)["profiles"] == []
        with pytest.raises(HTTPException) as exc:
            save_record(s, u, c.id, "profiles", {}, row["id"], 0)
        assert exc.value.status_code == 409
        from sqlmodel import select
        assert len(s.exec(select(AuditEvent)).all()) == 1


def test_matured_cash_is_exposed_until_payment_then_zero():
    trade = proposed()
    trade["pricing"].update(script='AT MATURITY\n  PAY 1 "capital"', T=.5,
                           r=0, payment_date="2027-04-28")
    result = evaluate_inputs(inputs([trade]))
    assert not result["errors"]
    profile = result["after"]["profile"]
    assert next(p for p in profile if p["t"] >= .5)["ee"] == pytest.approx(1_000_000)
    assert profile[-1]["ee"] == 0


def test_autocall_does_not_erase_unpaid_receivable():
    from backend.app.core.payscript.parser import parse_script
    from backend.app.core.payscript.engine import run_mark_to_future
    compiled = parse_script('AT 0.25\n  PAY 1.05 "recall"\n  STOP\nAT MATURITY\n  PAY 1')
    compiled.events[0].payment_dates = [.4]
    values = run_mark_to_future(compiled, [{"name": "S", "sigma": 0, "q": 0}], [[1]], 0, 1, 100,
        n_outer=32, n_inner=32, mtm_dates=[.25, .35, .5], credit_exposure=True)
    assert values["results"][0]["pvs"] == [105.] * 32
    assert values["results"][1]["pvs"] == [105.] * 32
    assert values["results"][2]["pvs"] == [0.] * 32


def test_separate_sets_and_non_enforceable_agreements_do_not_offset():
    long, short = proposed(), proposed("achat")
    long.update(key="1", deal_id=1)
    short["netting_set_id"] = 2
    cfg = legal_config()
    cfg["netting-sets"].append({"id": 2, "data": deepcopy(cfg["netting-sets"][0]["data"])})
    separated = evaluate_inputs(inputs([long, short], cfg))
    assert separated["after"]["pfe95"] > 0
    cfg["agreements"][0]["data"]["close_out_netting_enforceable"] = False
    short["netting_set_id"] = 1
    unenforceable = evaluate_inputs(inputs([long, short], cfg))
    assert unenforceable["after"]["pfe95"] > 0


def test_market_and_credit_stress_reuses_pricer_without_overwriting_base():
    snapshot = inputs([proposed()])
    snapshot["request"]["hypothetical_profile"] = dict(recovery=.4, recovery_source="USER_ASSUMPTION",
        pd_measure="RISK_NEUTRAL", curve_source="MANUAL", pd_curve=[[2, .04]])
    base = evaluate_inputs(snapshot)
    snapshot["request"].update(stress={"spot_pct": 20, "vol_points": 10}, credit_spread_multiplier=2, wwr="STRESS")
    stressed = evaluate_inputs(snapshot)
    assert stressed["after"]["pfe95"] == base["after"]["pfe95"]
    assert stressed["stress"]["after"]["current_exposure"] > base["after"]["current_exposure"]
    assert stressed["stress"]["after"]["cva"] > base["after"]["cva"]


def test_hard_block_at_real_booking_boundary_keeps_pricing_available():
    from backend.tests.test_rfq import _make_session, _booking_body, _pricing_receipt_for_booking, USER
    from backend.app.api import deals as api
    from backend.app.db.ccr_models import CCRCreditLimit
    from backend.app.core.valuation_context import canonical_json
    from sqlmodel import select
    from backend.app.db.models import Deal
    with _make_session() as session:
        cpty = Counterparty(name="BNP Paribas")
        session.add(cpty); session.flush()
        row = CCRCreditLimit(entity_id=1, counterparty_id=cpty.id, updated_by=1,
            payload_json=canonical_json(CreditLimit(metric="gross_notional", amount=10,
                action="HARD_BLOCK", effective_date=date.today()).model_dump(mode="json")))
        session.add(row); session.commit()
        body = _booking_body()
        body.pricing_receipt = _pricing_receipt_for_booking(body)
        # A real pricing receipt exists despite the limit breach.
        assert body.pricing_receipt["pricing_input"]["script"]
        with pytest.raises(HTTPException) as exc:
            api.book_deal(body, USER, session)
        assert exc.value.status_code == 409
        assert exc.value.detail["code"] == "CCR_CREDIT_BLOCK"
        assert session.exec(select(Deal)).all() == []
        assert any(e.action == "BOOKING_REJECTED" for e in session.exec(select(AuditEvent)).all())


def test_additive_migration_preserves_old_unknown_data(monkeypatch):
    from sqlalchemy import text
    from backend.app.db import database
    engine = create_engine("sqlite://", poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with engine.begin() as conn:
        columns = [r[1] for r in conn.execute(text("PRAGMA table_info(deals)")) if r[1] != "ccr_netting_set_id"]
        conn.execute(text("CREATE TABLE legacy_deals AS SELECT " + ", ".join(columns) + " FROM deals"))
        conn.execute(text("DROP TABLE deals"))
        conn.execute(text("ALTER TABLE legacy_deals RENAME TO deals"))
        conn.execute(text("INSERT INTO counterparties(name, country, active, created_at, updated_at) VALUES ('Legacy', '', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"))
    monkeypatch.setattr(database, "engine", engine)
    database._migrate()
    database._migrate()
    with engine.connect() as conn:
        assert "ccr_netting_set_id" in {r[1] for r in conn.execute(text("PRAGMA table_info(deals)"))}
        assert conn.execute(text("SELECT name FROM counterparties")).scalar() == "Legacy"
        assert conn.execute(text("SELECT COUNT(*) FROM ccr_credit_profiles")).scalar() == 0


def test_settlement_only_horizon_covers_payment_and_credit_stress():
    trade = proposed()
    trade.pop("pricing")
    trade.update(replay={"settlement_claim": True}, mtm_fraction=1.,
                 payment_date="2027-03-28", settlement_amount=1., settlement_market={})
    snapshot = inputs([trade])
    snapshot["request"].update(hypothetical_profile=dict(recovery=.4,
        recovery_source="USER_ASSUMPTION", pd_measure="RISK_NEUTRAL", curve_source="MANUAL", pd_curve=[[2, .04]]),
        credit_spread_multiplier=2)
    result = evaluate_inputs(snapshot)
    assert result["errors"] == []
    assert result["after"]["profile"][-1]["t"] >= .49
    assert result["after"]["profile"][-1]["ee"] == 0
    assert result["after"]["cva"] > 0
    assert result["stress"]["after"]["cva"] > result["after"]["cva"]
    snapshot["request"]["stress"] = {"rate_bp": 100}
    stressed = evaluate_inputs(snapshot)
    assert stressed["stress"]["errors"]
    assert stressed["stress"]["after"]["current_exposure"] is None
    trade["settlement_valuation_market"] = {"funding_spread": 1.}
    credit_adjusted = evaluate_inputs(inputs([trade]))
    assert credit_adjusted["after"]["current_exposure"] is None
    assert credit_adjusted["after"]["pfe95"] is None


def test_legacy_user_cannot_bypass_configured_credit_policy():
    from backend.tests.test_rfq import _make_session, _booking_body
    from backend.app.core.ccr.service import enforce_booking
    from backend.app.db.ccr_models import CCRCreditLimit
    user = User(id=1, username="legacy", email="legacy@example.test", password_hash="x")
    with _make_session() as session:
        cpty = Counterparty(name="BNP Paribas")
        session.add(cpty); session.commit()
        body = _booking_body()
        enforce_booking(session, user, body)
        session.add(CCRCreditLimit(entity_id=1, counterparty_id=cpty.id, updated_by=1, payload_json="{}"))
        session.commit()
        with pytest.raises(HTTPException) as exc:
            enforce_booking(session, user, body)
        assert exc.value.status_code == 409


def test_credit_adjusted_price_does_not_clear_current_exposure_limit():
    trade = proposed()
    trade["pricing"]["funding_spread"] = .01
    snapshot = inputs([trade])
    snapshot["request"]["mode"] = "FAST"
    result = evaluate_inputs(snapshot)
    assert result["after"]["current_exposure"] is None
    assert result["errors"]


def test_posted_collateral_outside_eligible_sets_is_not_silently_omitted():
    cfg = {"collateral": [{"id": 1, "data": {
        "as_of_date": str(DAY), "posted": 100, "netting_set_id": 123}}]}
    result = evaluate_inputs(inputs([proposed()], cfg))
    assert result["after"]["current_exposure"] is None
    assert result["errors"]
