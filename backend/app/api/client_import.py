"""Import d'historique commercial — modèle, aperçu, versement, annulation.

Quatre gestes, dans cet ordre : on télécharge le modèle, on le remplit, on
regarde ce que l'import ferait, on valide. L'aperçu n'est pas une politesse :
c'est ce qui évite de découvrir après coup qu'un fichier a créé quatre-vingts
sociétés parce qu'une colonne était décalée.

Motif d'upload repris de `api/amc.py`, qui lit et rend sans persister.
"""
from __future__ import annotations

import json
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response, StreamingResponse
from sqlmodel import Session, select

from ..core.audit import record_audit_event
from ..core.client_import import (
    FEUILLES, ImportError_, analyser, annuler, appliquer, modele_json,
    modele_xlsx,
)
from ..db.database import get_session
from ..db.models import ClientImportBatch, ClientTradeHistory, User
from .auth import get_current_user

router = APIRouter(prefix="/api/client-import", tags=["client-import"])

# 8 Mo : un historique commercial de plusieurs milliers de lignes tient
# largement dedans, et la borne évite qu'un fichier aberrant soit lu en entier
# en mémoire avant d'être refusé.
TAILLE_MAX = 8 * 1024 * 1024


def _format_depuis(nom: str, declare: Optional[str]) -> str:
    if declare in ("xlsx", "json"):
        return declare
    minuscule = (nom or "").lower()
    if minuscule.endswith(".json"):
        return "json"
    if minuscule.endswith((".xlsx", ".xlsm")):
        return "xlsx"
    raise HTTPException(422, "Format non reconnu : attendu .xlsx ou .json.")


async def _lire(fichier: UploadFile) -> bytes:
    contenu = await fichier.read()
    if not contenu:
        raise HTTPException(422, "Fichier vide.")
    if len(contenu) > TAILLE_MAX:
        raise HTTPException(
            413, f"Fichier trop volumineux ({len(contenu) // 1024} Ko) : "
                 f"la limite est de {TAILLE_MAX // 1024 // 1024} Mo.")
    return contenu


@router.get("/template.xlsx")
def modele_excel(current: Annotated[User, Depends(get_current_user)]):
    """Le classeur à remplir — en-têtes exactes, exemple, mode d'emploi."""
    return StreamingResponse(
        iter([modele_xlsx()]),
        media_type=("application/vnd.openxmlformats-officedocument"
                    ".spreadsheetml.sheet"),
        headers={"Content-Disposition":
                 'attachment; filename="structura_import_clients.xlsx"'})


@router.get("/template.json")
def modele_json_(current: Annotated[User, Depends(get_current_user)]):
    return Response(
        content=json.dumps(modele_json(), ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={"Content-Disposition":
                 'attachment; filename="structura_import_clients.json"'})


@router.get("/schema")
def schema(current: Annotated[User, Depends(get_current_user)]):
    """Le format, lisible par l'écran plutôt que recopié dedans — deux
    descriptions du même format divergent toujours."""
    from ..core.client_import import SCHEMA, VOCABULAIRES
    return {
        "sheets": [
            {"key": feuille, "label": SCHEMA[feuille]["libelle"],
             "columns": SCHEMA[feuille]["colonnes"],
             "required": SCHEMA[feuille]["requis"]}
            for feuille in FEUILLES
        ],
        "vocabularies": VOCABULAIRES,
    }


@router.post("/preview")
async def apercu(
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    file: UploadFile = File(...),
    source_format: Optional[str] = Form(None),
):
    """Import à blanc. Valide tout, n'écrit rien."""
    contenu = await _lire(file)
    format_ = _format_depuis(file.filename or "", source_format)
    try:
        rapport = analyser(session, contenu, format_=format_,
                           entity_id=current.entity_id, user_id=current.id)
    except ImportError_ as erreur:
        raise HTTPException(422, erreur.message)
    return {"filename": file.filename, "format": format_, **rapport.as_dict()}


@router.post("/apply")
async def verser(
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    file: UploadFile = File(...),
    source_format: Optional[str] = Form(None),
    skip_invalid: bool = Form(False),
):
    contenu = await _lire(file)
    format_ = _format_depuis(file.filename or "", source_format)
    try:
        lot, rapport = appliquer(
            session, contenu, format_=format_, filename=file.filename or "",
            entity_id=current.entity_id, user_id=current.id,
            ignorer_lignes_fautives=skip_invalid)
    except ImportError_ as erreur:
        session.rollback()
        raise HTTPException(422, erreur.message)

    record_audit_event(
        session, action="CLIENT_IMPORT_APPLIED", object_type="client_import_batch",
        object_id=lot.id, actor_user_id=current.id, result="SUCCESS",
        after={"filename": lot.filename, "created": lot.rows_created,
               "updated": lot.rows_updated, "skipped": lot.rows_skipped},
        data_source=format_)
    session.commit()
    session.refresh(lot)
    return {"batch_id": lot.id, "filename": lot.filename, "format": format_,
            **rapport.as_dict()}


@router.get("/batches")
def lots(
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    lignes = session.exec(
        select(ClientImportBatch).where(
            ClientImportBatch.entity_id == current.entity_id)).all()
    return [{
        "id": lot.id, "filename": lot.filename, "format": lot.source_format,
        "status": lot.status, "rows_created": lot.rows_created,
        "rows_updated": lot.rows_updated, "rows_skipped": lot.rows_skipped,
        "created_at": lot.created_at.isoformat(),
        "reverted_at": lot.reverted_at.isoformat() if lot.reverted_at else None,
        "report": json.loads(lot.report_json or "{}"),
    } for lot in sorted(lignes, key=lambda b: b.created_at, reverse=True)]


@router.post("/batches/{batch_id}/revert")
def annuler_lot(
    batch_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    """Retire les transactions d'historique versées par ce lot.

    Ne défait PAS les sociétés, personnes et affiliations créées : elles ont pu
    recevoir depuis des interactions ou des opportunités saisies à la main, et
    les supprimer emporterait ce travail. Le compte rendu du lot reste lisible
    pour faire le ménage à la main si nécessaire.
    """
    lot = session.get(ClientImportBatch, batch_id)
    if lot is None or lot.entity_id != current.entity_id:
        raise HTTPException(404, "Lot d'import introuvable")
    if lot.status == "reverted":
        raise HTTPException(409, detail={
            "code": "IMPORT_ALREADY_REVERTED",
            "message": "Ce lot a déjà été annulé."})

    retirees = annuler(session, lot)
    record_audit_event(
        session, action="CLIENT_IMPORT_REVERTED",
        object_type="client_import_batch", object_id=lot.id,
        actor_user_id=current.id, result="SUCCESS",
        before={"filename": lot.filename},
        after={"trades_removed": retirees})
    session.commit()
    return {"batch_id": lot.id, "trades_removed": retirees,
            "message": (f"{retirees} transaction(s) d'historique retirée(s). "
                        f"Les sociétés, personnes et parcours créés par ce lot "
                        f"sont conservés.")}
