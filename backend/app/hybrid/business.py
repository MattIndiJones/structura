"""Transactional managed bootstrap. Later starts observe drift without restoring grants."""
import json
from datetime import datetime

import bcrypt
from sqlmodel import Field, Session, SQLModel, select
from sqlalchemy import text

from .config import credentials
from ..core.audit import record_audit_event
from ..db.models import Entity, User, RfqDesk, RfqDeskMembership, RfqBankPublicationPolicy, RfqInstallation


class HybridBootstrap(SQLModel, table=True):
    __tablename__ = "hybrid_bootstrap"
    id: int = Field(default=1, primary_key=True)
    installation_id: str = Field(unique=True)
    organization_id: str = Field(unique=True)
    entity_id: int = Field(foreign_key="entities.id")
    seed_version: int = 1
    baseline_json: str


class DevelopmentRedemption(SQLModel, table=True):
    __tablename__ = "hybrid_development_redemptions"
    ticket_id: str = Field(primary_key=True)
    user_id: int = Field(foreign_key="users.id")
    origin_json: str
    received_at: datetime = Field(default_factory=datetime.utcnow)


ROLES = {"superuser": "organization_admin", "front": "user", "operations": "ops_maker", "controller": "checker"}
ALL_RIGHTS = {"read", "prepare", "price", "select", "solicit", "organize", "book", "validate_quote", "publish_quote"}


