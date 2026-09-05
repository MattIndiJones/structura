"""Déclarer un champ de contrainte — pour la maison, ou pour un client.

Le référentiel décrit ce qu'est une contrainte ; ce routeur permet d'en ajouter.
Deux portées, et la distinction n'est pas cosmétique :

- **Sans `client_id`** : un champ de la maison. Il apparaît sur toutes les
  fiches de l'entité. C'est le geste d'un admin qui formalise une politique.
- **Avec `client_id`** : un nom convenu entre l'utilisateur et ce client-là.
  Il n'apparaît que sur sa fiche. C'est le geste d'un commercial qui note la
  contrainte que son client formule dans son vocabulaire à lui.

Trois refus structurent l'écriture, tous pour la même raison — un champ qu'on
ne peut pas remplir correctement est pire que pas de champ :

1. Une clé standard ne se redéclare pas. Deux champs de même sens se
   remplissent chacun à moitié.
2. Une liste à choix fermé sans valeurs n'accepterait rien.
3. Un champ utilisé ne se supprime pas, il s'archive : sa valeur survivrait
   dans le blob de chaque client, et la validation suivante la refuserait
   comme clé inconnue.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session, select

from ..core.client_constraints_ref import (
    CATALOGS, ConstraintRefError, KINDS, catalog_options, definitions_for,
    key_in_use, normalize_key, require_definable,
)
from ..db.database import get_session
from ..db.models import Client, ConstraintDefinition, User
from .auth import get_current_user

router = APIRouter(prefix="/api/constraint-definitions",
                   tags=["constraint-definitions"])


class DefinitionCreate(BaseModel):
    label: str
    kind: str = "text"
    key: Optional[str] = None          # déduite du libellé si absente
    client_id: Optional[int] = None
    options: list[str] = []
    catalog: Optional[str] = None
    unit: Optional[str] = None
    help_text: Optional[str] = None
    free_entry: bool = True


class DefinitionUpdate(BaseModel):
    """La CLÉ ne figure pas ici, et c'est le point.

    Elle est écrite dans le blob de chaque client qui a rempli le champ ; la
    renommer orphelinerait toutes ces valeurs d'un coup, sans erreur ni trace.
    Le libellé, lui, se change librement — c'est ce que les gens lisent.
    """
    label: Optional[str] = None
    options: Optional[list[str]] = None
    catalog: Optional[str] = None
    unit: Optional[str] = None
    help_text: Optional[str] = None
    free_entry: Optional[bool] = None


def _client_de_l_entite(session: Session, client_id: int, current: User) -> Client:
    client = session.get(Client, client_id)
    if client is None or client.entity_id != current.entity_id:
        raise HTTPException(404, "Client introuvable.")
    return client


def _ligne_de_l_entite(session: Session, definition_id: int,
                       current: User) -> ConstraintDefinition:
    ligne = session.get(ConstraintDefinition, definition_id)
    if ligne is None or ligne.entity_id != current.entity_id:
        raise HTTPException(404, "Champ introuvable.")
    return ligne


def _rendu(ligne: ConstraintDefinition, *, usages: Optional[int] = None) -> dict:
    try:
        options = json.loads(ligne.options_json or "[]")
    except (TypeError, ValueError):
        options = []
    return {
        "id": ligne.id, "key": ligne.key, "label": ligne.label,
        "kind": ligne.kind, "options": options, "catalog": ligne.catalog,
        "unit": ligne.unit, "help_text": ligne.help_text,
        "free_entry": ligne.free_entry, "client_id": ligne.client_id,
        "scope": "client" if ligne.client_id else "entity",
        "archived": ligne.archived,
        "created_at": ligne.created_at.isoformat(),
        "usages": usages,
    }


@router.get("/meta")
def meta(current: Annotated[User, Depends(get_current_user)]):
    """Les types de champ et les catalogues disponibles.

    L'écran de déclaration les lit ici plutôt que de les recopier : une liste
    recopiée diverge le jour où on en ajoute un, et le champ créé devient
    invalide à l'enregistrement sans que l'utilisateur comprenne pourquoi.
    """
    return {
        "kinds": [{"value": cle, "label": meta_["label"],
                   "storage": meta_["storage"]}
                  for cle, meta_ in KINDS.items()],
        "catalogs": list(CATALOGS),
    }


@router.get("")
def list_definitions(
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    client_id: Optional[int] = Query(None),
    include_archived: bool = Query(False),
):
    """Les champs déclarés — ceux de la maison, et ceux de ce client s'il est nommé."""
    requete = select(ConstraintDefinition).where(
        ConstraintDefinition.entity_id == current.entity_id
        if current.entity_id is not None
        else ConstraintDefinition.entity_id.is_(None))
    if not include_archived:
        requete = requete.where(ConstraintDefinition.archived == False)  # noqa: E712

    lignes = []
    for ligne in session.exec(requete).all():
        if ligne.client_id is not None and ligne.client_id != client_id:
            continue
        lignes.append(_rendu(ligne, usages=key_in_use(session, ligne)))
    return {"definitions": sorted(lignes, key=lambda d: (d["scope"], d["label"]))}


