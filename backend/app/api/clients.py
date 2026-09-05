"""Clients — l'organisation cliente, sa couverture et ses contraintes.

Portée : le client appartient à l'ENTITÉ, pas à l'utilisateur. Deux commerciaux
qui couvrent ABC Asset Management doivent voir une seule fiche, sinon les
statistiques de Client Intelligence compteraient deux sociétés là où il n'y en
a qu'une. Qui couvre quoi se lit dans `client_coverage` et se filtre à la
demande, jamais en dupliquant la ligne.

Toutes les vérifications d'appartenance sont ici, pas dans l'écran : un
`GET /api/clients/123` lancé à la main doit se heurter au même refus que
l'interface.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session, select

from ..core.audit import commit_rejection, record_audit_event
from ..core.client_constraints_ref import (
    ConstraintRefError, catalog_options, definitions_for,
    validate_constraints_against,
)
from ..core.client_intelligence import declared_preferences, preference_history
from ..core.client_controls import (
    ClientRuleError, apply_constraints, client_history_counts,
    find_client_duplicates, read_constraints, require_client_deletable,
    validate_client_status, validate_client_type, validate_coverage_role,
    validate_data_origin,
    validate_mandate_status, validate_mandate_type,
    validate_scalar_constraints,
)
from ..db.database import get_session
from ..db.models import (
    Affiliation, Client, ClientCoverage, ClientMandate,
    ClientPreferenceStatement, Deal, Interaction, Opportunity, Person, User,
)
from .auth import get_current_user

router = APIRouter(prefix="/api/clients", tags=["clients"])


# ── Schémas ───────────────────────────────────────────────────────────

class ClientCreate(BaseModel):
    name: str
    legal_name: Optional[str] = None
    client_type: str = "other"
    country: Optional[str] = None
    status: str = "prospect"
    external_ref: Optional[str] = None
    notes: Optional[str] = None
    data_origin: str = "demo"
    # Confirmation explicite après un avertissement de doublon. Sans elle, un
    # doublon probable est signalé et l'écriture suspendue — §21 : on avertit,
    # on ne bloque pas, mais on ne crée pas non plus dans le dos de personne.
    confirm_duplicate: bool = False


class ClientUpdate(BaseModel):
    name: Optional[str] = None
    legal_name: Optional[str] = None
    client_type: Optional[str] = None
    country: Optional[str] = None
    status: Optional[str] = None
    external_ref: Optional[str] = None
    notes: Optional[str] = None
    data_origin: Optional[str] = None


class PreferenceEvidence(BaseModel):
    # A save without evidence remains a commercial recording, never a client
    # declaration invented by the application.
    statement_kind: str = "sales_note"
    statement_date: str = ""
    source_affiliation_id: Optional[int] = None
    channel: Optional[str] = None
    interaction_id: Optional[int] = None
    note: Optional[str] = None


class ScalarConstraintsUpdate(BaseModel):
    ticket_min: Optional[float] = None
    ticket_max: Optional[float] = None
    ticket_currency: Optional[str] = None
    maturity_min_months: Optional[int] = None
    maturity_max_months: Optional[int] = None
    min_rating: Optional[str] = None
    max_concentration_pct: Optional[float] = None
    evidence: Optional[PreferenceEvidence] = None


class ConstraintsUpdate(BaseModel):
    """Le blob de listes, sous verrou optimiste.

    `constraints_version` est obligatoire : c'est la version que l'écran avait
    sous les yeux. Si elle a bougé entre-temps, l'écriture est refusée plutôt
    qu'appliquée par-dessus le travail de quelqu'un d'autre.
    """
    constraints: dict
    constraints_version: int
    evidence: Optional[PreferenceEvidence] = None


class ScopedPreferencesUpdate(BaseModel):
    preferences: dict
    preferences_version: int
    mandate_id: Optional[int] = None
    affiliation_id: Optional[int] = None
    evidence: Optional[PreferenceEvidence] = None


class CoverageUpsert(BaseModel):
    user_id: int
    coverage_role: str = "primary"


class MandateCreate(BaseModel):
    name: str
    mandate_type: str = "mandate"
    reference_currency: Optional[str] = None
    comment: Optional[str] = None
    data_origin: Optional[str] = None


class MandateUpdate(BaseModel):
    name: Optional[str] = None
    mandate_type: Optional[str] = None
    status: Optional[str] = None
    reference_currency: Optional[str] = None
    comment: Optional[str] = None
    data_origin: Optional[str] = None


# ── Portée ────────────────────────────────────────────────────────────

def _scoped_client(session: Session, client_id: int, current: User) -> Client:
    """Le client, s'il est visible par cet utilisateur.

    404 et non 403 : répondre « interdit » confirmerait l'existence d'une fiche
    d'une autre entité, ce qui est déjà une information. Même choix que le reste
    de l'application.
    """
    client = session.get(Client, client_id)
    if client is None or client.entity_id != current.entity_id:
        raise HTTPException(404, "Client introuvable")
    return client


_PREFERENCE_KINDS = {
    "client_declared", "client_confirmed", "client_contradicted", "sales_note",
}
_PREFERENCE_CHANNELS = {"meeting", "phone", "email", "other"}


def _validate_preference_scope(
    session: Session, client: Client, *, mandate_id: Optional[int],
    affiliation_id: Optional[int],
) -> None:
    if mandate_id is not None:
        mandate = session.get(ClientMandate, mandate_id)
        if mandate is None or mandate.client_id != client.id:
            raise HTTPException(404, "Mandat introuvable")
    if affiliation_id is not None:
        affiliation = session.get(Affiliation, affiliation_id)
        if affiliation is None or affiliation.client_id != client.id:
            raise HTTPException(404, "Affiliation introuvable")


def _preference_evidence(
    session: Session, client: Client, evidence: Optional[PreferenceEvidence],
) -> dict:
    evidence = evidence or PreferenceEvidence()
    if evidence.statement_kind not in _PREFERENCE_KINDS:
        raise HTTPException(422, detail={
            "code": "PREFERENCE_KIND_INVALID",
            "message": "Nature de préférence inconnue.",
            "expected": sorted(_PREFERENCE_KINDS),
            "received": evidence.statement_kind,
        })
    statement_date = evidence.statement_date or date.today().isoformat()
    try:
        date.fromisoformat(statement_date)
    except ValueError:
        raise HTTPException(422, "La date de déclaration doit être au format AAAA-MM-JJ.")
    channel = evidence.channel or None
    if channel is not None and channel not in _PREFERENCE_CHANNELS:
        raise HTTPException(422, detail={
            "code": "PREFERENCE_CHANNEL_INVALID",
            "message": "Canal de déclaration inconnu.",
            "expected": sorted(_PREFERENCE_CHANNELS),
            "received": channel,
        })
    if evidence.source_affiliation_id is not None:
        source = session.get(Affiliation, evidence.source_affiliation_id)
        if source is None or source.client_id != client.id:
            raise HTTPException(404, "Contact source introuvable pour ce Client")
    if evidence.interaction_id is not None:
        interaction = session.get(Interaction, evidence.interaction_id)
        if interaction is None or interaction.client_id != client.id:
            raise HTTPException(404, "Interaction source introuvable pour ce Client")
    return {
        "statement_kind": evidence.statement_kind,
        "statement_date": statement_date,
        "source_affiliation_id": evidence.source_affiliation_id,
        "channel": channel,
        "interaction_id": evidence.interaction_id,
        "note": str(evidence.note or "").strip() or None,
    }


def _record_preference_changes(
    session: Session, *, client: Client, current: User,
    before: dict, after: dict, evidence: Optional[PreferenceEvidence],
    mandate_id: Optional[int] = None, affiliation_id: Optional[int] = None,
) -> list[ClientPreferenceStatement]:
    _validate_preference_scope(
        session, client, mandate_id=mandate_id, affiliation_id=affiliation_id)
    metadata = _preference_evidence(session, client, evidence)
    created = []
    existing_query = select(ClientPreferenceStatement).where(
        ClientPreferenceStatement.client_id == client.id)
    existing_query = (existing_query.where(
        ClientPreferenceStatement.mandate_id == mandate_id)
        if mandate_id is not None else existing_query.where(
            ClientPreferenceStatement.mandate_id.is_(None)))
    existing_query = (existing_query.where(
        ClientPreferenceStatement.affiliation_id == affiliation_id)
        if affiliation_id is not None else existing_query.where(
            ClientPreferenceStatement.affiliation_id.is_(None)))
    existing_keys = {
        row.preference_key for row in session.exec(existing_query).all()}
    for key in sorted(set(before) | set(after)):
        if before.get(key) == after.get(key) and (key in before) == (key in after):
            continue
        # The pre-Lot-2 projection has no defensible effective date.  Preserve
        # it once as an explicitly undated baseline before the first change;
        # this makes later as-of replay possible without inventing history.
        if key in before and key not in existing_keys:
            baseline = ClientPreferenceStatement(
                entity_id=client.entity_id, client_id=client.id,
                mandate_id=mandate_id, affiliation_id=affiliation_id,
                preference_key=key,
                value_json=json.dumps(before.get(key), ensure_ascii=False),
                statement_kind="legacy_snapshot", statement_date="",
                note="État antérieur non daté lors de l'activation de l'historique.",
                recorded_by_user_id=current.id)
            session.add(baseline)
            created.append(baseline)
        row = ClientPreferenceStatement(
            entity_id=client.entity_id,
            client_id=client.id,
            mandate_id=mandate_id,
            affiliation_id=affiliation_id,
            preference_key=key,
            value_json=json.dumps(after.get(key), ensure_ascii=False),
            recorded_by_user_id=current.id,
            **metadata,
        )
        session.add(row)
        created.append(row)
    return created


def _coverage_of(session: Session, client_id: int) -> list[dict]:
    lignes = session.exec(
        select(ClientCoverage).where(ClientCoverage.client_id == client_id)).all()
    sortie = []
    for ligne in lignes:
        utilisateur = session.get(User, ligne.user_id)
        sortie.append({
            "user_id": ligne.user_id,
            "username": utilisateur.username if utilisateur else None,
            "coverage_role": ligne.coverage_role,
        })
    return sorted(sortie, key=lambda d: (d["coverage_role"] != "primary",
                                         d["username"] or ""))


def _mandate_row(mandate: ClientMandate) -> dict:
    return {
        "id": mandate.id,
        "client_id": mandate.client_id,
        "mandate_type": mandate.mandate_type,
        "name": mandate.name,
        "status": mandate.status,
        "reference_currency": mandate.reference_currency,
        "comment": mandate.comment,
        "data_origin": mandate.data_origin,
        "created_at": mandate.created_at.isoformat(),
        "updated_at": mandate.updated_at.isoformat(),
    }


def _mandates_of(session: Session, client_id: int, *, include_archived: bool) -> list[dict]:
    query = select(ClientMandate).where(ClientMandate.client_id == client_id)
    if not include_archived:
        query = query.where(ClientMandate.status == "active")
    rows = session.exec(query).all()
    return [_mandate_row(row) for row in sorted(
        rows, key=lambda item: (item.status != "active", item.name.casefold()))]


def _rendu(session: Session, client: Client, *, detail: bool = False) -> dict:
    base = {
        "id": client.id,
        "name": client.name,
        "legal_name": client.legal_name,
        "client_type": client.client_type,
        "country": client.country,
        "status": client.status,
        "external_ref": client.external_ref,
        "notes": client.notes,
        "data_origin": client.data_origin,
        "ticket_min": client.ticket_min,
        "ticket_max": client.ticket_max,
        "ticket_currency": client.ticket_currency,
        "maturity_min_months": client.maturity_min_months,
        "maturity_max_months": client.maturity_max_months,
        "min_rating": client.min_rating,
        "max_concentration_pct": client.max_concentration_pct,
        "constraints": read_constraints(client),
        "constraints_version": client.constraints_version,
        "created_at": client.created_at.isoformat(),
        "updated_at": client.updated_at.isoformat(),
    }
    if detail:
        base["coverage"] = _coverage_of(session, client.id)
        base["history"] = client_history_counts(session, client.id)
        base["mandates"] = _mandates_of(session, client.id, include_archived=True)
    return base


# ── Lecture ───────────────────────────────────────────────────────────

@router.get("")
def list_clients(
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    status: Optional[str] = Query(None),
    client_type: Optional[str] = Query(None),
    country: Optional[str] = Query(None),
    mine: bool = Query(False, description="Restreindre à mes clients couverts"),
    include_archived: bool = Query(False),
):
    """La liste, filtrée côté serveur.

    Les clients archivés sortent par défaut : ils ne disparaissent pas de la
    base — leur historique reste lisible par Client Intelligence — mais ils
    n'encombrent pas l'écran de travail.
    """
    requete = select(Client).where(Client.entity_id == current.entity_id)
    if status:
        requete = requete.where(Client.status == status)
    elif not include_archived:
        requete = requete.where(Client.status != "archived")
    if client_type:
        requete = requete.where(Client.client_type == client_type)
    if country:
        requete = requete.where(Client.country == country)

    clients = list(session.exec(requete).all())

    if mine:
        couverts = {
            c.client_id for c in session.exec(
                select(ClientCoverage).where(ClientCoverage.user_id == current.id)
            ).all()
        }
        clients = [c for c in clients if c.id in couverts]

    # Une seule requête pour toute la couverture plutôt qu'une par client :
    # la liste doit rester plate en nombre de requêtes quand elle grandit (§68).
    ids = [c.id for c in clients]
    couverture: dict[int, list[str]] = {}
    if ids:
        for ligne in session.exec(
                select(ClientCoverage).where(ClientCoverage.client_id.in_(ids))).all():
            utilisateur = session.get(User, ligne.user_id)
            couverture.setdefault(ligne.client_id, []).append(
                utilisateur.username if utilisateur else f"#{ligne.user_id}")

    sortie = []
    for client in sorted(clients, key=lambda c: c.name.casefold()):
        ligne = _rendu(session, client)
        ligne["coverage_usernames"] = sorted(couverture.get(client.id, []))
        sortie.append(ligne)
    return sortie


@router.get("/{client_id}")
def get_client(
    client_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    return _rendu(session, _scoped_client(session, client_id, current), detail=True)


@router.get("/{client_id}/contacts")
def list_client_contacts(
    client_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    include_former: bool = Query(False),
):
    """Les contacts du client — actifs par défaut, anciens sur demande.

    C'est cette liste que le sélecteur d'une opportunité consomme : on
    n'ouvre pas un dossier avec quelqu'un qui a quitté la maison. Les anciens
    restent accessibles pour les vues d'historique.
    """
    client = _scoped_client(session, client_id, current)
    requete = select(Affiliation).where(Affiliation.client_id == client.id)
    if not include_former:
        requete = requete.where(Affiliation.end_date.is_(None))
    affiliations = list(session.exec(requete).all())

    sortie = []
    for affiliation in affiliations:
        personne = session.get(Person, affiliation.person_id)
        sortie.append({
            "affiliation_id": affiliation.id,
            "person_id": affiliation.person_id,
            "first_name": personne.first_name if personne else "",
            "last_name": personne.last_name if personne else "",
            "email": personne.email if personne else None,
            "job_title": affiliation.job_title,
            "commercial_role": affiliation.commercial_role,
            "start_date": affiliation.start_date,
            "end_date": affiliation.end_date,
            "is_current": affiliation.end_date is None,
        })
    return sorted(sortie, key=lambda d: (d["end_date"] is not None,
                                         d["last_name"].casefold()))


@router.get("/{client_id}/mandates")
def list_client_mandates(
    client_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    include_archived: bool = Query(False),
):
    client = _scoped_client(session, client_id, current)
    return _mandates_of(session, client.id, include_archived=include_archived)


def _mandate_name_available(
    session: Session, client_id: int, name: str, *, exclude_id: Optional[int] = None,
) -> None:
    normalized = name.casefold()
    duplicate = next((row for row in session.exec(
        select(ClientMandate).where(ClientMandate.client_id == client_id)).all()
        if row.id != exclude_id and row.name.casefold() == normalized), None)
    if duplicate:
        raise HTTPException(409, detail={
            "code": "MANDATE_DUPLICATE",
            "message": f"Un périmètre nommé « {duplicate.name} » existe déjà pour ce Client.",
        })


@router.post("/{client_id}/mandates", status_code=201)
def create_client_mandate(
    client_id: int,
    body: MandateCreate,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    client = _scoped_client(session, client_id, current)
    name = body.name.strip()
    if not name:
        raise HTTPException(422, "Le nom du mandat ou périmètre est requis.")
    try:
        validate_mandate_type(body.mandate_type)
        origin = validate_data_origin(body.data_origin or client.data_origin)
    except ClientRuleError as error:
        raise HTTPException(422, detail=error.as_dict())
    _mandate_name_available(session, client.id, name)
    mandate = ClientMandate(
        entity_id=current.entity_id,
        client_id=client.id,
        mandate_type=body.mandate_type,
        name=name,
        status="active",
        reference_currency=(body.reference_currency or None),
        comment=body.comment,
        data_origin=origin,
        created_by_user_id=current.id,
    )
    session.add(mandate)
    session.flush()
    record_audit_event(
        session, action="CLIENT_MANDATE_CREATED", object_type="client_mandate",
        object_id=mandate.id, actor_user_id=current.id, result="SUCCESS",
        after=_mandate_row(mandate), metadata={"client_id": client.id})
    session.commit()
    session.refresh(mandate)
    return _mandate_row(mandate)


@router.patch("/{client_id}/mandates/{mandate_id}")
def update_client_mandate(
    client_id: int,
    mandate_id: int,
    body: MandateUpdate,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    client = _scoped_client(session, client_id, current)
    mandate = session.get(ClientMandate, mandate_id)
    if mandate is None or mandate.client_id != client.id:
        raise HTTPException(404, "Mandat introuvable")
    before = _mandate_row(mandate)
    if body.name is not None:
        name = body.name.strip()
        if not name:
            raise HTTPException(422, "Le nom du mandat ou périmètre est requis.")
        _mandate_name_available(session, client.id, name, exclude_id=mandate.id)
        mandate.name = name
    try:
        if body.mandate_type is not None:
            validate_mandate_type(body.mandate_type)
            mandate.mandate_type = body.mandate_type
        if body.status is not None:
            validate_mandate_status(body.status)
            mandate.status = body.status
        if body.data_origin is not None:
            mandate.data_origin = validate_data_origin(body.data_origin)
    except ClientRuleError as error:
        raise HTTPException(422, detail=error.as_dict())
    if "reference_currency" in body.model_fields_set:
        mandate.reference_currency = body.reference_currency or None
    if "comment" in body.model_fields_set:
        mandate.comment = body.comment or None
    mandate.updated_at = datetime.utcnow()
    session.add(mandate)
    action = ("CLIENT_MANDATE_ARCHIVED"
              if before["status"] != "archived" and mandate.status == "archived"
              else "CLIENT_MANDATE_UPDATED")
    record_audit_event(
        session, action=action, object_type="client_mandate",
        object_id=mandate.id, actor_user_id=current.id, result="SUCCESS",
        before=before, after=_mandate_row(mandate),
        metadata={"client_id": client.id})
    session.commit()
    session.refresh(mandate)
    return _mandate_row(mandate)


@router.get("/{client_id}/duplicates")
def check_client_duplicates(
    client_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    client = _scoped_client(session, client_id, current)
    return find_client_duplicates(
        session, name=client.name, legal_name=client.legal_name,
        external_ref=client.external_ref, entity_id=current.entity_id,
        exclude_id=client.id)


# ── Écriture ──────────────────────────────────────────────────────────

@router.post("", status_code=201)
def create_client(
    body: ClientCreate,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    nom = (body.name or "").strip()
    if not nom:
        raise HTTPException(422, "Le nom du client est requis.")
    try:
        validate_client_type(body.client_type)
        validate_client_status(body.status)
        data_origin = validate_data_origin(body.data_origin)
    except ClientRuleError as erreur:
        raise HTTPException(422, erreur.message)

    doublons = find_client_duplicates(
        session, name=nom, legal_name=body.legal_name,
        external_ref=body.external_ref, entity_id=current.entity_id)
    if doublons and not body.confirm_duplicate:
        # 409 plutôt que 422 : ce n'est pas une saisie invalide, c'est une
        # décision à prendre. Le corps porte de quoi la prendre.
        raise HTTPException(409, detail={
            "code": "CLIENT_DUPLICATE_SUSPECTED",
            "message": ("Un client très proche existe déjà. Confirmez s'il s'agit "
                        "bien d'une société distincte."),
            "duplicates": doublons,
        })

    client = Client(
        entity_id=current.entity_id, name=nom, legal_name=body.legal_name,
        client_type=body.client_type, country=body.country, status=body.status,
        external_ref=body.external_ref, notes=body.notes,
        data_origin=data_origin,
        created_by_user_id=current.id)
    session.add(client)
    session.flush()

    # Le créateur couvre ce qu'il crée : sans cela, un client fraîchement saisi
    # n'apparaîtrait dans la liste « mes clients » de personne.
    session.add(ClientCoverage(user_id=current.id, client_id=client.id,
                               coverage_role="primary"))
    record_audit_event(
        session, action="CLIENT_CREATED", object_type="client",
        object_id=client.id, actor_user_id=current.id, result="SUCCESS",
        after={"name": client.name, "client_type": client.client_type,
               "status": client.status, "data_origin": client.data_origin})
    session.commit()
    session.refresh(client)
    return _rendu(session, client, detail=True)


@router.patch("/{client_id}")
def update_client(
    client_id: int,
    body: ClientUpdate,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    client = _scoped_client(session, client_id, current)
    avant = {"name": client.name, "status": client.status,
             "client_type": client.client_type, "legal_name": client.legal_name,
             "country": client.country, "external_ref": client.external_ref,
             "notes": client.notes, "data_origin": client.data_origin}

    if body.client_type is not None:
        try:
            validate_client_type(body.client_type)
        except ClientRuleError as erreur:
            raise HTTPException(422, erreur.message)
        client.client_type = body.client_type
    if body.status is not None:
        try:
            validate_client_status(body.status)
        except ClientRuleError as erreur:
            raise HTTPException(422, erreur.message)
        client.status = body.status
    if body.data_origin is not None:
        try:
            client.data_origin = validate_data_origin(body.data_origin)
        except ClientRuleError as erreur:
            raise HTTPException(422, erreur.message)
    if body.name is not None:
        nom = body.name.strip()
        if not nom:
            raise HTTPException(422, "Le nom du client ne peut pas être vide.")
        client.name = nom
    for champ in ("legal_name", "country", "external_ref", "notes"):
        valeur = getattr(body, champ)
        if valeur is not None:
            setattr(client, champ, valeur)

    client.updated_at = datetime.utcnow()
    session.add(client)
    apres = {"name": client.name, "status": client.status,
             "client_type": client.client_type, "legal_name": client.legal_name,
             "country": client.country, "external_ref": client.external_ref,
             "notes": client.notes, "data_origin": client.data_origin}
    if avant != apres:
        record_audit_event(
            session, action="CLIENT_UPDATED", object_type="client",
            object_id=client.id, actor_user_id=current.id, result="SUCCESS",
            before=avant, after=apres)
    session.commit()
    session.refresh(client)
    return _rendu(session, client, detail=True)


@router.patch("/{client_id}/scalar-constraints")
def update_scalar_constraints(
    client_id: int,
    body: ScalarConstraintsUpdate,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    """Les sept scalaires — hors verrou, exprès.

    Ce sont des colonnes distinctes : deux personnes qui modifient l'une le
    ticket, l'autre la notation minimale, ne se marchent pas dessus. Le verrou
    ne protège que le blob de listes, où l'écriture est un remplacement complet.
    """
    client = _scoped_client(session, client_id, current)
    before = {
        "ticket_min": client.ticket_min, "ticket_max": client.ticket_max,
        "ticket_currency": client.ticket_currency,
        "maturity_min_months": client.maturity_min_months,
        "maturity_max_months": client.maturity_max_months,
        "min_rating": client.min_rating,
        "max_concentration_pct": client.max_concentration_pct,
    }
    fusion = {key: value for key, value in before.items()
              if key != "ticket_currency"}
    envoye = body.model_dump(exclude_unset=True, exclude={"evidence"})
    fusion.update({k: v for k, v in envoye.items() if k != "ticket_currency"})

    try:
        validate_scalar_constraints(**fusion)
    except ClientRuleError as erreur:
        raise HTTPException(422, erreur.message)

    for champ, valeur in envoye.items():
        setattr(client, champ, valeur)
    client.updated_at = datetime.utcnow()
    session.add(client)
    after = dict(before)
    after.update(envoye)
    statements = _record_preference_changes(
        session, client=client, current=current, before=before, after=after,
        evidence=body.evidence)
    if statements:
        record_audit_event(
            session, action="CLIENT_PREFERENCES_UPDATED", object_type="client",
            object_id=client.id, actor_user_id=current.id, result="SUCCESS",
            before=before, after=after,
            metadata={"statement_count": len(statements), "scope": "client"})
    session.commit()
    session.refresh(client)
    return _rendu(session, client, detail=True)


@router.get("/{client_id}/constraints/schema")
def constraints_schema(
    client_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    """Ce que l'écran doit afficher : les champs, leurs valeurs possibles, les valeurs saisies.

    L'écran ne connaît aucun champ à l'avance. C'est délibéré : le jour où un
    admin ajoute « Poche défensive max », personne ne doit avoir à redéployer le
    frontend pour qu'il s'affiche, et surtout personne ne doit pouvoir le
    décrire différemment des deux côtés. Le serveur décrit, l'écran rend.

    Les catalogues sont résolus ici, une fois, et non par champ : trois champs
    pointés sur `counterparties` ne doivent pas produire trois requêtes.
    """
    client = _scoped_client(session, client_id, current)
    valeurs = read_constraints(client)
    vivantes = definitions_for(session, entity_id=client.entity_id,
                               client_id=client.id)

    # Un champ archivé dont ce client porte encore une valeur doit rester
    # VISIBLE. L'omettre laisserait la valeur vivre dans le blob sans que
    # personne puisse la lire ni l'effacer : elle ne s'appliquerait plus, ne se
    # verrait plus, et reviendrait au premier export.
    connues = {d.key for d in vivantes}
    retirees = [
        d for d in definitions_for(session, entity_id=client.entity_id,
                                   client_id=client.id, include_archived=True)
        if d.archived and d.key not in connues and d.key in valeurs
    ]

    catalogues = {}
    for definition in vivantes:
        if definition.catalog and definition.catalog not in catalogues:
            catalogues[definition.catalog] = catalog_options(session, definition.catalog)
    return {
        "definitions": [d.as_dict() for d in vivantes],
        "retired": [d.as_dict() for d in retirees],
        "catalogs": catalogues,
        "values": valeurs,
        "constraints_version": client.constraints_version,
    }


@router.get("/{client_id}/scoped-preferences/schema")
def scoped_preferences_schema(
    client_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    mandate_id: Optional[int] = Query(None),
    affiliation_id: Optional[int] = Query(None),
):
    """Same dynamic vocabulary, scoped to one mandate or one affiliation."""
    client = _scoped_client(session, client_id, current)
    if mandate_id is None and affiliation_id is None:
        raise HTTPException(
            422, "Choisissez un mandat ou un Contact pour ce profil spécifique.")
    _validate_preference_scope(
        session, client, mandate_id=mandate_id, affiliation_id=affiliation_id)
    definitions = definitions_for(
        session, entity_id=client.entity_id, client_id=client.id)
    catalogs = {}
    for definition in definitions:
        if definition.catalog and definition.catalog not in catalogs:
            catalogs[definition.catalog] = catalog_options(
                session, definition.catalog)
    declared = declared_preferences(
        session, client_id=client.id, mandate_id=mandate_id,
        affiliation_id=affiliation_id)
    values = (declared["combined"]
              if mandate_id is not None and affiliation_id is not None
              else declared["mandate"] if mandate_id is not None
              else declared["affiliation"])
    history = preference_history(
        session, client_id=client.id, mandate_id=mandate_id,
        affiliation_id=affiliation_id)
    return {
        "definitions": [definition.as_dict() for definition in definitions],
        "retired": [],
        "catalogs": catalogs,
        "values": values,
        "preference_history": history,
        "preferences_version": max((row["id"] for row in history), default=0),
        "scope": {"mandate_id": mandate_id, "affiliation_id": affiliation_id},
    }


@router.put("/{client_id}/scoped-preferences")
def replace_scoped_preferences(
    client_id: int,
    body: ScopedPreferencesUpdate,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    client = _scoped_client(session, client_id, current)
    if body.mandate_id is None and body.affiliation_id is None:
        raise HTTPException(
            422, "Choisissez un mandat ou un Contact pour ce profil spécifique.")
    _validate_preference_scope(
        session, client, mandate_id=body.mandate_id,
        affiliation_id=body.affiliation_id)
    definitions = definitions_for(
        session, entity_id=client.entity_id, client_id=client.id,
        include_archived=True)
    try:
        normalized = validate_constraints_against(body.preferences, definitions)
    except ConstraintRefError as error:
        raise HTTPException(422, detail=error.as_dict())
    current_history = preference_history(
        session, client_id=client.id, mandate_id=body.mandate_id,
        affiliation_id=body.affiliation_id)
    current_version = max(
        (row["id"] for row in current_history), default=0)
    if body.preferences_version != current_version:
        commit_rejection(
            session, action="CLIENT_PREFERENCES_CONFLICT",
            object_type="client", object_id=client.id,
            actor_user_id=current.id, reason="PREFERENCES_VERSION_STALE",
            metadata={
                "sent_version": body.preferences_version,
                "current_version": current_version,
                "mandate_id": body.mandate_id,
                "affiliation_id": body.affiliation_id,
            })
        raise HTTPException(409, detail={
            "code": "PREFERENCES_VERSION_STALE",
            "message": (
                "Ce profil spécifique a été modifié entre-temps. "
                "Rechargez-le avant d'enregistrer."),
            "current_version": current_version,
        })
    declared = declared_preferences(
        session, client_id=client.id, mandate_id=body.mandate_id,
        affiliation_id=body.affiliation_id)
    before = (declared["combined"]
              if body.mandate_id is not None and body.affiliation_id is not None
              else declared["mandate"] if body.mandate_id is not None
              else declared["affiliation"])
    statements = _record_preference_changes(
        session, client=client, current=current, before=before, after=normalized,
        evidence=body.evidence, mandate_id=body.mandate_id,
        affiliation_id=body.affiliation_id)
    if statements:
        record_audit_event(
            session, action="CLIENT_PREFERENCES_UPDATED",
            object_type="client", object_id=client.id,
            actor_user_id=current.id, result="SUCCESS", before=before,
            after=normalized, metadata={
                "statement_count": len(statements),
                "mandate_id": body.mandate_id,
                "affiliation_id": body.affiliation_id,
            })
    session.commit()
    history = preference_history(
        session, client_id=client.id, mandate_id=body.mandate_id,
        affiliation_id=body.affiliation_id)
    return {
        "values": normalized,
        "preference_history": history,
        "preferences_version": max((row["id"] for row in history), default=0),
    }


@router.get("/{client_id}/preference-history")
def get_preference_history(
    client_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    mandate_id: Optional[int] = Query(None),
    affiliation_id: Optional[int] = Query(None),
):
    client = _scoped_client(session, client_id, current)
    _validate_preference_scope(
        session, client, mandate_id=mandate_id, affiliation_id=affiliation_id)
    return preference_history(
        session, client_id=client.id, mandate_id=mandate_id,
        affiliation_id=affiliation_id)


@router.put("/{client_id}/constraints")
def replace_constraints(
    client_id: int,
    body: ConstraintsUpdate,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    """Le blob de listes, sous verrou optimiste.

    PUT et non PATCH : l'écriture est un remplacement complet de l'objet, et
    le nommer ainsi évite de laisser croire à une fusion champ par champ qui
    n'a pas lieu.
    """
    client = _scoped_client(session, client_id, current)
    before_values = read_constraints(client)
    try:
        # Les définitions applicables à CE client : standards, plus celles
        # déclarées pour l'entité, plus celles convenues avec lui seul. Sans
        # elles, un champ pourtant déclaré serait refusé comme clé inconnue.
        #
        # `include_archived` : la validation connaît aussi les champs retirés.
        # Sinon, archiver un champ rendait irrecevable la fiche de tout client
        # qui l'avait rempli — l'écran l'affichait, l'utilisateur n'y touchait
        # pas, et l'enregistrement était refusé pour une clé qu'il n'avait
        # jamais saisie.
        definitions = definitions_for(session, entity_id=client.entity_id,
                                      client_id=client.id,
                                      include_archived=True)
        apply_constraints(client, body.constraints, body.constraints_version,
                          definitions)
    except ClientRuleError as erreur:
        if erreur.code == "CONSTRAINTS_VERSION_STALE":
            # Un conflit d'écriture est un fait à tracer : c'est la preuve que
            # deux personnes travaillaient sur la même fiche.
            commit_rejection(
                session, action="CLIENT_CONSTRAINTS_CONFLICT", object_type="client",
                object_id=client.id, actor_user_id=current.id,
                reason=erreur.code,
                metadata={"sent_version": body.constraints_version,
                          "current_version": client.constraints_version})
            raise HTTPException(409, detail=erreur.as_dict())
        raise HTTPException(422, erreur.message)

    session.add(client)
    statements = _record_preference_changes(
        session, client=client, current=current, before=before_values,
        after=read_constraints(client), evidence=body.evidence)
    record_audit_event(
        session, action="CLIENT_CONSTRAINTS_UPDATED", object_type="client",
        object_id=client.id, actor_user_id=current.id, result="SUCCESS",
        after={"version": client.constraints_version},
        metadata={"statement_count": len(statements), "scope": "client"})
    session.commit()
    session.refresh(client)
    return _rendu(session, client, detail=True)


# ── Couverture ────────────────────────────────────────────────────────

@router.put("/{client_id}/coverage")
def upsert_coverage(
    client_id: int,
    body: CoverageUpsert,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    client = _scoped_client(session, client_id, current)
    try:
        validate_coverage_role(body.coverage_role)
    except ClientRuleError as erreur:
        raise HTTPException(422, erreur.message)

    cible = session.get(User, body.user_id)
    if cible is None or cible.entity_id != current.entity_id:
        raise HTTPException(404, "Utilisateur introuvable")

    existant = session.exec(
        select(ClientCoverage).where(ClientCoverage.client_id == client.id,
                                     ClientCoverage.user_id == body.user_id)
    ).first()
    if existant is None:
        existant = ClientCoverage(user_id=body.user_id, client_id=client.id,
                                  coverage_role=body.coverage_role)
    else:
        existant.coverage_role = body.coverage_role
    session.add(existant)
    record_audit_event(
        session, action="CLIENT_COVERAGE_SET", object_type="client",
        object_id=client.id, actor_user_id=current.id, result="SUCCESS",
        after={"user_id": body.user_id, "coverage_role": body.coverage_role})
    session.commit()
    return _coverage_of(session, client.id)


@router.delete("/{client_id}/coverage/{user_id}", status_code=204)
def remove_coverage(
    client_id: int,
    user_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    client = _scoped_client(session, client_id, current)
    ligne = session.exec(
        select(ClientCoverage).where(ClientCoverage.client_id == client.id,
                                     ClientCoverage.user_id == user_id)).first()
    if ligne is None:
        raise HTTPException(404, "Couverture introuvable")
    session.delete(ligne)
    record_audit_event(
        session, action="CLIENT_COVERAGE_REMOVED", object_type="client",
        object_id=client.id, actor_user_id=current.id, result="SUCCESS",
        before={"user_id": user_id, "coverage_role": ligne.coverage_role})
    session.commit()


# ── Archivage et suppression ──────────────────────────────────────────

@router.post("/{client_id}/archive")
def archive_client(
    client_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    client = _scoped_client(session, client_id, current)
    avant = client.status
    client.status = "archived"
    client.updated_at = datetime.utcnow()
    session.add(client)
    record_audit_event(
        session, action="CLIENT_ARCHIVED", object_type="client",
        object_id=client.id, actor_user_id=current.id, result="SUCCESS",
        before={"status": avant}, after={"status": "archived"})
    session.commit()
    session.refresh(client)
    return _rendu(session, client, detail=True)


@router.post("/{client_id}/reactivate")
def reactivate_client(
    client_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    client = _scoped_client(session, client_id, current)
    if client.status != "archived":
        raise HTTPException(422, "Ce client n'est pas archivé.")
    client.status = "active"
    client.updated_at = datetime.utcnow()
    session.add(client)
    record_audit_event(
        session, action="CLIENT_REACTIVATED", object_type="client",
        object_id=client.id, actor_user_id=current.id, result="SUCCESS",
        after={"status": "active"})
    session.commit()
    session.refresh(client)
    return _rendu(session, client, detail=True)


@router.delete("/{client_id}", status_code=204)
def delete_client(
    client_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    """Suppression physique — réservée à une fiche vierge.

    Dès qu'un contact, une interaction, une opportunité ou un trade y pend, on
    refuse et on renvoie de quoi comprendre. Effacer en cascade un historique
    commercial n'est jamais la bonne réponse à une erreur de saisie ;
    l'archivage l'est.
    """
    client = _scoped_client(session, client_id, current)
    try:
        require_client_deletable(session, client.id)
    except ClientRuleError as erreur:
        commit_rejection(
            session, action="CLIENT_DELETE_REJECTED", object_type="client",
            object_id=client.id, actor_user_id=current.id, reason=erreur.code,
            metadata=client_history_counts(session, client.id))
        raise HTTPException(409, detail=erreur.as_dict())

    for ligne in session.exec(
            select(ClientCoverage).where(ClientCoverage.client_id == client.id)).all():
        session.delete(ligne)
    record_audit_event(
        session, action="CLIENT_DELETED", object_type="client",
        object_id=client.id, actor_user_id=current.id, result="SUCCESS",
        before={"name": client.name})
    session.delete(client)
    session.commit()
