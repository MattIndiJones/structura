"""Interactions — les événements commerciaux datés.

Une interaction se rattache TOUJOURS à un client, JAMAIS obligatoirement à une
opportunité : une prospection initiale n'a pas de dossier derrière elle, et
l'exiger obligerait à ouvrir une opportunité vide pour enregistrer un premier
appel.

Les participants sont désignés par leur affiliation du moment, comme partout
ailleurs dans ce module : une réunion tenue chez Bank A en 2024 reste une
réunion chez Bank A, même si son participant travaille ailleurs aujourd'hui.
"""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session, select

from ..core.audit import record_audit_event
from ..core.client_controls import (
    ClientRuleError, INTERACTION_TYPES, PARTICIPANT_ROLES, parse_iso_date,
    require_affiliation_of_client, validate_interaction_type,
)
from ..db.database import get_session
from ..db.models import (
    Affiliation, Client, Interaction, InteractionParticipant, Opportunity,
    Person, User,
)
from .auth import get_current_user

router = APIRouter(prefix="/api/interactions", tags=["interactions"])


class ParticipantIn(BaseModel):
    affiliation_id: int
    role: str = "other"


class InteractionCreate(BaseModel):
    client_id: int
    opportunity_id: Optional[int] = None
    interaction_date: str
    interaction_type: str = "other"
    summary: str = ""
    notes: Optional[str] = None
    next_action: Optional[str] = None
    next_action_date: Optional[str] = None
    participants: list[ParticipantIn] = []


class InteractionUpdate(BaseModel):
    interaction_date: Optional[str] = None
    interaction_type: Optional[str] = None
    summary: Optional[str] = None
    notes: Optional[str] = None
    next_action: Optional[str] = None
    next_action_date: Optional[str] = None
    opportunity_id: Optional[int] = None
    participants: Optional[list[ParticipantIn]] = None


def _scoped(session: Session, interaction_id: int, current: User) -> Interaction:
    interaction = session.get(Interaction, interaction_id)
    if interaction is None or interaction.entity_id != current.entity_id:
        raise HTTPException(404, "Interaction introuvable")
    return interaction


def _scoped_client(session: Session, client_id: int, current: User) -> Client:
    client = session.get(Client, client_id)
    if client is None or client.entity_id != current.entity_id:
        raise HTTPException(404, "Client introuvable")
    return client


def _participants_rendus(session: Session, interaction_id: int) -> list[dict]:
    sortie = []
    for lien in session.exec(
            select(InteractionParticipant).where(
                InteractionParticipant.interaction_id == interaction_id)).all():
        affiliation = session.get(Affiliation, lien.affiliation_id)
        personne = (session.get(Person, affiliation.person_id)
                    if affiliation else None)
        sortie.append({
            "affiliation_id": lien.affiliation_id,
            "person_id": affiliation.person_id if affiliation else None,
            "name": (f"{personne.first_name} {personne.last_name}".strip()
                     if personne else None),
            "role": lien.role,
        })
    return sortie


def _rendu(session: Session, interaction: Interaction) -> dict:
    client = session.get(Client, interaction.client_id)
    opportunite = (session.get(Opportunity, interaction.opportunity_id)
                   if interaction.opportunity_id else None)
    return {
        "id": interaction.id,
        "client_id": interaction.client_id,
        "client_name": client.name if client else None,
        "opportunity_id": interaction.opportunity_id,
        "opportunity_reference": opportunite.reference if opportunite else None,
        "user_id": interaction.user_id,
        "interaction_date": interaction.interaction_date,
        "interaction_type": interaction.interaction_type,
        "summary": interaction.summary,
        "notes": interaction.notes,
        "next_action": interaction.next_action,
        "next_action_date": interaction.next_action_date,
        "participants": _participants_rendus(session, interaction.id),
        "created_at": interaction.created_at.isoformat(),
        "updated_at": interaction.updated_at.isoformat(),
    }


def _set_participants(session: Session, interaction: Interaction,
                      participants: list[ParticipantIn]) -> None:
    """Valide tout avant d'écrire : une liste à moitié remplacée serait pire
    que le refus."""
    vus: set[int] = set()
    for participant in participants:
        if participant.role not in PARTICIPANT_ROLES:
            raise ClientRuleError(
                code="PARTICIPANT_ROLE_INVALID",
                message=(f"Rôle « {participant.role} » inconnu. Acceptés : "
                         f"{', '.join(sorted(PARTICIPANT_ROLES))}."))
        # Le participant doit travailler chez le client de l'interaction —
        # sinon on enregistrerait une réunion chez Bank A avec un contact de
        # Bank B, ce qui fausserait toute statistique par affiliation.
        require_affiliation_of_client(session, participant.affiliation_id,
                                      interaction.client_id)
        if participant.affiliation_id in vus:
            raise ClientRuleError(
                code="PARTICIPANT_DUPLICATE",
                message="Ce contact figure deux fois parmi les participants.")
        vus.add(participant.affiliation_id)

    for ancien in session.exec(
            select(InteractionParticipant).where(
                InteractionParticipant.interaction_id == interaction.id)).all():
        session.delete(ancien)
    session.flush()
    for participant in participants:
        session.add(InteractionParticipant(
            interaction_id=interaction.id,
            affiliation_id=participant.affiliation_id, role=participant.role))


