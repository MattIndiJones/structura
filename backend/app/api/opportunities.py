"""Opportunités — l'intention d'investissement, entre le client et la RFQ.

Deux règles gouvernent ce fichier.

**Un contact appartient au client de son opportunité.** Vérifié à la création,
à la modification, et surtout au changement de client — le cas §29, où l'on
remplace Client A par Client B en laissant derrière des contacts qui n'y
travaillent pas. Le contrôle est ici et pas seulement à l'écran : un appel
direct doit se heurter au même refus.

**Une opportunité ne suit jamais une personne qui change d'employeur.** Elle
reste attachée à l'affiliation sous laquelle elle a été ouverte, donc au client
de l'époque. Si le contact part, on la clôt ou on la continue avec quelqu'un
d'autre de la même maison — on n'en fait pas une opportunité chez le nouvel
employeur (§30).
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session, select

from ..core.audit import commit_rejection, record_audit_event
from ..core.client_controls import (
    ClientRuleError, LOST_REASONS, OPPORTUNITY_TERMINAL, PARTICIPANT_ROLES,
    require_mandate_of_client, validate_data_origin, validate_opportunity_contacts,
    validate_status_transition,
)
from ..core.references import next_reference
from ..db.database import get_session
from ..db.models import (
    Affiliation, Client, ClientMandate, Deal, Interaction, Opportunity,
    OpportunityParticipant, Person, RfqRequest, User,
)
from .auth import get_current_user

router = APIRouter(prefix="/api/opportunities", tags=["opportunities"])


# ── Schémas ───────────────────────────────────────────────────────────

class ParticipantIn(BaseModel):
    affiliation_id: int
    role: str = "other"


class OpportunityCreate(BaseModel):
    client_id: int
    mandate_id: Optional[int] = None
    primary_affiliation_id: Optional[int] = None
    participants: list[ParticipantIn] = []
    title: str = ""
    description: Optional[str] = None
    amount: Optional[float] = None
    currency: str = "EUR"
    horizon: Optional[str] = None
    expected_trade_date: Optional[str] = None
    expected_window_start: Optional[str] = None
    expected_window_end: Optional[str] = None
    priority: str = "medium"
    source: Optional[str] = None
    transaction_format: Optional[str] = None
    instrument_family: Optional[str] = None
    payoff_family: Optional[str] = None
    payoff_description: Optional[str] = None
    data_origin: Optional[str] = None
    status: str = "lead"
    notes: Optional[str] = None
    next_action: Optional[str] = None
    next_action_date: Optional[str] = None


class OpportunityUpdate(BaseModel):
    client_id: Optional[int] = None
    mandate_id: Optional[int] = None
    primary_affiliation_id: Optional[int] = None
    participants: Optional[list[ParticipantIn]] = None
    title: Optional[str] = None
    description: Optional[str] = None
    amount: Optional[float] = None
    currency: Optional[str] = None
    horizon: Optional[str] = None
    expected_trade_date: Optional[str] = None
    expected_window_start: Optional[str] = None
    expected_window_end: Optional[str] = None
    priority: Optional[str] = None
    source: Optional[str] = None
    transaction_format: Optional[str] = None
    instrument_family: Optional[str] = None
    payoff_family: Optional[str] = None
    payoff_description: Optional[str] = None
    data_origin: Optional[str] = None
    notes: Optional[str] = None
    next_action: Optional[str] = None
    next_action_date: Optional[str] = None
    owner_user_id: Optional[int] = None


class StatusChange(BaseModel):
    status: str
    lost_reason: Optional[str] = None
    lost_comment: Optional[str] = None


# ── Portée et rendu ───────────────────────────────────────────────────

def _scoped(session: Session, opportunity_id: int, current: User) -> Opportunity:
    opportunite = session.get(Opportunity, opportunity_id)
    if opportunite is None or opportunite.entity_id != current.entity_id:
        raise HTTPException(404, "Opportunité introuvable")
    return opportunite


def _scoped_client(session: Session, client_id: int, current: User) -> Client:
    client = session.get(Client, client_id)
    if client is None or client.entity_id != current.entity_id:
        raise HTTPException(404, "Client introuvable")
    return client


def _contact_rendu(session: Session, affiliation_id: Optional[int]) -> Optional[dict]:
    if affiliation_id is None:
        return None
    affiliation = session.get(Affiliation, affiliation_id)
    if affiliation is None:
        return None
    personne = session.get(Person, affiliation.person_id)
    return {
        "affiliation_id": affiliation.id,
        "person_id": affiliation.person_id,
        "name": (f"{personne.first_name} {personne.last_name}".strip()
                 if personne else None),
        "job_title": affiliation.job_title,
        "commercial_role": affiliation.commercial_role,
        # Le contact a-t-il quitté la maison depuis ? L'opportunité reste chez
        # le client d'origine, mais l'écran doit pouvoir le signaler (§30).
        "still_current": affiliation.end_date is None,
    }


def _rendu(session: Session, opportunite: Opportunity, *, detail: bool = False) -> dict:
    client = session.get(Client, opportunite.client_id)
    mandate = (session.get(ClientMandate, opportunite.mandate_id)
               if opportunite.mandate_id is not None else None)
    base = {
        "id": opportunite.id,
        "reference": opportunite.reference,
        "client_id": opportunite.client_id,
        "client_name": client.name if client else None,
        "mandate_id": opportunite.mandate_id,
        "mandate": ({"id": mandate.id, "name": mandate.name,
                     "mandate_type": mandate.mandate_type,
                     "status": mandate.status,
                     "reference_currency": mandate.reference_currency}
                    if mandate else None),
        "owner_user_id": opportunite.owner_user_id,
        "primary_contact": _contact_rendu(session,
                                          opportunite.primary_affiliation_id),
        "title": opportunite.title,
        "description": opportunite.description,
        "amount": opportunite.amount,
        "currency": opportunite.currency,
        "horizon": opportunite.horizon,
        "expected_trade_date": opportunite.expected_trade_date,
        "expected_window_start": opportunite.expected_window_start,
        "expected_window_end": opportunite.expected_window_end,
        "priority": opportunite.priority,
        "source": opportunite.source,
        "transaction_format": opportunite.transaction_format,
        "instrument_family": opportunite.instrument_family,
        "payoff_family": opportunite.payoff_family,
        "payoff_description": opportunite.payoff_description,
        "data_origin": opportunite.data_origin,
        "status": opportunite.status,
        "lost_reason": opportunite.lost_reason,
        "lost_comment": opportunite.lost_comment,
        "next_action": opportunite.next_action,
        "next_action_date": opportunite.next_action_date,
        "notes": opportunite.notes,
        "last_activity_at": (opportunite.last_activity_at.isoformat()
                             if opportunite.last_activity_at else None),
        "created_at": opportunite.created_at.isoformat(),
        "updated_at": opportunite.updated_at.isoformat(),
    }
    if detail:
        participants = session.exec(
            select(OpportunityParticipant).where(
                OpportunityParticipant.opportunity_id == opportunite.id)).all()
        base["participants"] = [
            {**(_contact_rendu(session, p.affiliation_id) or {}), "role": p.role}
            for p in participants
        ]
        base["interactions"] = [
            {"id": i.id, "interaction_date": i.interaction_date,
             "interaction_type": i.interaction_type, "summary": i.summary}
            for i in session.exec(
                select(Interaction).where(
                    Interaction.opportunity_id == opportunite.id)).all()
        ]
        base["rfqs"] = [
            {"id": r.id, "reference": r.reference, "name": r.name,
             "status": r.status}
            for r in session.exec(
                select(RfqRequest).where(
                    RfqRequest.opportunity_id == opportunite.id)).all()
        ]
        base["deals"] = [
            {"id": d.id, "reference": d.reference, "nominal": d.nominal,
             "devise": d.devise}
            for d in session.exec(
                select(Deal).where(Deal.opportunity_id == opportunite.id)).all()
        ]
    return base


def _set_participants(session: Session, opportunite: Opportunity,
                      participants: list[ParticipantIn]) -> None:
    """Remplace la liste des participants après validation complète.

    On valide TOUT avant d'écrire quoi que ce soit : valider au fil de
    l'écriture laisserait une liste à moitié remplacée si le troisième
    participant est refusé.
    """
    for participant in participants:
        if participant.role not in PARTICIPANT_ROLES:
            raise ClientRuleError(
                code="PARTICIPANT_ROLE_INVALID",
                message=(f"Rôle « {participant.role} » inconnu. Acceptés : "
                         f"{', '.join(sorted(PARTICIPANT_ROLES))}."))
    validate_opportunity_contacts(
        session, opportunite.client_id, opportunite.primary_affiliation_id,
        [p.affiliation_id for p in participants])

    for ancien in session.exec(
            select(OpportunityParticipant).where(
                OpportunityParticipant.opportunity_id == opportunite.id)).all():
        session.delete(ancien)
    session.flush()
    for participant in participants:
        session.add(OpportunityParticipant(
            opportunity_id=opportunite.id,
            affiliation_id=participant.affiliation_id, role=participant.role))


# ── Lecture ───────────────────────────────────────────────────────────

@router.get("")
def list_opportunities(
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    client_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    owner_user_id: Optional[int] = Query(None),
    person_id: Optional[int] = Query(None),
    open_only: bool = Query(False, description="Exclure les dossiers clos"),
):
    requete = select(Opportunity).where(Opportunity.entity_id == current.entity_id)
    if client_id is not None:
        requete = requete.where(Opportunity.client_id == client_id)
    if status:
        requete = requete.where(Opportunity.status == status)
    if priority:
        requete = requete.where(Opportunity.priority == priority)
    if owner_user_id is not None:
        requete = requete.where(Opportunity.owner_user_id == owner_user_id)
    opportunites = list(session.exec(requete).all())

    if open_only:
        opportunites = [o for o in opportunites
                        if o.status not in OPPORTUNITY_TERMINAL]

    if person_id is not None:
        # Toutes les affiliations de la personne, pas seulement l'actuelle :
        # « les opportunités de Jean » inclut celles qu'il portait chez son
        # employeur précédent.
        ids = [a.id for a in session.exec(
            select(Affiliation).where(Affiliation.person_id == person_id)).all()]
        participations = {
            p.opportunity_id for p in session.exec(
                select(OpportunityParticipant).where(
                    OpportunityParticipant.affiliation_id.in_(ids))).all()
        } if ids else set()
        opportunites = [o for o in opportunites
                        if o.primary_affiliation_id in ids
                        or o.id in participations]

    return [_rendu(session, o) for o in
            sorted(opportunites, key=lambda o: o.created_at, reverse=True)]


@router.get("/lost-reasons")
def list_lost_reasons():
    """Le vocabulaire fermé des raisons de perte, pour alimenter le sélecteur.
    Exposé plutôt que recopié dans le frontend : deux listes divergent."""
    return sorted(LOST_REASONS)


@router.get("/{opportunity_id}")
def get_opportunity(
    opportunity_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    return _rendu(session, _scoped(session, opportunity_id, current), detail=True)


# ── Écriture ──────────────────────────────────────────────────────────

@router.post("", status_code=201)
def create_opportunity(
    body: OpportunityCreate,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    client = _scoped_client(session, body.client_id, current)
    try:
        validate_status_transition("", body.status, None)
        data_origin = validate_data_origin(body.data_origin or client.data_origin)
        if body.mandate_id is not None:
            require_mandate_of_client(session, body.mandate_id, client.id)
    except ClientRuleError as erreur:
        raise HTTPException(422, detail=erreur.as_dict())

    reference = next_reference(
        session, Opportunity, f"OPP-{date.today().strftime('%Y%m%d')}-")
    opportunite = Opportunity(
        reference=reference, entity_id=current.entity_id,
        owner_user_id=current.id, client_id=body.client_id,
        mandate_id=body.mandate_id,
        primary_affiliation_id=body.primary_affiliation_id,
        title=body.title.strip(), description=body.description,
        amount=body.amount, currency=body.currency, horizon=body.horizon,
        expected_trade_date=body.expected_trade_date,
        expected_window_start=body.expected_window_start,
        expected_window_end=body.expected_window_end,
        priority=body.priority, source=body.source,
        transaction_format=(body.transaction_format or None),
        instrument_family=(body.instrument_family or None),
        payoff_family=(body.payoff_family or None),
        payoff_description=(body.payoff_description or None),
        data_origin=data_origin, status=body.status,
        notes=body.notes, next_action=body.next_action,
        next_action_date=body.next_action_date,
        last_activity_at=datetime.utcnow())
    session.add(opportunite)
    session.flush()

    try:
        _set_participants(session, opportunite, body.participants)
    except ClientRuleError as erreur:
        session.rollback()
        raise HTTPException(422, detail=erreur.as_dict())

    record_audit_event(
        session, action="OPPORTUNITY_CREATED", object_type="opportunity",
        object_id=opportunite.id, actor_user_id=current.id, result="SUCCESS",
        after={"reference": reference, "client_id": body.client_id,
               "mandate_id": body.mandate_id, "status": body.status,
               "data_origin": data_origin})
    session.commit()
    session.refresh(opportunite)
    return _rendu(session, opportunite, detail=True)


@router.patch("/{opportunity_id}")
def update_opportunity(
    opportunity_id: int,
    body: OpportunityUpdate,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    """Modifie une opportunité, y compris son client.

    Changer de client est le cas §29 : les contacts déjà sélectionnés ne sont
    probablement plus valides. On ne les efface pas en silence — on refuse tant
    que l'appelant n'a pas fourni une sélection cohérente avec le nouveau
    client, en le disant.
    """
    opportunite = _scoped(session, opportunity_id, current)
    avant = {"client_id": opportunite.client_id,
             "mandate_id": opportunite.mandate_id,
             "status": opportunite.status,
             "owner_user_id": opportunite.owner_user_id}

    if body.client_id is not None and body.client_id != opportunite.client_id:
        new_client = _scoped_client(session, body.client_id, current)
        participants_fournis = body.participants if body.participants is not None else []
        contact_fourni = (body.primary_affiliation_id
                          if "primary_affiliation_id" in body.model_fields_set
                          else opportunite.primary_affiliation_id)
        try:
            validate_opportunity_contacts(
                session, body.client_id, contact_fourni,
                [p.affiliation_id for p in participants_fournis])
            mandate_fourni = (body.mandate_id
                              if "mandate_id" in body.model_fields_set
                              else opportunite.mandate_id)
            if mandate_fourni is not None:
                require_mandate_of_client(session, mandate_fourni, new_client.id)
        except ClientRuleError as erreur:
            commit_rejection(
                session, action="OPPORTUNITY_CLIENT_CHANGE_REJECTED",
                object_type="opportunity", object_id=opportunite.id,
                actor_user_id=current.id, reason=erreur.code,
                metadata={"from_client": opportunite.client_id,
                          "to_client": body.client_id})
            raise HTTPException(409, detail={
                "code": erreur.code,
                "message": (f"{erreur.message} Le client a changé : "
                            f"resélectionnez les contacts."),
            })
        opportunite.client_id = body.client_id
        opportunite.primary_affiliation_id = contact_fourni
        opportunite.mandate_id = mandate_fourni

    elif "primary_affiliation_id" in body.model_fields_set:
        try:
            validate_opportunity_contacts(
                session, opportunite.client_id, body.primary_affiliation_id, [])
        except ClientRuleError as erreur:
            raise HTTPException(422, detail=erreur.as_dict())
        opportunite.primary_affiliation_id = body.primary_affiliation_id

    if ("mandate_id" in body.model_fields_set
            and not (body.client_id is not None
                     and body.client_id != avant["client_id"])):
        if body.mandate_id is not None:
            try:
                require_mandate_of_client(
                    session, body.mandate_id, opportunite.client_id)
            except ClientRuleError as erreur:
                raise HTTPException(422, detail=erreur.as_dict())
        opportunite.mandate_id = body.mandate_id

    if body.owner_user_id is not None:
        cible = session.get(User, body.owner_user_id)
        if cible is None or cible.entity_id != current.entity_id:
            raise HTTPException(404, "Utilisateur introuvable")
        opportunite.owner_user_id = body.owner_user_id

    for champ in ("title", "description", "amount", "currency", "horizon",
                  "expected_trade_date", "expected_window_start",
                  "expected_window_end", "priority", "source",
                  "transaction_format", "instrument_family", "payoff_family",
                  "payoff_description", "notes", "next_action",
                  "next_action_date"):
        valeur = getattr(body, champ)
        if valeur is not None:
            setattr(opportunite, champ, valeur)

    if body.data_origin is not None:
        try:
            opportunite.data_origin = validate_data_origin(body.data_origin)
        except ClientRuleError as erreur:
            raise HTTPException(422, detail=erreur.as_dict())

    if body.participants is not None:
        try:
            _set_participants(session, opportunite, body.participants)
        except ClientRuleError as erreur:
            session.rollback()
            raise HTTPException(422, detail=erreur.as_dict())

    opportunite.updated_at = datetime.utcnow()
    opportunite.last_activity_at = datetime.utcnow()
    session.add(opportunite)
    if avant["client_id"] != opportunite.client_id:
        record_audit_event(
            session, action="OPPORTUNITY_CLIENT_CHANGED",
            object_type="opportunity", object_id=opportunite.id,
            actor_user_id=current.id, result="SUCCESS",
            before={"client_id": avant["client_id"]},
            after={"client_id": opportunite.client_id})
    if avant["owner_user_id"] != opportunite.owner_user_id:
        record_audit_event(
            session, action="OPPORTUNITY_REASSIGNED", object_type="opportunity",
            object_id=opportunite.id, actor_user_id=current.id, result="SUCCESS",
            before={"owner_user_id": avant["owner_user_id"]},
            after={"owner_user_id": opportunite.owner_user_id})
    if avant["mandate_id"] != opportunite.mandate_id:
        record_audit_event(
            session, action="OPPORTUNITY_MANDATE_CHANGED",
            object_type="opportunity", object_id=opportunite.id,
            actor_user_id=current.id, result="SUCCESS",
            before={"mandate_id": avant["mandate_id"]},
            after={"mandate_id": opportunite.mandate_id})
    session.commit()
    session.refresh(opportunite)
    return _rendu(session, opportunite, detail=True)


@router.post("/{opportunity_id}/status")
def change_status(
    opportunity_id: int,
    body: StatusChange,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    """Change le statut. Perdre exige un motif — c'est la matière première de
    Client Intelligence : savoir pourquoi un client refuse vaut mieux que
    savoir combien de fois."""
    opportunite = _scoped(session, opportunity_id, current)
    avant = opportunite.status
    if body.status in {"lost", "cancelled"}:
        booked = session.exec(
            select(Deal).where(Deal.opportunity_id == opportunite.id)).first()
        if booked:
            detail = {
                "code": "OPPORTUNITY_HAS_BOOKED_DEAL",
                "message": (f"Le deal {booked.reference} est rattaché à cette Opportunity. "
                            "Elle ne peut pas être marquée perdue ou annulée sans "
                            "rectification explicite du rattachement."),
            }
            commit_rejection(
                session, action="OPPORTUNITY_STATUS_REJECTED",
                object_type="opportunity", object_id=opportunite.id,
                actor_user_id=current.id, reason=detail["code"],
                metadata={"from": avant, "to": body.status,
                          "deal_id": booked.id})
            raise HTTPException(409, detail=detail)
    try:
        validate_status_transition(avant, body.status, body.lost_reason)
    except ClientRuleError as erreur:
        commit_rejection(
            session, action="OPPORTUNITY_STATUS_REJECTED",
            object_type="opportunity", object_id=opportunite.id,
            actor_user_id=current.id, reason=erreur.code,
            metadata={"from": avant, "to": body.status})
        raise HTTPException(422, detail=erreur.as_dict())

    opportunite.status = body.status
    if body.status == "lost":
        opportunite.lost_reason = body.lost_reason
        opportunite.lost_comment = body.lost_comment
    opportunite.updated_at = datetime.utcnow()
    opportunite.last_activity_at = datetime.utcnow()
    session.add(opportunite)
    record_audit_event(
        session, action="OPPORTUNITY_STATUS_CHANGED", object_type="opportunity",
        object_id=opportunite.id, actor_user_id=current.id, result="SUCCESS",
        before={"status": avant},
        after={"status": body.status, "lost_reason": opportunite.lost_reason},
        reason=body.lost_comment)
    session.commit()
    session.refresh(opportunite)
    return _rendu(session, opportunite, detail=True)


@router.delete("/{opportunity_id}", status_code=204)
def delete_opportunity(
    opportunity_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    """Suppression physique — réservée à un dossier vierge.

    Reliée à une interaction, une RFQ ou un trade, une opportunité s'annule ou
    s'archive : elle est le maillon qui rend la chaîne Trade → RFQ →
    Opportunity → Client reconstructible, et la supprimer la briserait.
    """
    opportunite = _scoped(session, opportunity_id, current)
    portant = {
        "interactions": len(session.exec(
            select(Interaction).where(
                Interaction.opportunity_id == opportunite.id)).all()),
        "rfqs": len(session.exec(
            select(RfqRequest).where(
                RfqRequest.opportunity_id == opportunite.id)).all()),
        "deals": len(session.exec(
            select(Deal).where(Deal.opportunity_id == opportunite.id)).all()),
    }
    if any(portant.values()):
        detail = ", ".join(f"{v} {k}" for k, v in portant.items() if v)
        commit_rejection(
            session, action="OPPORTUNITY_DELETE_REJECTED",
            object_type="opportunity", object_id=opportunite.id,
            actor_user_id=current.id, reason="OPPORTUNITY_HAS_HISTORY",
            metadata=portant)
        raise HTTPException(409, detail={
            "code": "OPPORTUNITY_HAS_HISTORY",
            "message": (f"Ce dossier porte {detail}. Annulez-le ou archivez-le "
                        f"plutôt que de le supprimer."),
        })

    for participant in session.exec(
            select(OpportunityParticipant).where(
                OpportunityParticipant.opportunity_id == opportunite.id)).all():
        session.delete(participant)
    record_audit_event(
        session, action="OPPORTUNITY_DELETED", object_type="opportunity",
        object_id=opportunite.id, actor_user_id=current.id, result="SUCCESS",
        before={"reference": opportunite.reference})
    session.delete(opportunite)
    session.commit()
