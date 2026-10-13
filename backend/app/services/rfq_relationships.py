"""Bilateral RFQ permissions, independent of private pricing and booking terms."""
from __future__ import annotations

import json
import math
import re
from datetime import date, datetime
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import update
from sqlmodel import Session, select

from ..core.audit import record_audit_event
from ..core.payoff_families import canonical_payoff_family
from ..db.models import (
    Counterparty, Entity, RfqDesk, RfqRelationship, RfqRelationshipSide, RfqRequest, User,
)
from ..db.trading_models import TradingRelationship
from ..runtime import business_today


class SharedContact(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=150)
    email: str = Field(default="", max_length=254)

    @model_validator(mode="after")
    def clean(self):
        self.name, self.email = self.name.strip(), self.email.strip()
        if not self.name or (self.email and not re.fullmatch(r"[^@\s]+@[^@\s]+", self.email)):
            raise ValueError("Contact partagé invalide")
        return self


class RelationshipTerms(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    formats: list[str] = Field(min_length=1, max_length=30)
    instruments: list[str] = Field(min_length=1, max_length=30)
    payoff_families: list[str] = Field(min_length=1, max_length=40)
    currencies: list[str] = Field(min_length=1, max_length=30)
    min_notional: float | None = Field(default=None, gt=0)
    max_notional: float | None = Field(default=None, gt=0)
    effective_date: date
    expiry_date: date | None = None
    solicitation_allowed: bool = False
    indicative_allowed: bool = True
    to_trade_allowed: bool = False
    treatment_allowed: bool = False
    documentation_reference: str = Field(default="", max_length=1000)
    policy: Literal["RFQ_V1"] = "RFQ_V1"

    @model_validator(mode="after")
    def perimeter(self):
        for field in ("formats", "instruments", "currencies"):
            values = getattr(self, field)
            cleaned = sorted({item.strip().upper() for item in values})
            if any(not item or len(item) > 80 or item in {"*", "ALL", "TOUT"} for item in cleaned):
                raise ValueError("Le périmètre doit contenir des valeurs explicites")
            setattr(self, field, cleaned)
        if any(len(ccy) != 3 or not ccy.isalpha() for ccy in self.currencies):
            raise ValueError("Les devises doivent avoir un code de trois lettres")
        families = [canonical_payoff_family(item) for item in self.payoff_families]
        if any(item is None for item in families):
            raise ValueError("Famille de payoff hors catalogue")
        self.payoff_families = sorted(set(families))
        if self.expiry_date and self.expiry_date < self.effective_date:
            raise ValueError("L'expiration précède la date d'effet")
        if self.min_notional and self.max_notional and self.min_notional > self.max_notional:
            raise ValueError("Le nominal minimum dépasse le maximum")
        self.documentation_reference = self.documentation_reference.strip()
        if self.treatment_allowed and (not self.to_trade_allowed or not self.documentation_reference):
            raise ValueError("Le traitement exige le périmètre to trade et une documentation")
        return self


class RelationshipConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid")
    receiver_desk_id: int
    terms: RelationshipTerms
    counterparty_id: int
    trading_relationship_id: int | None = None
    contacts: list[SharedContact] = Field(default_factory=list, max_length=20)
    reason: str = Field(min_length=3, max_length=500)


class RelationshipCreate(RelationshipConfiguration):
    requester_entity_id: int | None = None
    partner_entity_id: int
    reference: str = Field(min_length=3, max_length=100)


class RelationshipUpdate(RelationshipConfiguration):
    expected_version: int = Field(gt=0)


class RelationshipDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(gt=0)
    reason: str = Field(min_length=3, max_length=500)


class RelationshipSuspension(RelationshipDecision):
    suspended: bool


def organization_admin(user: User) -> int:
    if user.role != "admin" or not user.is_active or user.entity_id is None:
        raise HTTPException(403, "Un administrateur rattaché à l'organisation est requis")
    return user.entity_id


def sides(session: Session, row: RfqRelationship) -> list[RfqRelationshipSide]:
    return list(session.exec(select(RfqRelationshipSide).where(
        RfqRelationshipSide.relationship_id == row.id)).all())


def require_relation(session: Session, relation_id: int, entity_id: int) -> RfqRelationship:
    row = session.get(RfqRelationship, relation_id)
    if not row or entity_id not in {row.requester_entity_id, row.partner_entity_id}:
        raise HTTPException(404, "Relation RFQ introuvable")
    return row


def status(session: Session, row: RfqRelationship) -> str:
    parties = sides(session, row)
    if any(side.suspended for side in parties):
        return "SUSPENDED"
    terms = RelationshipTerms.model_validate_json(row.terms_json)
    today = business_today()
    if terms.expiry_date and terms.expiry_date < today:
        return "EXPIRED"
    if len(parties) != 2 or any(side.recognized_version != row.version for side in parties):
        return "PENDING"
    if terms.effective_date > today:
        return "NOT_STARTED"
    return "ACTIVE"


def public_row(session: Session, row: RfqRelationship) -> dict:
    desk = session.get(RfqDesk, row.receiver_desk_id)
    organizations = {e.id: e.name for e in session.exec(select(Entity).where(
        Entity.id.in_([row.requester_entity_id, row.partner_entity_id]))).all()}
    recognitions = []
    for side in sides(session, row):
        cpty = session.get(Counterparty, side.counterparty_id) if side.counterparty_id else None
        recognitions.append({"entity_id": side.entity_id,
            "organization": organizations.get(side.entity_id),
            "recognized": side.recognized_version == row.version,
            "suspended": side.suspended, "legal_counterparty": cpty.name if cpty else None,
            "contacts": json.loads(side.contacts_json)})
    return {"id": row.id, "reference": row.reference, "version": row.version,
            "requester_entity_id": row.requester_entity_id,
            "partner_entity_id": row.partner_entity_id,
            "requester_name": organizations.get(row.requester_entity_id),
            "partner_name": organizations.get(row.partner_entity_id),
            "receiver_desk_id": row.receiver_desk_id,
            "receiver_desk_name": desk.name if desk else None,
            "terms": json.loads(row.terms_json), "status": status(session, row),
            "recognitions": recognitions}


def row_for(session: Session, row: RfqRelationship, entity_id: int) -> dict:
    local = session.get(RfqRelationshipSide, (row.id, entity_id))
    return {**public_row(session, row), "local": {
        "counterparty_id": local.counterparty_id, "trading_relationship_id": local.trading_relationship_id,
        "contacts": json.loads(local.contacts_json), "suspended": local.suspended,
        "recognized": local.recognized_version == row.version,
    }}


def _validate_mapping(session: Session, entity_id: int, counterparty_id: int | None,
                      trading_id: int | None, terms: RelationshipTerms) -> None:
    cpty = session.get(Counterparty, counterparty_id) if counterparty_id else None
    if not cpty or not cpty.active:
        raise HTTPException(422, "Rapprochez explicitement une contrepartie juridique active")
    if terms.treatment_allowed and trading_id is None:
        raise HTTPException(422, "Le traitement exige un accord de booking local explicite")
    if trading_id is not None:
        trading = session.get(TradingRelationship, trading_id)
        if not trading or trading.entity_id != entity_id or trading.counterparty_id != counterparty_id:
            raise HTTPException(422, "L'accord de booking n'appartient pas à ce périmètre local")
        booking = json.loads(trading.terms_json)
        if terms.treatment_allowed and (booking.get("status") != "ACTIVE"
                or booking.get("currency") not in terms.currencies
                or not booking.get("documentation_reference")):
            raise HTTPException(422, "L'accord de booking doit être actif, documenté et dans les devises autorisées")
        if terms.treatment_allowed and (
                (booking.get("effective_date") and date.fromisoformat(booking["effective_date"]) > terms.effective_date)
                or (booking.get("expiry_date") and date.fromisoformat(booking["expiry_date"]) < terms.effective_date)):
            raise HTTPException(422, "L'accord de booking doit être en vigueur à la date d'effet RFQ")


def _validate_config(session: Session, partner_id: int, entity_id: int,
                     body: RelationshipConfiguration) -> None:
    desk = session.get(RfqDesk, body.receiver_desk_id)
    if not desk or not desk.active or desk.entity_id != partner_id:
        raise HTTPException(422, "Le desk destinataire doit appartenir à l'organisation partenaire")
    _validate_mapping(session, entity_id, body.counterparty_id, body.trading_relationship_id, body.terms)
    if len(body.reason.strip()) < 3:
        raise HTTPException(422, "Le motif de changement est requis")


def _lock_version(session: Session, row: RfqRelationship, version: int, *, increment=False):
    result = session.execute(update(RfqRelationship).where(
        RfqRelationship.id == row.id, RfqRelationship.version == version,
    ).values(updated_at=datetime.utcnow(), version=version + (1 if increment else 0))
      .execution_options(synchronize_session=False))
    if result.rowcount != 1:
        raise HTTPException(409, "La relation a changé ; rechargez la version courante")
    session.expire_all()


def _audit(session: Session, row: RfqRelationship, user: User, action: str, reason: str, before=None):
    record_audit_event(session, action=action, object_type="RFQ_RELATIONSHIP", object_id=row.id,
                       actor_user_id=user.id, result="SUCCESS", before=before,
                       after=public_row(session, row), reason=reason.strip())


def create_relation(session: Session, user: User, body: RelationshipCreate) -> dict:
    entity_id = organization_admin(user)
    requester_id = body.requester_entity_id or entity_id
    if requester_id == body.partner_entity_id or entity_id not in {requester_id, body.partner_entity_id} \
            or not session.get(Entity, body.partner_entity_id) or not session.get(Entity, requester_id):
        raise HTTPException(422, "Choisissez une autre organisation partenaire")
    _validate_config(session, body.partner_entity_id, entity_id, body)
    reference = body.reference.strip()
    if len(reference) < 3:
        raise HTTPException(422, "La référence de relation est requise")
    if session.exec(select(RfqRelationship).where(
            RfqRelationship.requester_entity_id == requester_id,
            RfqRelationship.reference == reference)).first():
        raise HTTPException(409, "Cette référence de relation existe déjà")
    row = RfqRelationship(requester_entity_id=requester_id, partner_entity_id=body.partner_entity_id,
        receiver_desk_id=body.receiver_desk_id, reference=reference,
        terms_json=body.terms.model_dump_json(), created_by=user.id)
    session.add(row)
    session.flush()
    for organization in (requester_id, body.partner_entity_id):
        session.add(RfqRelationshipSide(relationship_id=row.id, entity_id=organization,
            updated_by=user.id, counterparty_id=body.counterparty_id if organization == entity_id else None,
            trading_relationship_id=body.trading_relationship_id if organization == entity_id else None,
            contacts_json=json.dumps([c.model_dump() for c in body.contacts]) if organization == entity_id else "[]"))
    session.flush()
    _audit(session, row, user, "RFQ_RELATIONSHIP_CREATED", body.reason)
    session.commit()
    return row_for(session, row, entity_id)


def update_relation(session: Session, relation_id: int, user: User, body: RelationshipUpdate) -> dict:
    entity_id = organization_admin(user)
    row = require_relation(session, relation_id, entity_id)
    _validate_config(session, row.partner_entity_id, entity_id, body)
    before = public_row(session, row)
    _lock_version(session, row, body.expected_version, increment=True)
    row.receiver_desk_id, row.terms_json = body.receiver_desk_id, body.terms.model_dump_json()
    session.add(row)
    for side in sides(session, row):
        side.recognized_version = None
        if side.entity_id == entity_id:
            side.counterparty_id, side.trading_relationship_id = body.counterparty_id, body.trading_relationship_id
            side.contacts_json = json.dumps([c.model_dump() for c in body.contacts])
            side.updated_by, side.updated_at = user.id, datetime.utcnow()
        session.add(side)
    session.flush()
    _audit(session, row, user, "RFQ_RELATIONSHIP_UPDATED", body.reason, before)
    session.commit()
    return row_for(session, row, entity_id)


def recognize_relation(session: Session, relation_id: int, user: User, body: RelationshipDecision) -> dict:
    entity_id = organization_admin(user)
    row = require_relation(session, relation_id, entity_id)
    local = session.get(RfqRelationshipSide, (row.id, entity_id))
    terms = RelationshipTerms.model_validate_json(row.terms_json)
    _validate_mapping(session, entity_id, local.counterparty_id, local.trading_relationship_id, terms)
    if local.suspended or (terms.expiry_date and terms.expiry_date < business_today()):
        raise HTTPException(409, "Une relation suspendue ou expirée ne peut pas être reconnue")
    if len(body.reason.strip()) < 3:
        raise HTTPException(422, "Le motif de reconnaissance est requis")
    before = public_row(session, row)
    _lock_version(session, row, body.expected_version)
    local.recognized_version = row.version
    local.updated_by, local.updated_at = user.id, datetime.utcnow()
    session.add(local)
    session.flush()
    _audit(session, row, user, "RFQ_RELATIONSHIP_RECOGNIZED", body.reason, before)
    session.commit()
    return row_for(session, row, entity_id)


def suspend_relation(session: Session, relation_id: int, user: User, body: RelationshipSuspension) -> dict:
    entity_id = organization_admin(user)
    row = require_relation(session, relation_id, entity_id)
    if len(body.reason.strip()) < 3:
        raise HTTPException(422, "Le motif de suspension ou reprise est requis")
    before = public_row(session, row)
    _lock_version(session, row, body.expected_version)
    local = session.get(RfqRelationshipSide, (row.id, entity_id))
    local.suspended, local.recognized_version = body.suspended, None
    local.updated_by, local.updated_at = user.id, datetime.utcnow()
    session.add(local)
    session.flush()
    _audit(session, row, user, "RFQ_RELATIONSHIP_SUSPENDED" if body.suspended else "RFQ_RELATIONSHIP_RESUMED",
           body.reason, before)
    session.commit()
    return row_for(session, row, entity_id)


def eligibility(session: Session, row: RfqRelationship, rfq: RfqRequest,
                 *, currency: str | None, nominal: float | None, purpose="solicit") -> list[str]:
    terms = RelationshipTerms.model_validate_json(row.terms_json)
    issues = []
    if row.requester_entity_id != rfq.entity_id:
        return ["La relation appartient à une autre organisation demandeuse"]
    state = status(session, row)
    if state != "ACTIVE":
        issues.append({"PENDING": "Reconnaissance des deux parties requise", "SUSPENDED": "Relation suspendue",
                       "EXPIRED": "Relation expirée", "NOT_STARTED": "Relation pas encore en vigueur"}[state])
    desk = session.get(RfqDesk, row.receiver_desk_id)
    if not desk or not desk.active or desk.entity_id != row.partner_entity_id:
        issues.append("Desk destinataire indisponible")
    if not terms.solicitation_allowed:
        issues.append("Sollicitation non autorisée")
    if (rfq.kind == "indicatif" and not terms.indicative_allowed) or (rfq.kind == "to_trade" and not terms.to_trade_allowed):
        issues.append("Nature de RFQ hors périmètre")
    for value, allowed, label in [(rfq.transaction_format, terms.formats, "Format"),
                                  (rfq.instrument_family, terms.instruments, "Instrument"),
                                  (currency, terms.currencies, "Devise")]:
        if not value or value.strip().upper() not in allowed:
            issues.append(f"{label} hors périmètre ou manquant")
    if canonical_payoff_family(rfq.payoff_family) not in terms.payoff_families:
        issues.append("Famille de payoff hors périmètre ou manquante")
    if not isinstance(nominal, (int, float)) or isinstance(nominal, bool) or not math.isfinite(nominal) or nominal <= 0:
        issues.append("Nominal positif et fini requis")
    elif (terms.min_notional and nominal < terms.min_notional) or (terms.max_notional and nominal > terms.max_notional):
        issues.append("Nominal hors périmètre")
    for side in sides(session, row):
        cpty = session.get(Counterparty, side.counterparty_id) if side.counterparty_id else None
        if not cpty or not cpty.active:
            issues.append("Rapprochement juridique inactif ou manquant")
        from .rfq_transport import channel_for_relation
        channel = channel_for_relation(session, row.id)
        if purpose == "treat" and (not channel or side.entity_id == channel.entity_id):
            try:
                _validate_mapping(session, side.entity_id, side.counterparty_id, side.trading_relationship_id, terms)
                if side.trading_relationship_id is not None:
                    booking = json.loads(session.get(TradingRelationship, side.trading_relationship_id).terms_json)
                    today = business_today().isoformat()
                    if (booking.get("currency") != currency or booking.get("effective_date", today) > today
                            or (booking.get("expiry_date") and booking["expiry_date"] < today)):
                        issues.append("Accord de booking hors devise ou dates de traitement")
                    permission = "otc_allowed" if str(rfq.transaction_format).upper() == "OTC" else "note_distribution_allowed"
                    if not booking.get(permission):
                        issues.append("Instrument non autorisé par l'accord de booking")
            except HTTPException as exc:
                issues.append(str(exc.detail))
    if purpose == "treat" and not terms.treatment_allowed:
        issues.append("Traitement non autorisé par cette relation")
    return list(dict.fromkeys(issues))