@router.get("")
def list_interactions(
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    client_id: Optional[int] = Query(None),
    opportunity_id: Optional[int] = Query(None),
    person_id: Optional[int] = Query(None),
    interaction_type: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
):
    requete = select(Interaction).where(Interaction.entity_id == current.entity_id)
    if client_id is not None:
        requete = requete.where(Interaction.client_id == client_id)
    if opportunity_id is not None:
        requete = requete.where(Interaction.opportunity_id == opportunity_id)
    if interaction_type:
        requete = requete.where(Interaction.interaction_type == interaction_type)
    interactions = list(session.exec(requete).all())

    if person_id is not None:
        ids = [a.id for a in session.exec(
            select(Affiliation).where(Affiliation.person_id == person_id)).all()]
        retenus = {
            p.interaction_id for p in session.exec(
                select(InteractionParticipant).where(
                    InteractionParticipant.affiliation_id.in_(ids))).all()
        } if ids else set()
        interactions = [i for i in interactions if i.id in retenus]

    interactions.sort(key=lambda i: (i.interaction_date or "", i.id or 0),
                      reverse=True)
    return [_rendu(session, i) for i in interactions[:limit]]


@router.get("/types")
def list_types():
    return sorted(INTERACTION_TYPES)


@router.get("/{interaction_id}")
def get_interaction(
    interaction_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    return _rendu(session, _scoped(session, interaction_id, current))


@router.post("", status_code=201)
def create_interaction(
    body: InteractionCreate,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    _scoped_client(session, body.client_id, current)
    try:
        validate_interaction_type(body.interaction_type)
        parse_iso_date(body.interaction_date, "Date de l'interaction")
        if body.next_action_date:
            parse_iso_date(body.next_action_date, "Date de la prochaine action")
    except ClientRuleError as erreur:
        raise HTTPException(422, erreur.message)

    if body.opportunity_id is not None:
        opportunite = session.get(Opportunity, body.opportunity_id)
        if opportunite is None or opportunite.entity_id != current.entity_id:
            raise HTTPException(404, "Opportunité introuvable")
        if opportunite.client_id != body.client_id:
            raise HTTPException(422, detail={
                "code": "OPPORTUNITY_CLIENT_MISMATCH",
                "message": ("Cette opportunité ne concerne pas ce client."),
            })

    interaction = Interaction(
        entity_id=current.entity_id, user_id=current.id,
        client_id=body.client_id, opportunity_id=body.opportunity_id,
        interaction_date=body.interaction_date,
        interaction_type=body.interaction_type, summary=body.summary,
        notes=body.notes, next_action=body.next_action,
        next_action_date=body.next_action_date)
    session.add(interaction)
    session.flush()

    try:
        _set_participants(session, interaction, body.participants)
    except ClientRuleError as erreur:
        session.rollback()
        raise HTTPException(422, detail=erreur.as_dict())

    # Une interaction est de l'activité : elle rafraîchit la date de dernière
    # activité du dossier, ce qui alimente le signal « opportunité en sommeil ».
    if body.opportunity_id is not None:
        opportunite = session.get(Opportunity, body.opportunity_id)
        opportunite.last_activity_at = datetime.utcnow()
        session.add(opportunite)

    record_audit_event(
        session, action="INTERACTION_CREATED", object_type="interaction",
        object_id=interaction.id, actor_user_id=current.id, result="SUCCESS",
        after={"client_id": body.client_id,
               "opportunity_id": body.opportunity_id,
               "interaction_type": body.interaction_type})
    session.commit()
    session.refresh(interaction)
    return _rendu(session, interaction)


@router.patch("/{interaction_id}")
def update_interaction(
    interaction_id: int,
    body: InteractionUpdate,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    interaction = _scoped(session, interaction_id, current)
    if body.interaction_type is not None:
        try:
            validate_interaction_type(body.interaction_type)
        except ClientRuleError as erreur:
            raise HTTPException(422, erreur.message)
        interaction.interaction_type = body.interaction_type
    for champ in ("interaction_date", "summary", "notes", "next_action",
                  "next_action_date"):
        valeur = getattr(body, champ)
        if valeur is not None:
            setattr(interaction, champ, valeur)

    if "opportunity_id" in body.model_fields_set:
        if body.opportunity_id is None:
            interaction.opportunity_id = None
        else:
            opportunite = session.get(Opportunity, body.opportunity_id)
            if opportunite is None or opportunite.entity_id != current.entity_id:
                raise HTTPException(404, "Opportunité introuvable")
            if opportunite.client_id != interaction.client_id:
                raise HTTPException(422, detail={
                    "code": "OPPORTUNITY_CLIENT_MISMATCH",
                    "message": "Cette opportunité ne concerne pas ce client."})
            interaction.opportunity_id = body.opportunity_id

    if body.participants is not None:
        try:
            _set_participants(session, interaction, body.participants)
        except ClientRuleError as erreur:
            session.rollback()
            raise HTTPException(422, detail=erreur.as_dict())

    interaction.updated_at = datetime.utcnow()
    session.add(interaction)
    session.commit()
    session.refresh(interaction)
    return _rendu(session, interaction)


@router.delete("/{interaction_id}", status_code=204)
def delete_interaction(
    interaction_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    """Une interaction se supprime — c'est une note, pas un contrat.

    Mais elle nourrit le calcul du délai entre première discussion et trade :
    l'effacer déplace ce délai. D'où la trace d'audit, qui garde ce qui a été
    retiré et par qui.
    """
    interaction = _scoped(session, interaction_id, current)
    for lien in session.exec(
            select(InteractionParticipant).where(
                InteractionParticipant.interaction_id == interaction.id)).all():
        session.delete(lien)
    record_audit_event(
        session, action="INTERACTION_DELETED", object_type="interaction",
        object_id=interaction.id, actor_user_id=current.id, result="SUCCESS",
        before={"client_id": interaction.client_id,
                "interaction_date": interaction.interaction_date,
                "interaction_type": interaction.interaction_type,
                "summary": interaction.summary})
    session.delete(interaction)
    session.commit()
