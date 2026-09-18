#!/usr/bin/env python3
"""Create a local UAT batch through the production Product workflow.

This CLI is intentionally a thin adapter over Administration's generator.
It must not maintain its own RFQ, fixing or lifecycle fixtures: doing so used
to leave the command on a retired manual-validation workflow while the
application had already moved to automatic provider fixings.

Usage from the repository root::

    .venv\Scripts\python.exe backend\scripts\seed_workflow_uat.py --reset-test-db
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlmodel import Session, select

from backend.app.api import deals as deals_api
from backend.app.api import products as products_api
from backend.app.api import rfq as rfq_api
from backend.app.db.database import engine, init_db
from backend.app.db.models import Deal, ProductRecord, RfqRequest, User
from backend.app.services.uat_generation import (
    LIFECYCLE_PROFILE_KEYS,
    UatGenerationRequest,
    configure_uat_workflows,
    generate_batch,
)


configure_uat_workflows(deals_api, rfq_api, products_api)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Cree un lot RFQ -> Product interne -> Pricer -> booking -> Risk.")
    parser.add_argument(
        "--reset-test-db",
        action="store_true",
        help="Supprime et recree explicitement la base SQLite locale de test.",
    )
    parser.add_argument("--count", type=int, default=8, choices=range(1, 101))
    parser.add_argument(
        "--lifecycle-profile",
        choices=(*LIFECYCLE_PROFILE_KEYS, "COMPLETE_MIX"),
        default="COMPLETE_MIX",
    )
    parser.add_argument(
        "--product-calculations", type=int, default=3, choices=range(1, 6),
        help="Nombre de pricings conserves avec leur marche par Product.",
    )
    parser.add_argument(
        "--mtm-history", type=int, default=3, choices=range(0, 6),
        help="Nombre maximal de dates de MTM conservees par deal eligible.",
    )
    parser.add_argument(
        "--without-greeks", action="store_true",
        help="Ne calcule pas les Greeks destines a Risk.",
    )
    return parser.parse_args()


def _reset_local_test_schema() -> None:
    expected = (
        Path(__file__).resolve().parents[1] / "data" / "structura.db"
    ).resolve()
    actual = Path(str(engine.url.database)).resolve()
    if engine.url.drivername != "sqlite" or actual != expected:
        raise SystemExit(
            f"Reset refuse : moteur inattendu ({engine.url}) ; cible autorisee : {expected}")
    raw = engine.raw_connection()
    try:
        cursor = raw.cursor()
        cursor.execute("PRAGMA foreign_keys=OFF")
        tables = [row[0] for row in cursor.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()]
        for table_name in tables:
            quoted = table_name.replace('"', '""')
            cursor.execute(f'DROP TABLE IF EXISTS "{quoted}"')
        raw.commit()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
    finally:
        raw.close()


def main() -> None:
    args = _parse_args()
    if args.reset_test_db:
        _reset_local_test_schema()
    init_db()
    with Session(engine) as session:
        if any((
            session.exec(select(ProductRecord)).first(),
            session.exec(select(RfqRequest)).first(),
            session.exec(select(Deal)).first(),
        )):
            raise SystemExit(
                "Refus : la base contient deja des Products, RFQ ou deals. "
                "Utilisez uniquement ce script apres un reset explicite de la base de test.")
        admin = session.exec(select(User).where(User.username == "admin")).one()
        target = session.exec(select(User).where(User.username == "test")).one()
        batch = generate_batch(
            UatGenerationRequest(
                target_user_id=target.id,
                mode="FULL_CHAIN",
                count=args.count,
                label="Lot CLI partagé avec le générateur Admin",
                lifecycle_profile=args.lifecycle_profile,
                product_calculations=args.product_calculations,
                mtm_history_count=args.mtm_history,
                compute_greeks=not args.without_greeks,
            ),
            admin,
            session,
        )
        print(json.dumps(batch, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
