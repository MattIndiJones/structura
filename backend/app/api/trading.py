"""Reusable bilateral relationships, note bookings and settlement evidence."""
from datetime import date, datetime
import hashlib
import json
import threading
from typing import Annotated, Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, ConfigDict, model_validator
from sqlmodel import Session, select
from .auth import get_current_user
from .deals import DealCreate, _book_deal, _apply_pricing_receipt
from ..core.rfq_controls import product_terms, product_terms_hash
from ..db.database import get_session
from ..db.models import User, Entity, Counterparty, Deal
from ..db.trading_models import TradingRelationship, TradingExecution
from ..core.audit import record_audit_event
from ..runtime import business_today

router = APIRouter(prefix="/api/trading", tags=["Trading relationships"])
Current = Annotated[User, Depends(get_current_user)]
Database = Annotated[Session, Depends(get_session)]
_booking_lock = threading.RLock()


class RelationshipTerms(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    counterparty_id: int
    reference: str = Field(min_length=3, max_length=100)
    status: Literal["PENDING", "ACTIVE", "SUSPENDED", "EXPIRED"] = "PENDING"
    effective_date: date
    expiry_date: date | None = None
    currency: str = "EUR"
    note_distribution_allowed: bool = False
    otc_allowed: bool = False
    documentation_reference: str = Field(default="", max_length=1000)
    gross_notional_limit: float = Field(default=100_000_000, gt=0)
    master_agreement_id: int | None = None
    csa_id: int | None = None
    csa_required: bool = False
    settlement: Literal["DVP", "FREE_OF_PAYMENT"] = "DVP"
    notes: str = Field(default="", max_length=3000)

    @model_validator(mode="after")
    def dates(self):
        if self.expiry_date and self.expiry_date < self.effective_date:
            raise ValueError("L'expiration précède la date d'effet.")
        if self.status == "ACTIVE" and not self.documentation_reference.strip():
            raise ValueError("La documentation est requise pour activer la relation.")
        return self


class RelationshipUpdate(RelationshipTerms):
    expected_version: int


def entity_id(current):
    if current.entity_id is None:
        raise HTTPException(409, "Une entité est requise.")
    return current.entity_id


def relation(row):
    return {"id": row.id, "version": row.version, **json.loads(row.terms_json)}


@router.get("/relationships")
def relationships(current: Current, session: Database):
    return [relation(r) for r in session.exec(select(TradingRelationship).where(
        TradingRelationship.entity_id == entity_id(current))).all()]


def check_references(body, current, session):
    cpty = session.get(Counterparty, body.counterparty_id)
    if not cpty or not cpty.active:
        raise HTTPException(422, "Contrepartie inexistante ou inactive.")
    from ..db.ccr_models import CCRMasterAgreement, CCRCSAAgreement
    for key, model in [("master_agreement_id", CCRMasterAgreement), ("csa_id", CCRCSAAgreement)]:
        value = getattr(body, key)
        if value is not None:
            row = session.get(model, value)
            if not row or row.entity_id != current.entity_id or row.counterparty_id != body.counterparty_id:
                raise HTTPException(422, "L'accord CCR ne correspond pas à cette relation.")
    if body.status == "ACTIVE" and body.otc_allowed:
        if body.master_agreement_id is None or (body.csa_required and body.csa_id is None):
            raise HTTPException(422, "Accord OTC ou CSA requis manquant.")
        master = session.get(CCRMasterAgreement, body.master_agreement_id)
        terms = json.loads(master.payload_json)
        if terms.get("status") != "ACTIVE" or date.fromisoformat(terms["effective_date"]) > body.effective_date:
            raise HTTPException(422, "Le master agreement n'est pas actif à la date requise.")
        if body.csa_id:
            csa = json.loads(session.get(CCRCSAAgreement, body.csa_id).payload_json)
            if not csa.get("active") or csa.get("master_agreement_id") != body.master_agreement_id:
                raise HTTPException(422, "Le CSA ne correspond pas au master agreement actif.")


@router.post("/relationships", status_code=201)
def create_relationship(body: RelationshipTerms, current: Current, session: Database):
    check_references(body, current, session)
    if session.exec(select(TradingRelationship).where(
            TradingRelationship.entity_id == entity_id(current),
            TradingRelationship.counterparty_id == body.counterparty_id,
            TradingRelationship.reference == body.reference)).first():
        raise HTTPException(409, "Cette référence de relation existe déjà.")
    row = TradingRelationship(entity_id=current.entity_id, counterparty_id=body.counterparty_id,
        reference=body.reference, terms_json=body.model_dump_json(), updated_by=current.id)
    session.add(row); session.flush()
    record_audit_event(session, action="TRADING_RELATIONSHIP_CREATED", object_type="TRADING_RELATIONSHIP",
        object_id=row.id, actor_user_id=current.id, after=relation(row), result="SUCCESS")
    session.commit(); session.refresh(row)
    return relation(row)


@router.put("/relationships/{row_id}")
def update_relationship(row_id: int, body: RelationshipUpdate, current: Current, session: Database):
    row = session.get(TradingRelationship, row_id)
    if not row or row.entity_id != entity_id(current):
        raise HTTPException(404, "Relation introuvable.")
    if row.version != body.expected_version or body.counterparty_id != row.counterparty_id or body.reference != row.reference:
        raise HTTPException(409, "Version ou identité de relation incohérente.")
    check_references(body, current, session)
    before = relation(row)
    row.terms_json = body.model_dump_json(exclude={"expected_version"})
    row.version += 1; row.updated_by = current.id
    row.updated_at = datetime.utcnow()
    session.add(row)
    record_audit_event(session, action="TRADING_RELATIONSHIP_UPDATED", object_type="TRADING_RELATIONSHIP",
        object_id=row.id, actor_user_id=current.id, before=before, after=relation(row), result="SUCCESS")
    session.commit(); session.refresh(row)
    return relation(row)


class NoteBooking(BaseModel):
    model_config = ConfigDict(extra="forbid")
    trade_reference: str = Field(min_length=6, max_length=100)
    relationship_id: int
    issuer: str = Field(min_length=1, max_length=200)
    our_side: Literal["BUY", "SELL"]
    instrument_reference: str = Field(min_length=5, max_length=100)
    deal: DealCreate


def execution(row, session):
    d = session.get(Deal, row.deal_id)
    return {**row.model_dump(mode="json"), "nominal": d.nominal, "currency": d.devise,
        "price_traded": d.price_traded, "counterparty": d.contrepartie, "deal_reference": d.reference,
        "value_date": d.value_date, "status": d.status, "contract_hash": contract_identity(d)}


def contract_identity(deal):
    snapshot = json.loads(deal.market_snapshot_json or "{}")
    inputs = snapshot.get("pricing_input") or snapshot
    terms = product_terms(deal.script_snapshot, inputs)
    terms.update(currency=deal.devise, strike_date=deal.strike_date, maturity_date=deal.maturity_date,
        payment_date=deal.payment_date, transaction_format=deal.transaction_format)
    return product_terms_hash(terms)


@router.get("/executions")
def executions(current: Current, session: Database):
    return [execution(r, session) for r in session.exec(select(TradingExecution).where(
        TradingExecution.entity_id == entity_id(current))).all()]


@router.post("/book-note", status_code=201)
def book_note(body: NoteBooking, current: Current, session: Database):
    # The native booking commits before the journal is linked. Serialize this
    # critical section in the single-worker installation, including inventory.
    with _booking_lock:
        return _book_note(body, current, session)


def _book_note(body: NoteBooking, current: User, session: Session):
    digest = hashlib.sha256(body.model_dump_json().encode()).hexdigest()
    previous = session.exec(select(TradingExecution).where(
        TradingExecution.entity_id == entity_id(current), TradingExecution.trade_reference == body.trade_reference)).first()
    if previous:
        if previous.request_hash != digest:
            raise HTTPException(409, "Cette référence désigne une autre exécution.")
        return execution(previous, session)
    if not body.deal.pricing_receipt:
        raise HTTPException(422, "Le booking note exige un résultat de pricing authentifié de cette instance.")
    _apply_pricing_receipt(body.deal)
    row = session.get(TradingRelationship, body.relationship_id)
    if not row or row.entity_id != current.entity_id:
        raise HTTPException(404, "Relation introuvable.")
    terms = RelationshipTerms.model_validate_json(row.terms_json)
    as_of = business_today()
    if terms.status != "ACTIVE" or terms.effective_date > as_of or (terms.expiry_date and terms.expiry_date < as_of):
        raise HTTPException(422, "Relation inactive à la date de traitement.")
    if not terms.note_distribution_allowed or terms.currency != body.deal.devise:
        raise HTTPException(422, "Note ou devise hors périmètre de la relation.")
    if body.deal.documentation_reference != terms.documentation_reference:
        raise HTTPException(422, "La documentation du deal diffère de la relation de distribution.")
    cpty = session.get(Counterparty, row.counterparty_id)
    if body.deal.contrepartie != cpty.name:
        raise HTTPException(422, "La contrepartie du deal diffère de la relation.")
    expected_sens = "vente" if body.our_side == "BUY" else "achat"
    if body.deal.sens != expected_sens:
        raise HTTPException(422, "Le sens du Deal décrit la contrepartie : BUY correspond à vente.")
    if body.deal.transaction_format not in {"EMTN", "BMTN", "NOTE"} or body.deal.instrument_family != "NOTE":
        raise HTTPException(422, "Le booking note exige un format note explicite.")
    if body.deal.ccr_netting_set_id is not None:
        raise HTTPException(422, "Une note ne se rattache pas à un netting set OTC dans ce journal.")
    own_name = session.get(Entity, current.entity_id).name
    records = session.exec(select(TradingExecution).where(TradingExecution.entity_id == current.entity_id)).all()
    if any(x.instrument_reference == body.instrument_reference and x.issuer != body.issuer for x in records):
        raise HTTPException(409, "Cette référence d'instrument appartient à un autre émetteur.")
    inputs = body.deal.market_snapshot.get("pricing_input") or body.deal.market_snapshot
    identity = product_terms(body.deal.script_snapshot, inputs)
    identity.update(currency=body.deal.devise, strike_date=body.deal.strike_date,
        maturity_date=body.deal.maturity_date, payment_date=body.deal.payment_date,
        transaction_format=body.deal.transaction_format)
    fingerprint = product_terms_hash(identity)
    if any(contract_identity(session.get(Deal, x.deal_id)) != fingerprint for x in records
           if x.instrument_reference == body.instrument_reference and x.issuer == body.issuer):
        raise HTTPException(409, "Cette référence d'instrument possède d'autres termes contractuels.")
    used = sum(session.get(Deal, x.deal_id).nominal for x in records if x.relationship_id == row.id
        and session.get(Deal, x.deal_id).status in {"actif", "en_reglement"})
    if used + body.deal.nominal > terms.gross_notional_limit:
        raise HTTPException(422, "Limite de notionnel brut de la relation dépassée.")
    if body.our_side == "SELL" and body.issuer != own_name:
        holding = sum((1 if x.our_side == "BUY" else -1) * session.get(Deal, x.deal_id).nominal
            for x in records if x.instrument_reference == body.instrument_reference and x.issuer == body.issuer
            and session.get(Deal, x.deal_id).status in {"actif", "en_reglement"})
        if holding < body.deal.nominal:
            raise HTTPException(422, "Quantité de note détenue insuffisante pour cette vente.")
    marker = f"TRADING:{body.trade_reference}:{digest}"
    body.deal.commercial_reason = marker
    # Recover a committed native booking if the process stopped before the journal write.
    native = session.exec(select(Deal).where(Deal.user_id == current.id, Deal.commercial_reason == marker)).first()
    booked = {"id": native.id} if native else _book_deal(body.deal, current, session)
    out = TradingExecution(entity_id=current.entity_id, user_id=current.id, deal_id=booked["id"],
        relationship_id=row.id, trade_reference=body.trade_reference, request_hash=digest,
        issuer=body.issuer, our_side=body.our_side, instrument_reference=body.instrument_reference)
    session.add(out); session.flush()
    record_audit_event(session, action="NOTE_EXECUTION_LINKED", object_type="DEAL", object_id=out.deal_id,
        actor_user_id=current.id, after={"trade_reference": body.trade_reference, "issuer": body.issuer, "our_side": body.our_side}, result="SUCCESS")
    session.commit(); session.refresh(out)
    return execution(out, session)


class SettlementProof(BaseModel):
    reference: str = Field(min_length=5, max_length=200)


@router.post("/executions/{row_id}/settle")
def settle(row_id: int, body: SettlementProof, current: Current, session: Database):
    row = session.get(TradingExecution, row_id)
    if not row or row.entity_id != entity_id(current):
        raise HTTPException(404, "Exécution introuvable.")
    d = session.get(Deal, row.deal_id)
    if date.fromisoformat(d.value_date) > business_today():
        raise HTTPException(422, "La date de valeur n'est pas atteinte.")
    if row.settlement_status == "SETTLED" and row.settlement_reference != body.reference:
        raise HTTPException(409, "Cette exécution possède déjà une preuve de règlement.")
    if row.settlement_status != "SETTLED":
        row.settlement_status = "SETTLED"; row.settlement_reference = body.reference
        session.add(row)
        record_audit_event(session, action="NOTE_SETTLEMENT_RECORDED", object_type="DEAL", object_id=d.id,
            actor_user_id=current.id, after={"reference": body.reference}, result="SUCCESS")
        session.commit()
    return execution(row, session)


@router.get("/positions")
def positions(current: Current, session: Database):
    rows = executions(current, session)
    result = {}
    for row in rows:
        key = (row["instrument_reference"], row["issuer"])
        item = result.setdefault(key, {"instrument_reference": key[0], "issuer": key[1],
            "currency": row["currency"], "nominal": 0, "pending_cash": 0})
        signed = (1 if row["our_side"] == "BUY" else -1) * row["nominal"]
        if row["status"] in {"actif", "en_reglement"}:
            item["nominal"] += signed
        if row["settlement_status"] != "SETTLED":
            item["pending_cash"] -= signed * row["price_traded"] / 100
    return {"positions": list(result.values()), "risk_definition":
        "Le porteur de la note est exposé à son émetteur. Ce journal ne calcule ni CVA ni SA-CCR.",
        "our_entity": session.get(Entity, current.entity_id).name}
