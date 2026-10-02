#!/usr/bin/env python3
"""Seed explicit, synthetic CCR scenarios for the existing `test` user's UAT deals.

Run from the repository root. The default is read-only; --apply writes audited
configuration records only when the three counterparties have no CCR setup.
Existing booked notes are never assigned to an ISDA netting set.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path

from sqlmodel import Session, select

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.app.core.ccr.contracts import SCHEMAS
from backend.app.core.ccr.service import records, save_record
from backend.app.db.database import engine
from backend.app.db.models import Counterparty, Deal, User


AS_OF = date(2026, 9, 29)
EFFECTIVE = date(2026, 9, 1)
NAMES = ("UBS", "BNP Paribas", "Société Générale")
OTC_ONLY = "UAT_CCR_OTC_ONLY"


def scenario_data():
    """Sources and legal statuses here are fictitious UAT assumptions, never facts."""
    return {
        "Société Générale": {
            "scenario": "issuer note, no ISDA/CSA, complete risk-neutral PD and CVA",
            "profile": dict(legal_name="Société Générale — UAT SIMULATION", short_name="SG UAT",
                counterparty_type="Bank", currency="EUR", recovery=.40,
                recovery_source="USER_ASSUMPTION", curve_source="MANUAL", pd_measure="RISK_NEUTRAL",
                pd_curve=[[1,.01],[2,.02],[3,.03],[5,.05],[7,.07],[10,.10]],
                has_isda=False, has_csa=False),
            "limits": [("gross_notional", 1_000_000, "INFORMATION_ONLY"),
                       ("current_exposure", 1_000_000, "INFORMATION_ONLY"),
                       ("pfe95", 1_200_000, "INFORMATION_ONLY"),
                       ("cva", 50_000, "INFORMATION_ONLY")],
        },
        "BNP Paribas": {
            "scenario": "risk-neutral spread/CVA, simulated OTC ISDA and VM collateral",
            "profile": dict(legal_name="BNP Paribas — UAT SIMULATION", short_name="BNP UAT",
                counterparty_type="Bank", currency="EUR", recovery=.40,
                recovery_source="USER_ASSUMPTION", curve_source="MANUAL", pd_measure="RISK_NEUTRAL",
                spread_curve=[[1,.006],[2,.008],[3,.010],[5,.012],[7,.014],[10,.016]],
                has_isda=True, has_csa=True),
            "limits": [("gross_notional", 5_000_000, "INFORMATION_ONLY"),
                       ("current_exposure", 3_000_000, "INFORMATION_ONLY"),
                       ("pfe95", 4_000_000, "INFORMATION_ONLY"),
                       ("pfe99", 5_000_000, "INFORMATION_ONLY"),
                       ("cva", 100_000, "INFORMATION_ONLY")],
        },
        "UBS": {
            "scenario": "historical PD: PFE available, market CVA intentionally unavailable; legal pending",
            "profile": dict(legal_name="UBS — UAT SIMULATION", short_name="UBS UAT",
                counterparty_type="Bank", currency="EUR", recovery=.25,
                recovery_source="USER_ASSUMPTION", curve_source="MANUAL", pd_measure="HISTORICAL",
                pd_curve=[[1,.005],[2,.011],[3,.018],[5,.035],[7,.052],[10,.08]],
                has_isda=None, has_csa=None),
            "limits": [("gross_notional", 3_000_000, "INFORMATION_ONLY"),
                       ("current_exposure", 2_000_000, "INFORMATION_ONLY"),
                       ("pfe95", 2_500_000, "INFORMATION_ONLY"),
                       ("cva", 20_000, "INFORMATION_ONLY"),
                       ("stressed_exposure", 3_000_000, "INFORMATION_ONLY")],
        },
    }


def plan(session: Session):
    admin = session.exec(select(User).where(User.username == "admin")).one()
    test = session.exec(select(User).where(User.username == "test")).one()
    if admin.role != "admin" or not test.entity_id or admin.entity_id != test.entity_id:
        raise RuntimeError("Administrateur et utilisateur test doivent appartenir à la même entité")
    counterparties = {row.name: row for row in session.exec(select(Counterparty)).all() if row.name in NAMES}
    if set(counterparties) != set(NAMES):
        raise RuntimeError("Les trois contreparties UAT attendues sont introuvables")
    deals = session.exec(select(Deal).where(Deal.counterparty_id.in_(
        [row.id for row in counterparties.values()]))).all()
    if not deals or any(d.user_id != test.id or d.entity_id != test.entity_id or d.uat_batch_id is None for d in deals):
        raise RuntimeError("Périmètre refusé : deal non UAT ou non détenu par l'utilisateur test")
    if any(d.ccr_netting_set_id is not None for d in deals):
        raise RuntimeError("Périmètre refusé : un deal a déjà un rattachement juridique")
    existing = {name: records(session, admin, cpty.id) for name, cpty in counterparties.items()}
    if any(rows for config in existing.values() for rows in config.values()):
        raise RuntimeError("Périmètre refusé : paramétrage CCR déjà présent ; aucune donnée n'est écrasée")
    fixture = scenario_data()
    for scenario in fixture.values():
        SCHEMAS["profiles"].model_validate(scenario["profile"])
        for metric, amount, action in scenario["limits"]:
            SCHEMAS["limits"].model_validate(dict(metric=metric, amount=amount,
                currency="EUR", action=action, effective_date=EFFECTIVE))
    return admin, test, counterparties, fixture, deals


def backup_database(path: Path) -> Path:
    target = path.with_name(f"{path.stem}.ccr-preseed-{datetime.now():%Y%m%d-%H%M%S}.db")
    with sqlite3.connect(path) as source, sqlite3.connect(target) as destination:
        source.backup(destination)
    return target


def seed(session: Session, admin: User, counterparties: dict, fixture: dict):
    created = []

    def add(name, kind, payload):
        row = save_record(session, admin, counterparties[name].id, kind, payload)
        created.append(dict(counterparty=name, kind=kind, id=row["id"]))
        return row["id"]

    for name in NAMES:
        scenario = fixture[name]
        add(name, "profiles", scenario["profile"])
        for metric, amount, action in scenario["limits"]:
            add(name, "limits", dict(metric=metric, amount=amount, currency="EUR",
                action=action, effective_date=EFFECTIVE, warning_threshold=.8, hard_threshold=1))

    bnp = "BNP Paribas"
    agreement = add(bnp, "agreements", dict(agreement_id="UAT-SIM-BNP-ISDA-2026",
        agreement_version="FICTIF-UAT-V1", effective_date=EFFECTIVE,
        governing_law="English law (hypothèse UAT)", status="ACTIVE",
        legal_opinion_available=None, close_out_netting_enforceable=True,
        cross_product_netting_allowed=False,
        notes="Simulation UAT uniquement. Aucune documentation ni opinion juridique réelle vérifiée. "
              "Ne pas rattacher les notes émises à ce set OTC."))
    csa = add(bnp, "csas", dict(csa_id="UAT-SIM-BNP-CSA-VM", master_agreement_id=agreement,
        bilateral=True, collateralised=True, vm_required=True, vm_frequency_days=1,
        threshold_counterparty=100_000, threshold_our_side=100_000, mta=10_000,
        independent_amount=0, im_required=True, im_model="FIXED", im_amount=50_000,
        segregated=True, im_recognised=True, base_currency="EUR", eligible_collateral=["CASH"],
        collateral_haircut=.02, settlement_lag_days=1, mpor_days=10, active=True))
    collateralised = add(bnp, "netting-sets", dict(netting_set_id="UAT-SIM-BNP-OTC-VM",
        master_agreement_id=agreement, csa_id=csa, currency="EUR", product_scope=[OTC_ONLY],
        our_legal_entity="Demo (simulation UAT)",
        counterparty_legal_entity="BNP Paribas (simulation UAT)",
        active=True, enforceable_netting=True))
    add(bnp, "netting-sets", dict(netting_set_id="UAT-SIM-BNP-OTC-UNCOLL",
        master_agreement_id=agreement, currency="EUR", product_scope=[OTC_ONLY],
        our_legal_entity="Demo (simulation UAT)",
        counterparty_legal_entity="BNP Paribas (simulation UAT)",
        active=True, enforceable_netting=True))
    for day in (date(2026, 9, 28), AS_OF):
        add(bnp, "collateral", dict(netting_set_id=collateralised, as_of_date=day,
            currency="EUR", collateral_type="CASH", held=150_000, posted=0,
            im_held=50_000, recognised=True, source="UAT_SIMULATION: position fictive, non réconciliée"))

    ubs = "UBS"
    pending = add(ubs, "agreements", dict(agreement_id="UAT-SIM-UBS-PENDING",
        agreement_version="FICTIF-UAT-V1", effective_date=EFFECTIVE,
        governing_law="Non vérifié — simulation UAT", status="PENDING",
        legal_opinion_available=None, close_out_netting_enforceable=None,
        cross_product_netting_allowed=None,
        notes="Simulation UAT : documentation juridique non confirmée ; netting non reconnu."))
    add(ubs, "netting-sets", dict(netting_set_id="UAT-SIM-UBS-INELIGIBLE",
        master_agreement_id=pending, currency="EUR", product_scope=[OTC_ONLY],
        our_legal_entity="Demo (simulation UAT)",
        counterparty_legal_entity="UBS (simulation UAT)",
        active=False, enforceable_netting=None))
    return created


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Enregistre les hypothèses UAT après sauvegarde SQLite")
    args = parser.parse_args()
    db_path = Path(str(engine.url.database)).resolve()
    expected = (Path(__file__).resolve().parents[1] / "data" / "structura.db").resolve()
    if engine.url.drivername != "sqlite" or db_path != expected:
        raise SystemExit(f"Base inattendue : {engine.url}")
    with Session(engine) as session:
        admin, test, counterparties, fixture, deals = plan(session)
        report = dict(mode="apply" if args.apply else "dry-run", user=test.username,
            entity_id=test.entity_id, deal_count=len(deals),
            counterparties=[dict(id=counterparties[n].id, name=n, scenario=fixture[n]["scenario"])
                            for n in NAMES],
            note="Données synthétiques UAT partagées au niveau de l'entité ; aucun deal n'est affecté à un netting set")
        if args.apply:
            report["backup"] = str(backup_database(db_path))
            report["created"] = seed(session, admin, counterparties, fixture)
            report["created_count"] = len(report["created"])
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
