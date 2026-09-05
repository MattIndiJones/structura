"""Personnes et affiliations — l'identité et l'historique professionnel.

Une personne n'appartient pas à une société : elle y travaille pendant une
période. Ce module n'expose donc aucun moyen de « changer l'employeur » d'une
personne. Il expose un moyen de **clore une affiliation et d'en ouvrir une
autre**, ce qui n'est pas la même chose : la première formulation réécrit un
passé, la seconde l'empile.

C'est la raison d'être de `POST /{id}/change-company`, et la raison pour
laquelle aucun `PATCH` de ce fichier ne touche au couple (person, client) d'une
affiliation existante.
"""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session, select

from ..core.audit import commit_rejection, record_audit_event
from ..core.client_controls import (
    ClientRuleError, change_company, close_affiliation, current_affiliation,
    find_person_duplicates, person_history_counts, require_person_deletable,
    validate_commercial_role, validate_coverage_role,
)
from ..db.database import get_session
from ..db.models import (
    Affiliation, Client, ContactCoverage, Deal, Opportunity,
    OpportunityParticipant, Person, User,
)
from .auth import get_current_user

router = APIRouter(prefix="/api/persons", tags=["persons"])


# ── Schémas ───────────────────────────────────────────────────────────

class PersonCreate(BaseModel):
    first_name: str
    last_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    notes: Optional[str] = None
    confirm_duplicate: bool = False
    # Rattachement immédiat : ajouter un contact depuis une fiche client ne
    # doit pas imposer deux écrans (§18).
    client_id: Optional[int] = None
    job_title: str = ""
    commercial_role: str = "other"
    start_date: Optional[str] = None


class PersonUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    notes: Optional[str] = None


class AffiliationCreate(BaseModel):
    client_id: int
    job_title: str = ""
    commercial_role: str = "other"
    start_date: str
    notes: Optional[str] = None


class AffiliationUpdate(BaseModel):
    """Ce qu'on peut corriger sur une affiliation : sa description, jamais son
    rattachement. `client_id` et `person_id` sont volontairement absents — les
    changer réécrirait l'appartenance de tout ce qui pend à cette période."""
    job_title: Optional[str] = None
    commercial_role: Optional[str] = None
    start_date: Optional[str] = None
    notes: Optional[str] = None


class ChangeCompany(BaseModel):
    new_client_id: int
    start_date: str
    job_title: str = ""
    commercial_role: str = "other"
    end_date_previous: Optional[str] = None
    notes: Optional[str] = None


class CloseAffiliation(BaseModel):
    end_date: str


class ContactCoverageUpsert(BaseModel):
    user_id: int
    coverage_role: str = "primary"


# ── Portée ────────────────────────────────────────────────────────────

def _scoped_person(session: Session, person_id: int, current: User) -> Person:
    personne = session.get(Person, person_id)
    if personne is None or personne.entity_id != current.entity_id:
        raise HTTPException(404, "Personne introuvable")
    return personne


def _scoped_client(session: Session, client_id: int, current: User) -> Client:
    client = session.get(Client, client_id)
    if client is None or client.entity_id != current.entity_id:
        raise HTTPException(404, "Client introuvable")
    return client


def _affiliation_rendue(session: Session, affiliation: Affiliation) -> dict:
    client = session.get(Client, affiliation.client_id)
    return {
        "id": affiliation.id,
        "client_id": affiliation.client_id,
        "client_name": client.name if client else None,
        "job_title": affiliation.job_title,
        "commercial_role": affiliation.commercial_role,
        "start_date": affiliation.start_date,
        "end_date": affiliation.end_date,
        "is_current": affiliation.end_date is None,
        "notes": affiliation.notes,
    }


