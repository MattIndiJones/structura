"""Synthetic CCR fixture must remain auditable and avoid issued-note netting."""
import json
from datetime import date

from sqlmodel import SQLModel, Session, create_engine, select
from sqlalchemy.pool import StaticPool

from backend.app.core.ccr.contracts import CreditProfile
from backend.app.core.ccr.exposure import cva, eligible_set
from backend.app.db.ccr_models import (CCRCreditProfile, CCRCreditLimit, CCRMasterAgreement,
                                        CCRCSAAgreement, CCRNettingSet, CCRCollateralPosition)
from backend.app.db.models import Counterparty, Entity, User
from backend.scripts.seed_ccr_test_client import AS_OF, NAMES, OTC_ONLY, scenario_data, seed


def test_ccr_test_fixture_covers_credit_and_legal_scenarios_without_note_assignment():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        entity = Entity(name="Demo")
        session.add(entity); session.flush()
        admin = User(username="admin", email="admin@test.invalid", password_hash="x",
                     role="admin", entity_id=entity.id)
        counterparties = {name: Counterparty(name=name) for name in NAMES}
        session.add_all([admin, *counterparties.values()]); session.flush()
        created = seed(session, admin, counterparties, scenario_data())
        assert len(created) == 25
        assert len(session.exec(select(CCRCreditProfile)).all()) == 3
        assert len(session.exec(select(CCRCreditLimit)).all()) == 14
        assert len(session.exec(select(CCRMasterAgreement)).all()) == 2
        assert len(session.exec(select(CCRCSAAgreement)).all()) == 1
        assert len(session.exec(select(CCRNettingSet)).all()) == 3
        positions = session.exec(select(CCRCollateralPosition)).all()
        assert len(positions) == 2
        assert all(json.loads(row.payload_json)["posted"] == 0 for row in positions)

        profiles = {row.counterparty_id: CreditProfile.model_validate(json.loads(row.payload_json))
                    for row in session.exec(select(CCRCreditProfile)).all()}
        expected_ee = [0, 100_000, 150_000]
        for name in ("BNP Paribas", "Société Générale"):
            value, reason = cva([0, 1, 2], expected_ee, .03, profiles[counterparties[name].id])
            assert value is not None and value > 0 and reason is None
        value, reason = cva([0, 1, 2], expected_ee, .03, profiles[counterparties["UBS"].id])
        assert value is None and "risk-neutral" in reason

        agreements = {row.id: json.loads(row.payload_json) for row in session.exec(select(CCRMasterAgreement)).all()}
        sets = {row.id: json.loads(row.payload_json) for row in session.exec(select(CCRNettingSet)).all()}
        bnp_set = next(row for row in session.exec(select(CCRNettingSet)).all()
                       if row.counterparty_id == counterparties["BNP Paribas"].id)
        assert eligible_set(dict(key="new-otc", netting_set_id=bnp_set.id, currency="EUR",
                                 product_type=OTC_ONLY), sets, agreements, date(2026, 9, 28)) == f"set:{bnp_set.id}"
        assert eligible_set(dict(key="issued-note", netting_set_id=bnp_set.id, currency="EUR",
                                 product_type="Autocall Athena"), sets, agreements, AS_OF) == "trade:issued-note"