@router.post("", status_code=201)
def create_definition(
    body: DefinitionCreate,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    if not (body.label or "").strip():
        raise HTTPException(422, "Un champ sans libellé ne se remplit pas.")
    if body.client_id is not None:
        _client_de_l_entite(session, body.client_id, current)

    try:
        cle = normalize_key(body.key or body.label)
        require_definable(session, entity_id=current.entity_id,
                          client_id=body.client_id, key=cle, kind=body.kind,
                          catalog=body.catalog, options=body.options)
    except ConstraintRefError as erreur:
        raise HTTPException(422, detail=erreur.as_dict())

    ligne = ConstraintDefinition(
        entity_id=current.entity_id, client_id=body.client_id, key=cle,
        label=body.label.strip(), kind=body.kind,
        options_json=json.dumps(sorted({o.strip() for o in body.options if o.strip()}),
                                ensure_ascii=False),
        catalog=body.catalog, unit=body.unit, help_text=body.help_text,
        free_entry=body.free_entry, created_by_user_id=current.id)
    session.add(ligne)
    session.commit()
    session.refresh(ligne)
    return _rendu(ligne, usages=0)


@router.patch("/{definition_id}")
def update_definition(
    definition_id: int,
    body: DefinitionUpdate,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    ligne = _ligne_de_l_entite(session, definition_id, current)
    if body.label is not None:
        if not body.label.strip():
            raise HTTPException(422, "Un champ sans libellé ne se remplit pas.")
        ligne.label = body.label.strip()
    if body.options is not None:
        try:
            require_definable(session, entity_id=ligne.entity_id,
                              client_id=ligne.client_id, key=ligne.key,
                              kind=ligne.kind,
                              catalog=body.catalog if body.catalog is not None
                              else ligne.catalog,
                              options=body.options, definition_id=ligne.id)
        except ConstraintRefError as erreur:
            raise HTTPException(422, detail=erreur.as_dict())
        ligne.options_json = json.dumps(
            sorted({o.strip() for o in body.options if o.strip()}),
            ensure_ascii=False)
    for champ in ("catalog", "unit", "help_text", "free_entry"):
        valeur = getattr(body, champ)
        if valeur is not None:
            setattr(ligne, champ, valeur)
    ligne.updated_at = datetime.utcnow()
    session.add(ligne)
    session.commit()
    session.refresh(ligne)
    return _rendu(ligne, usages=key_in_use(session, ligne))


@router.delete("/{definition_id}")
def archive_definition(
    definition_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    force: bool = Query(False),
):
    """Archive le champ. Supprime pour de bon uniquement s'il n'a jamais servi.

    Un champ rempli chez ne serait-ce qu'un client laisse une valeur dans son
    blob. Sans définition pour la décrire, l'enregistrement suivant de SA fiche
    la refuserait comme clé inconnue — l'utilisateur se retrouverait bloqué sur
    un écran par une suppression faite ailleurs, des semaines plus tôt.
    """
    ligne = _ligne_de_l_entite(session, definition_id, current)
    usages = key_in_use(session, ligne)
    if usages == 0 and force:
        session.delete(ligne)
        session.commit()
        return {"deleted": True, "archived": False, "usages": 0}
    ligne.archived = True
    ligne.updated_at = datetime.utcnow()
    session.add(ligne)
    session.commit()
    return {"deleted": False, "archived": True, "usages": usages}


@router.post("/{definition_id}/restore")
def restore_definition(
    definition_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    ligne = _ligne_de_l_entite(session, definition_id, current)
    try:
        require_definable(session, entity_id=ligne.entity_id,
                          client_id=ligne.client_id, key=ligne.key,
                          kind=ligne.kind, catalog=ligne.catalog,
                          options=json.loads(ligne.options_json or "[]"),
                          definition_id=ligne.id)
    except ConstraintRefError as erreur:
        raise HTTPException(422, detail=erreur.as_dict())
    ligne.archived = False
    ligne.updated_at = datetime.utcnow()
    session.add(ligne)
    session.commit()
    session.refresh(ligne)
    return _rendu(ligne, usages=key_in_use(session, ligne))


@router.get("/catalog/{catalog}")
def read_catalog(
    catalog: str,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    try:
        return {"options": catalog_options(session, catalog)}
    except ConstraintRefError as erreur:
        raise HTTPException(404, detail=erreur.as_dict())