def _rendu(session: Session, personne: Person, *, detail: bool = False) -> dict:
    courante = current_affiliation(session, personne.id)
    base = {
        "id": personne.id,
        "first_name": personne.first_name,
        "last_name": personne.last_name,
        "email": personne.email,
        "phone": personne.phone,
        "notes": personne.notes,
        "is_active": personne.is_active,
        "current_affiliation": (_affiliation_rendue(session, courante)
                                if courante else None),
        "created_at": personne.created_at.isoformat(),
        "updated_at": personne.updated_at.isoformat(),
    }
    if detail:
        affiliations = session.exec(
            select(Affiliation).where(Affiliation.person_id == personne.id)).all()
        # L'affiliation ouverte d'abord, puis les précédentes de la plus récente
        # à la plus ancienne — l'ordre dans lequel une fiche se lit (§57).
        base["affiliations"] = sorted(
            (_affiliation_rendue(session, a) for a in affiliations),
            key=lambda d: (d["end_date"] is not None, d["start_date"] or ""),
            reverse=False)
        base["affiliations"].sort(
            key=lambda d: (d["end_date"] is not None,
                           "" if d["end_date"] is None else d["end_date"]),
            reverse=False)
        base["history"] = person_history_counts(session, personne.id)
    return base


# ── Lecture ───────────────────────────────────────────────────────────

@router.get("")
def list_persons(
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    client_id: Optional[int] = Query(None, description="Affiliés à ce client"),
    commercial_role: Optional[str] = Query(None),
    include_inactive: bool = Query(False),
    search: Optional[str] = Query(None),
):
    requete = select(Person).where(Person.entity_id == current.entity_id)
    if not include_inactive:
        requete = requete.where(Person.is_active.is_(True))
    personnes = list(session.exec(requete).all())

    if client_id is not None or commercial_role is not None:
        filtre = select(Affiliation).where(Affiliation.end_date.is_(None))
        if client_id is not None:
            filtre = filtre.where(Affiliation.client_id == client_id)
        if commercial_role is not None:
            filtre = filtre.where(Affiliation.commercial_role == commercial_role)
        retenus = {a.person_id for a in session.exec(filtre).all()}
        personnes = [p for p in personnes if p.id in retenus]

    if search:
        terme = search.strip().casefold()
        personnes = [
            p for p in personnes
            if terme in f"{p.first_name} {p.last_name}".casefold()
            or terme in (p.email or "").casefold()
        ]

    return [_rendu(session, p) for p in
            sorted(personnes, key=lambda p: (p.last_name.casefold(),
                                             p.first_name.casefold()))]


@router.get("/duplicates")
def search_duplicates(
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    first_name: str = Query(""),
    last_name: str = Query(""),
    email: Optional[str] = Query(None),
):
    """Interrogé AVANT la création, depuis l'écran : c'est le cas §20 — Jean
    Dupont qui rejoint une nouvelle société doit se voir proposer son propre
    dossier plutôt qu'un second."""
    return find_person_duplicates(
        session, first_name=first_name, last_name=last_name, email=email,
        entity_id=current.entity_id)