def preflight(engine, config):
    """Refuse foreign/occupied databases before any migration or business update."""
    # Both identity tables are created by init_db. Register the Admin schema
    # before checking a fresh process's metadata, even for a business service.
    from .admin_workbench import AdminWorkbenchIdentity
    if config.kind != "organization":
        raise RuntimeError("Un service central ne doit pas initialiser le schéma métier.")
    with engine.connect() as connection:
        tables = {row[0] for row in connection.execute(text(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT GLOB 'sqlite_*'"))}
        if tables - (set(SQLModel.metadata.tables) | {"app_migrations"}):
            raise RuntimeError("Schéma préexistant non identifié ; aucune mise à jour appliquée.")
        if AdminWorkbenchIdentity.__tablename__ in tables and connection.execute(text(
                "SELECT 1 FROM admin_workbench_identity LIMIT 1")).first():
            raise RuntimeError("Identités métier et Admin incompatibles ; aucune mise à jour appliquée.")
        marker = connection.execute(text("SELECT installation_id, organization_id FROM hybrid_bootstrap WHERE id=1")).first() \
            if "hybrid_bootstrap" in tables else None
        if marker:
            if marker[0] != str(config.installation_id) or marker[1] != str(config.organization_id):
                raise RuntimeError("La base appartient à une autre installation ; aucune mise à jour appliquée.")
            organization = connection.execute(text(
                "SELECT entities.name FROM entities JOIN hybrid_bootstrap ON entities.id=hybrid_bootstrap.entity_id WHERE hybrid_bootstrap.id=1")).first()
            if not organization or organization[0] != config.name:
                raise RuntimeError("Nom canonique divergent du manifeste ; provisionnement explicite requis avant toute migration.")
            return
        # An interrupted first boot may have created empty tables and schema
        # markers. It cannot have committed private rows without its identity.
        for table in tables - {"app_migrations"}:
            identifier = '"' + table.replace('"', '""') + '"'
            if connection.execute(text(f"SELECT 1 FROM {identifier} LIMIT 1")).first():
                raise RuntimeError("Base préexistante sans bootstrap identifié ; aucune mise à jour appliquée.")


def seed(engine, config):
    if config.kind != "organization":
        raise RuntimeError("Le bootstrap métier ne s'applique pas au service central.")
    passwords = credentials(config)
    with Session(engine) as session:
        marker = session.get(HybridBootstrap, 1)
        if marker:
            if marker.installation_id != str(config.installation_id) or marker.organization_id != str(config.organization_id):
                raise RuntimeError("Cette base appartient à une autre installation ou organisation.")
            return inspect(session, marker)
        if session.exec(select(Entity)).first() or session.exec(select(User)).first():
            raise RuntimeError("Base préexistante sans bootstrap identifié ; aucune reprise ou remise à zéro implicite.")
        organization = Entity(name=config.name)
        session.add(organization)
        session.flush()
        users = {}
        for username, role in ROLES.items():
            user = User(username=username, email=f"{username}@{config.key}.example.test",
                password_hash=bcrypt.hashpw(passwords[username].encode(), bcrypt.gensalt()).decode(),
                role=role, entity_id=organization.id)
            session.add(user)
            session.flush()
            users[username] = user
        responding = "respond_rfq" in config.capabilities
        desks, baseline = {}, {"users": {}, "memberships": [], "policies": [], "entity_name": config.name}
        for name in ("Pricing" if responding else "Sales", "Opérations"):
            desk = RfqDesk(entity_id=organization.id, name=name)
            session.add(desk)
            session.flush()
            desks[name] = desk
            for username, user in users.items():
                if username == "superuser":
                    rights = ALL_RIGHTS
                elif username == "operations":
                    rights = {"read", "book"}
                elif username == "controller":
                    rights = {"read", "validate_quote", "publish_quote"} if responding and name == "Pricing" else {"read"}
                else:
                    rights = {"read"} if name == "Opérations" else {"read", "prepare", "price", "select", "solicit", "organize"}
                    if responding and name == "Pricing":
                        rights |= {"validate_quote", "publish_quote"}
                membership = RfqDeskMembership(desk_id=desk.id, user_id=user.id, rights_json=json.dumps(sorted(rights)))
                session.add(membership)
                baseline["memberships"].append({"desk_id": desk.id, "user_id": user.id, "rights": sorted(rights)})
        if responding:
            policy = RfqBankPublicationPolicy(desk_id=desks["Pricing"].id, second_validation_required=False,
                max_calculation_age_minutes=60, updated_by=users["superuser"].id)
            session.add(policy)
            baseline["policies"].append({"desk_id": policy.desk_id, "second_validation_required": False,
                                         "max_calculation_age_minutes": 60})
        for name, user in users.items():
            baseline["users"][name] = {"id": user.id, "role": user.role, "entity_id": user.entity_id}
        transport = session.get(RfqInstallation, 1)
        if transport and transport.installation_id != str(config.installation_id):
            raise RuntimeError("Identité de transport incompatible.")
        if not transport:
            session.add(RfqInstallation(installation_id=str(config.installation_id)))
        marker = HybridBootstrap(installation_id=str(config.installation_id), organization_id=str(config.organization_id),
            entity_id=organization.id, baseline_json=json.dumps(baseline, ensure_ascii=False, sort_keys=True))
        session.add(marker)
        record_audit_event(session, action="HYBRID_BOOTSTRAP", object_type="INSTALLATION", object_id=1,
            actor_user_id=None, actor_type="SYSTEM", result="SUCCESS",
            after={"installation_id": marker.installation_id, "organization_id": marker.organization_id,
                   "accounts": 4, "desks": 2, "seed_version": 1})
        session.commit()
        for user in users.values():
            (config.data_dir / "studies" / str(user.id)).mkdir(parents=True, exist_ok=True)
        return inspect(session, marker)


def inspect(session, marker):
    baseline, drift = json.loads(marker.baseline_json), []
    entity = session.get(Entity, marker.entity_id)
    if not entity:
        raise RuntimeError("Organisation locale absente.")
    if entity.name != baseline["entity_name"]:
        drift.append("organization.name")
    transport = session.get(RfqInstallation, 1)
    if not transport or transport.installation_id != marker.installation_id:
        raise RuntimeError("Identité de transport absente ou divergente ; aucune réparation implicite.")
    for username, expected in baseline["users"].items():
        user = session.get(User, expected["id"])
        if not user or user.username != username or user.role != expected["role"] or user.entity_id != marker.entity_id or not user.is_active:
            drift.append(f"account.{username}")
    for expected in baseline["memberships"]:
        membership = session.exec(select(RfqDeskMembership).where(RfqDeskMembership.desk_id == expected["desk_id"],
            RfqDeskMembership.user_id == expected["user_id"])).first()
        desk = session.get(RfqDesk, expected["desk_id"])
        if not desk or not desk.active or not membership or not membership.active or membership.expires_at or sorted(json.loads(membership.rights_json)) != expected["rights"]:
            drift.append(f"membership.{expected['desk_id']}.{expected['user_id']}")
    for expected in baseline["policies"]:
        policy = session.get(RfqBankPublicationPolicy, expected["desk_id"])
        if not policy or any(getattr(policy, field) != expected[field] for field in ("second_validation_required", "max_calculation_age_minutes")):
            drift.append(f"publication_policy.{expected['desk_id']}")
    return {"installation_id": marker.installation_id, "organization_id": marker.organization_id,
            "accounts": len(session.exec(select(User)).all()), "desks": len(session.exec(select(RfqDesk)).all()),
            "seed_version": marker.seed_version, "configuration_drift": drift}