@router.get("/{person_id}")
def get_person(
    person_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    return _rendu(session, _scoped_person(session, person_id, current), detail=True)


# ── Écriture ──────────────────────────────────────────────────────────

@router.post("", status_code=201)
def create_person(
    body: PersonCreate,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    prenom, nom = (body.first_name or "").strip(), (body.last_name or "").strip()
    if not nom:
        raise HTTPException(422, "Le nom est requis.")

    doublons = find_person_duplicates(
        session, first_name=prenom, last_name=nom, email=body.email,
        entity_id=current.entity_id)
    if doublons and not body.confirm_duplicate:
        raise HTTPException(409, detail={
            "code": "PERSON_DUPLICATE_SUSPECTED",
            "message": ("Cette personne existe peut-être déjà. Rattachez-lui une "
                        "nouvelle affiliation plutôt que de créer un second dossier, "
                        "ou confirmez qu'il s'agit bien de quelqu'un d'autre."),
            "duplicates": doublons,
        })

    if body.client_id is not None:
        _scoped_client(session, body.client_id, current)
        try:
            validate_commercial_role(body.commercial_role)
        except ClientRuleError as erreur:
            raise HTTPException(422, erreur.message)

    personne = Person(entity_id=current.entity_id, first_name=prenom,
                      last_name=nom, email=body.email, phone=body.phone,
                      notes=body.notes, created_by_user_id=current.id)
    session.add(personne)
    session.flush()

    affiliation = None
    if body.client_id is not None:
        affiliation = Affiliation(
            person_id=personne.id, client_id=body.client_id,
            job_title=body.job_title, commercial_role=body.commercial_role,
            start_date=(body.start_date or datetime.utcnow().date().isoformat()))
        session.add(affiliation)
        session.flush()
        session.add(ContactCoverage(user_id=current.id,
                                    affiliation_id=affiliation.id,
                                    coverage_role="primary"))

    record_audit_event(
        session, action="PERSON_CREATED", object_type="person",
        object_id=personne.id, actor_user_id=current.id, result="SUCCESS",
        after={"name": f"{prenom} {nom}".strip(),
               "client_id": body.client_id})
    session.commit()
    session.refresh(personne)
    return _rendu(session, personne, detail=True)


@router.patch("/{person_id}")
def update_person(
    person_id: int,
    body: PersonUpdate,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    personne = _scoped_person(session, person_id, current)
    for champ in ("first_name", "last_name", "email", "phone", "notes"):
        valeur = getattr(body, champ)
        if valeur is not None:
            setattr(personne, champ, valeur.strip() if isinstance(valeur, str)
                    else valeur)
    if not personne.last_name:
        raise HTTPException(422, "Le nom ne peut pas être vide.")
    personne.updated_at = datetime.utcnow()
    session.add(personne)
    session.commit()
    session.refresh(personne)
    return _rendu(session, personne, detail=True)


@router.post("/{person_id}/deactivate")
def deactivate_person(
    person_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    personne = _scoped_person(session, person_id, current)
    personne.is_active = False
    personne.updated_at = datetime.utcnow()
    session.add(personne)
    record_audit_event(
        session, action="PERSON_DEACTIVATED", object_type="person",
        object_id=personne.id, actor_user_id=current.id, result="SUCCESS")
    session.commit()
    session.refresh(personne)
    return _rendu(session, personne, detail=True)


@router.post("/{person_id}/reactivate")
def reactivate_person(
    person_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    personne = _scoped_person(session, person_id, current)
    personne.is_active = True
    personne.updated_at = datetime.utcnow()
    session.add(personne)
    record_audit_event(
        session, action="PERSON_REACTIVATED", object_type="person",
        object_id=personne.id, actor_user_id=current.id, result="SUCCESS")
    session.commit()
    session.refresh(personne)
    return _rendu(session, personne, detail=True)


@router.delete("/{person_id}", status_code=204)
def delete_person(
    person_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    personne = _scoped_person(session, person_id, current)
    try:
        require_person_deletable(session, personne.id)
    except ClientRuleError as erreur:
        commit_rejection(
            session, action="PERSON_DELETE_REJECTED", object_type="person",
            object_id=personne.id, actor_user_id=current.id, reason=erreur.code,
            metadata=person_history_counts(session, personne.id))
        raise HTTPException(409, detail=erreur.as_dict())
    record_audit_event(
        session, action="PERSON_DELETED", object_type="person",
        object_id=personne.id, actor_user_id=current.id, result="SUCCESS",
        before={"name": f"{personne.first_name} {personne.last_name}".strip()})
    session.delete(personne)
    session.commit()


# ── Affiliations ──────────────────────────────────────────────────────

@router.get("/{person_id}/affiliations")
def list_affiliations(
    person_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    personne = _scoped_person(session, person_id, current)
    affiliations = session.exec(
        select(Affiliation).where(Affiliation.person_id == personne.id)).all()
    return sorted((_affiliation_rendue(session, a) for a in affiliations),
                  key=lambda d: (d["end_date"] is not None,
                                 d["start_date"] or ""), reverse=True)


@router.post("/{person_id}/affiliations", status_code=201)
def create_affiliation(
    person_id: int,
    body: AffiliationCreate,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    """Ouvre une affiliation sans en clore une autre.

    Sert au premier rattachement d'une personne, ou aux cas professionnels
    réels de double casquette. Pour un changement d'employeur, utiliser
    `change-company` : c'est lui qui garantit qu'aucun état intermédiaire
    incohérent n'existe.
    """
    personne = _scoped_person(session, person_id, current)
    _scoped_client(session, body.client_id, current)
    try:
        validate_commercial_role(body.commercial_role)
    except ClientRuleError as erreur:
        raise HTTPException(422, erreur.message)

    affiliation = Affiliation(
        person_id=personne.id, client_id=body.client_id,
        job_title=body.job_title, commercial_role=body.commercial_role,
        start_date=body.start_date, notes=body.notes)
    session.add(affiliation)
    session.flush()
    record_audit_event(
        session, action="AFFILIATION_CREATED", object_type="affiliation",
        object_id=affiliation.id, actor_user_id=current.id, result="SUCCESS",
        after={"person_id": personne.id, "client_id": body.client_id,
               "start_date": body.start_date})
    session.commit()
    session.refresh(affiliation)
    return _affiliation_rendue(session, affiliation)


@router.patch("/{person_id}/affiliations/{affiliation_id}")
def update_affiliation(
    person_id: int,
    affiliation_id: int,
    body: AffiliationUpdate,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    """Corrige la description d'une affiliation — pas son rattachement.

    `client_id` n'est pas modifiable, et ce n'est pas un oubli : déplacer une
    affiliation d'une société à l'autre emporterait avec elle toutes les
    interactions, opportunités et trades qui y pendent. Une erreur de société
    se répare en supprimant l'affiliation tant qu'elle est vierge, puis en la
    recréant au bon endroit.
    """
    _scoped_person(session, person_id, current)
    affiliation = session.get(Affiliation, affiliation_id)
    if affiliation is None or affiliation.person_id != person_id:
        raise HTTPException(404, "Affiliation introuvable")

    if body.commercial_role is not None:
        try:
            validate_commercial_role(body.commercial_role)
        except ClientRuleError as erreur:
            raise HTTPException(422, erreur.message)
        affiliation.commercial_role = body.commercial_role
    for champ in ("job_title", "start_date", "notes"):
        valeur = getattr(body, champ)
        if valeur is not None:
            setattr(affiliation, champ, valeur)
    affiliation.updated_at = datetime.utcnow()
    session.add(affiliation)
    session.commit()
    session.refresh(affiliation)
    return _affiliation_rendue(session, affiliation)


@router.post("/{person_id}/affiliations/{affiliation_id}/close")
def close_person_affiliation(
    person_id: int,
    affiliation_id: int,
    body: CloseAffiliation,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    """Un départ sans successeur connu — on ferme une période, on n'efface pas
    un passage."""
    _scoped_person(session, person_id, current)
    affiliation = session.get(Affiliation, affiliation_id)
    if affiliation is None or affiliation.person_id != person_id:
        raise HTTPException(404, "Affiliation introuvable")
    try:
        close_affiliation(session, affiliation_id, body.end_date)
    except ClientRuleError as erreur:
        raise HTTPException(422, erreur.message)
    record_audit_event(
        session, action="AFFILIATION_CLOSED", object_type="affiliation",
        object_id=affiliation.id, actor_user_id=current.id, result="SUCCESS",
        after={"end_date": body.end_date})
    session.commit()
    session.refresh(affiliation)
    return _affiliation_rendue(session, affiliation)


@router.delete("/{person_id}/affiliations/{affiliation_id}", status_code=204)
def delete_affiliation(
    person_id: int,
    affiliation_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    """Supprime une affiliation VIERGE — la réparation d'une erreur de saisie.

    Dès qu'une opportunité ou un trade s'y rattache, on refuse : supprimer
    l'affiliation les rendrait orphelins et effacerait le contexte qui dit chez
    qui la personne se trouvait à ce moment-là.
    """
    _scoped_person(session, person_id, current)
    affiliation = session.get(Affiliation, affiliation_id)
    if affiliation is None or affiliation.person_id != person_id:
        raise HTTPException(404, "Affiliation introuvable")

    portant = {
        "opportunities": len(session.exec(
            select(Opportunity).where(
                Opportunity.primary_affiliation_id == affiliation.id)).all()),
        "participations": len(session.exec(
            select(OpportunityParticipant).where(
                OpportunityParticipant.affiliation_id == affiliation.id)).all()),
        "deals": len(session.exec(
            select(Deal).where(
                Deal.primary_affiliation_id == affiliation.id)).all()),
    }
    if any(portant.values()):
        detail = ", ".join(f"{v} {k}" for k, v in portant.items() if v)
        commit_rejection(
            session, action="AFFILIATION_DELETE_REJECTED",
            object_type="affiliation", object_id=affiliation.id,
            actor_user_id=current.id, reason="AFFILIATION_HAS_HISTORY",
            metadata=portant)
        raise HTTPException(409, detail={
            "code": "AFFILIATION_HAS_HISTORY",
            "message": (f"Ce passage porte {detail}. Clôturez-le avec une date de "
                        f"fin plutôt que de le supprimer — l'historique doit rester "
                        f"rattaché à la société de l'époque."),
        })

    for ligne in session.exec(
            select(ContactCoverage).where(
                ContactCoverage.affiliation_id == affiliation.id)).all():
        session.delete(ligne)
    record_audit_event(
        session, action="AFFILIATION_DELETED", object_type="affiliation",
        object_id=affiliation.id, actor_user_id=current.id, result="SUCCESS",
        before={"person_id": person_id, "client_id": affiliation.client_id})
    session.delete(affiliation)
    session.commit()


@router.post("/{person_id}/change-company")
def change_person_company(
    person_id: int,
    body: ChangeCompany,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    """Clôt l'affiliation en cours et en ouvre une nouvelle, d'un seul geste.

    Les deux écritures partagent la session : si la seconde échoue, la première
    n'est jamais validée. Une clôture sans réouverture laisserait la personne
    sans employeur, une réouverture sans clôture lui en donnerait deux — ni
    l'un ni l'autre n'est un état atteignable.

    Rien de ce qui pend à l'ancienne affiliation ne bouge. C'est tout l'objet
    du modèle.
    """
    personne = _scoped_person(session, person_id, current)
    _scoped_client(session, body.new_client_id, current)
    try:
        ancienne, nouvelle = change_company(
            session, person_id=personne.id, new_client_id=body.new_client_id,
            start_date=body.start_date, job_title=body.job_title,
            commercial_role=body.commercial_role,
            end_date_previous=body.end_date_previous, notes=body.notes)
    except ClientRuleError as erreur:
        session.rollback()
        commit_rejection(
            session, action="AFFILIATION_CHANGE_REJECTED", object_type="person",
            object_id=personne.id, actor_user_id=current.id, reason=erreur.code)
        raise HTTPException(422, detail=erreur.as_dict())

    session.add(ContactCoverage(user_id=current.id, affiliation_id=nouvelle.id,
                                coverage_role="primary"))
    record_audit_event(
        session, action="AFFILIATION_CHANGED", object_type="person",
        object_id=personne.id, actor_user_id=current.id, result="SUCCESS",
        before=({"affiliation_id": ancienne.id, "client_id": ancienne.client_id,
                 "end_date": ancienne.end_date} if ancienne else None),
        after={"affiliation_id": nouvelle.id, "client_id": nouvelle.client_id,
               "start_date": nouvelle.start_date})
    session.commit()
    session.refresh(personne)
    return _rendu(session, personne, detail=True)


# ── Couverture des contacts ───────────────────────────────────────────

@router.put("/{person_id}/affiliations/{affiliation_id}/coverage")
def upsert_contact_coverage(
    person_id: int,
    affiliation_id: int,
    body: ContactCoverageUpsert,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    """Deux commerciaux peuvent couvrir le même client sur des contacts
    différents — l'un le CIO, l'autre les conseillers (§14)."""
    _scoped_person(session, person_id, current)
    affiliation = session.get(Affiliation, affiliation_id)
    if affiliation is None or affiliation.person_id != person_id:
        raise HTTPException(404, "Affiliation introuvable")
    try:
        validate_coverage_role(body.coverage_role)
    except ClientRuleError as erreur:
        raise HTTPException(422, erreur.message)

    cible = session.get(User, body.user_id)
    if cible is None or cible.entity_id != current.entity_id:
        raise HTTPException(404, "Utilisateur introuvable")

    existant = session.exec(
        select(ContactCoverage).where(
            ContactCoverage.affiliation_id == affiliation_id,
            ContactCoverage.user_id == body.user_id)).first()
    if existant is None:
        existant = ContactCoverage(user_id=body.user_id,
                                   affiliation_id=affiliation_id,
                                   coverage_role=body.coverage_role)
    else:
        existant.coverage_role = body.coverage_role
    session.add(existant)
    session.commit()
    return {"affiliation_id": affiliation_id, "user_id": body.user_id,
            "coverage_role": body.coverage_role}
