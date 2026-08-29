import json
from datetime import datetime
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select, or_
from ..db.database import get_session
from ..db.models import Script, User, Folder
from ..core.variants import (
    MODE_AVENANT, MODE_ROLL, MODES, VariantError, decrire_ecarts, resoudre,
    termes_de_rejeu, valider,
)
from .auth import get_current_user

router = APIRouter(prefix="/api/db/scripts", tags=["scripts-db"])


class ScriptCreate(BaseModel):
    name: str
    description: str = ""
    folder_id: int | None = None
    script_text: str = ""
    params_json: str = "{}"
    constats_json: str = "{}"
    global_params_json: str = "{}"
    category: str = ""
    tags: str = ""
    is_shared: bool = False


class ScriptUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    folder_id: int | None = None
    script_text: str | None = None
    params_json: str | None = None
    constats_json: str | None = None
    global_params_json: str | None = None
    category: str | None = None
    tags: str | None = None
    is_shared: bool | None = None


# Ce qui décrit le PRODUIT, par opposition à ce qui décrit la fiche (nom,
# dossier, partage, tags). Une déclinaison hérite le premier de son origine.
_CHAMPS_DE_CONTEXTE = {
    "script_text", "params_json", "constats_json", "global_params_json",
}


def _row(s: Script, owner_name: str, variant_count: int = 0) -> dict:
    return {
        "id": s.id,
        "name": s.name,
        "description": s.description,
        "folder_id": s.folder_id,
        "user_id": s.user_id,
        "owner": owner_name,
        "script_text": s.script_text,
        "params_json": s.params_json,
        "constats_json": s.constats_json,
        "global_params_json": s.global_params_json,
        "category": s.category,
        "tags": s.tags,
        "is_shared": s.is_shared,
        "created_at": s.created_at.isoformat(),
        "updated_at": s.updated_at.isoformat(),
        "parent_id": s.parent_id,
        "variant_title": s.variant_title,
        "variant_mode": s.variant_mode,
        "variant_delta_json": s.variant_delta_json,
        # Rempli seulement sur les parents, et seulement par la liste : l'écran
        # doit pouvoir marquer une origine à variantes sans un appel par ligne.
        "variant_count": variant_count,
    }


@router.get("")
def list_scripts(
    folder_id: int | None = None,
    include_variants: bool = False,
    current: Annotated[User, Depends(get_current_user)] = None,
    session: Annotated[Session, Depends(get_session)] = None,
):
    """Return scripts owned by current user + scripts shared within same entity."""
    stmt = select(Script).where(
        or_(
            Script.user_id == current.id,
            Script.is_shared == True,          # noqa: E712
        )
    )
    if folder_id is not None:
        stmt = stmt.where(Script.folder_id == folder_id)
    scripts = session.exec(stmt).all()

    # Les variantes ne figurent pas dans la liste : elles vivent en sous-onglets
    # de leur origine. Les remonter à plat noierait la liste et ferait perdre ce
    # à quoi elles se comparent.
    comptes: dict[int, int] = {}
    for s_ in scripts:
        if s_.parent_id:
            comptes[s_.parent_id] = comptes.get(s_.parent_id, 0) + 1
    if not include_variants:
        scripts = [s_ for s_ in scripts if not s_.parent_id]

    # For shared scripts, filter to same entity
    entity_id = current.entity_id
    owners: dict[int, str] = {}

    def get_owner(uid: int) -> str:
        if uid not in owners:
            u = session.get(User, uid)
            owners[uid] = u.username if u else "?"
        return owners[uid]

    result = []
    for s in scripts:
        if s.user_id != current.id and s.is_shared:
            owner = session.get(User, s.user_id)
            if not owner or owner.entity_id != entity_id:
                continue
        result.append(_row(s, get_owner(s.user_id), comptes.get(s.id, 0)))

    result.sort(key=lambda x: x["updated_at"], reverse=True)
    return result


@router.post("", status_code=201)
def create_script(
    body: ScriptCreate,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    if body.folder_id:
        f = session.get(Folder, body.folder_id)
        if not f or f.user_id != current.id:
            raise HTTPException(404, "Dossier introuvable")
    s = Script(
        name=body.name.strip(),
        description=body.description,
        folder_id=body.folder_id,
        user_id=current.id,
        script_text=body.script_text,
        params_json=body.params_json,
        constats_json=body.constats_json,
        global_params_json=body.global_params_json,
        category=body.category,
        tags=body.tags,
        is_shared=body.is_shared,
    )
    session.add(s)
    session.commit()
    session.refresh(s)
    return _row(s, current.username)


@router.get("/{script_id}")
def get_script(
    script_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    s = session.get(Script, script_id)
    if not s:
        raise HTTPException(404, "Script introuvable")
    if s.user_id != current.id:
        if not s.is_shared:
            raise HTTPException(403, "Accès refusé")
        owner = session.get(User, s.user_id)
        if not owner or owner.entity_id != current.entity_id:
            raise HTTPException(403, "Accès refusé")
    owner_name = (session.get(User, s.user_id) or User(username="?")).username
    return _row(s, owner_name)


@router.put("/{script_id}")
def update_script(
    script_id: int,
    body: ScriptUpdate,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    s = session.get(Script, script_id)
    if not s or s.user_id != current.id:
        raise HTTPException(404, "Script introuvable ou accès refusé")
    fourni = body.model_dump(exclude_unset=True)

    # Une déclinaison ne porte PAS de contexte : le sien vient de son origine, et
    # ses propres blobs ne sont jamais relus. Écrire dedans ne produirait donc
    # pas un prix faux, mais de la donnée morte et un utilisateur convaincu
    # d'avoir enregistré quelque chose. On refuse ces champs-là précisément —
    # refuser la requête entière casserait le renommage, le rangement en dossier
    # et le partage, qui passent par le même endpoint.
    if s.parent_id:
        interdits = sorted(set(fourni) & _CHAMPS_DE_CONTEXTE)
        if interdits:
            raise HTTPException(
                422,
                f"Une déclinaison ne stocke que ses écarts : {', '.join(interdits)} "
                f"ne s'y écrit pas et ne serait jamais relu. Passez par "
                f"PUT /api/db/scripts/variants/{script_id}, qui enregistre le delta. "
                f"Le nom, le dossier et le partage restent modifiables ici.")

    for field, value in fourni.items():
        setattr(s, field, value)
    s.updated_at = datetime.utcnow()
    session.add(s)
    session.commit()
    return _row(s, current.username)


@router.delete("/{script_id}", status_code=204)
def delete_script(
    script_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    cascade: bool = False,
):
    """Supprime un script — origine ou déclinaison.

    Une déclinaison se supprime seule, sans conséquence : elle ne stocke que ses
    écarts, et son origine n'en sait rien.

    Une ORIGINE qui porte des déclinaisons est refusée par défaut. Les
    supprimer en silence détruirait un travail réel — cinq propositions
    client — parce qu'on a voulu ranger le deal dont elles descendent. Et les
    laisser derrière serait pire : sans leur origine, elles n'ont plus de
    contexte à hériter, donc plus de prix ; elles deviendraient des fantômes
    qui s'affichent et ne s'ouvrent jamais. On demande donc, et on ne cascade
    que si l'appelant l'a dit."""
    s = session.get(Script, script_id)
    if not s or s.user_id != current.id:
        raise HTTPException(404, "Script introuvable ou accès refusé")

    enfants = session.exec(select(Script).where(Script.parent_id == script_id)).all()
    # La cascade n'emporte QUE ses propres déclinaisons. Sur une origine
    # partagée, ranger son dossier détruisait les propositions client des
    # collègues — après une confirmation qui ne nommait que des titres, sans
    # dire à qui ils appartenaient.
    miennes = [e for e in enfants if e.user_id == current.id]
    autrui = [e for e in enfants if e.user_id != current.id]
    if enfants and not cascade:
        titres = ", ".join(f"« {e.variant_title or e.name} »" for e in enfants[:4])
        suite = "…" if len(enfants) > 4 else ""
        detail = (f"Ce deal porte {len(enfants)} déclinaison(s) : {titres}{suite}. "
                  f"Elles n'ont pas de contexte propre — sans leur origine, elles ne "
                  f"peuvent plus être valorisées.")
        if autrui:
            noms = sorted({(session.get(User, e.user_id) or User(username="?")).username
                           for e in autrui})
            detail += (f" {len(autrui)} d'entre elles appartiennent à "
                       f"{', '.join(noms)} et ne seront PAS supprimées ; elles "
                       f"resteront sans origine.")
        detail += " Supprimez-les d'abord, ou confirmez la suppression de l'ensemble."
        raise HTTPException(409, detail)
    if autrui and cascade:
        raise HTTPException(
            409,
            f"{len(autrui)} déclinaison(s) de ce deal appartiennent à quelqu'un "
            f"d'autre. Supprimer l'origine les rendrait illisibles sans que leur "
            f"auteur soit prévenu : demandez-lui de les retirer d'abord.")
    for e in miennes:
        session.delete(e)
    session.delete(s)
    session.commit()


# ── Variantes ───────────────────────────────────────────────────────
#
# Une variante est un DELTA rattaché à une origine, jamais une copie. Tout ce
# qu'elle ne dit pas est hérité à la lecture — c'est ce qui garantit qu'elle se
# compare à son parent « toutes choses égales par ailleurs », et ce qui permet
# à l'écran de colorer les écarts et de griser les retraits. Voir
# core/variants.py pour le détail du raisonnement.

class VariantCreate(BaseModel):
    """Ce qu'il faut pour décliner un deal : un titre, un mode, des écarts."""
    variant_title: str
    variant_mode: str = MODE_AVENANT
    delta: dict = {}


class VariantUpdate(BaseModel):
    variant_title: str | None = None
    variant_mode: str | None = None
    delta: dict | None = None


def _contexte(s: Script) -> dict:
    """Le contexte de pricing complet porté par une ligne de script."""
    return {
        "script_text": s.script_text,
        "params": json.loads(s.params_json or "{}"),
        "constats": json.loads(s.constats_json or "{}"),
        "global": json.loads(s.global_params_json or "{}"),
    }


def _visible_par(s: Script, current: User, session: Session) -> bool:
    """La règle de visibilité, écrite UNE fois.

    Le sien, ou celui d'un collègue de la même entité qui l'a partagé. Deux
    formes en découlent : celle-ci, qui répond, et `_lisible`, qui lève —
    l'une pour filtrer une liste, l'autre pour garder un accès. Elles
    coexistaient en deux implémentations, ce qui est exactement la divergence
    que ce chantier a fermée partout ailleurs."""
    if s.user_id == current.id:
        return True
    if not s.is_shared:
        return False
    owner = session.get(User, s.user_id)
    return bool(owner and owner.entity_id == current.entity_id)


def _lisible(s: Script, current: User, session: Session) -> Script:
    """Le script, ou 404/403 — même règle de visibilité que get_script."""
    if not s:
        raise HTTPException(404, "Script introuvable")
    if not _visible_par(s, current, session):
        raise HTTPException(403, "Accès refusé")
    return s


def _origine(variante: Script, current: User, session: Session) -> Script:
    """L'origine d'une variante, avec le MÊME contrôle de visibilité qu'elle.

    Une variante n'a pas de contexte propre : sa vue rend celui de son parent,
    script compris. Relire le parent sans contrôle laissait donc fuir une
    origine devenue privée — il suffisait qu'elle ait été partagée au moment où
    la variante a été créée, puisque le partage s'hérite à la création et ne se
    révise jamais ensuite."""
    parent = session.get(Script, variante.parent_id) if variante.parent_id else None
    if not parent:
        raise HTTPException(422, "L'origine de cette variante est introuvable — "
                                 "elle a probablement été supprimée.")
    return _lisible(parent, current, session)


def _vue_variante(v: Script, parent: Script) -> dict:
    """Une variante, avec son contexte effectif ET ses écarts.

    Les deux, parce qu'ils servent à des choses différentes : le contexte
    effectif price, les écarts colorent. Les recalculer séparément à l'écran
    ferait diverger ce qu'on price de ce qu'on montre."""
    delta = json.loads(v.variant_delta_json or "{}")
    base = _contexte(parent)
    try:
        effectif = resoudre(base, delta, v.variant_mode or MODE_AVENANT)
    except VariantError as e:
        raise HTTPException(422, str(e))
    vue = {
        "id": v.id, "parent_id": parent.id, "name": v.name,
        "variant_title": v.variant_title, "variant_mode": v.variant_mode,
        "delta": delta,
        "ecarts": decrire_ecarts(base, delta),
        "contexte": effectif,
        "updated_at": v.updated_at.isoformat(),
    }
    # Le contexte de l'ORIGINE, contre lequel l'écran calcule ses écarts quand
    # on enregistre. Le déduire du contexte effectif moins le delta serait une
    # inversion fragile ; le rendre coûte quelques kilo-octets et ferme la
    # question.
    vue["contexte_parent"] = base
    if (v.variant_mode or MODE_AVENANT) != MODE_ROLL:
        # Les termes sous lesquels le PASSÉ doit être rejoué — ceux de
        # l'origine. L'écran en a besoin pour bâtir sa requête : le corps
        # principal les prend, le bloc `variant` prend ce qui est affiché. Sans
        # cette asymétrie, une barrière abaissée à 50 % ferait rappeler le
        # produit dans le passé, et le moteur rendrait le prix d'une note déjà
        # remboursée. Une note neuve n'en a pas besoin : elle n'a pas de passé.
        try:
            vue["base_pricing"] = termes_de_rejeu(base)
        except ValueError as e:
            raise HTTPException(422, f"Script de l'origine illisible : {e}")
    return vue


@router.get("/{script_id}/variants")
def list_variants(
    script_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    """Les variantes d'une origine, chacune avec ses écarts résolus."""
    parent = _lisible(session.get(Script, script_id), current, session)
    if parent.parent_id:
        raise HTTPException(422, "Cette entrée est déjà une variante. Les variantes "
                                 "sont à plat : pour itérer, dupliquez-la en sœur.")
    stmt = select(Script).where(Script.parent_id == script_id)
    variantes = sorted(session.exec(stmt).all(), key=lambda v: v.created_at)
    # Les siennes, plus celles que l'entité partage. Sans ce filtre, une origine
    # partagée exposait à tous les brouillons de chacun — une proposition client
    # à demi rédigée n'a rien à faire sous les yeux d'un collègue.
    return [_vue_variante(v, parent) for v in variantes
            if _visible_par(v, current, session)]





@router.post("/{script_id}/variants", status_code=201)
def create_variant(
    script_id: int,
    body: VariantCreate,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    """Décline une origine — sans copier son contexte, en le référençant."""
    parent = _lisible(session.get(Script, script_id), current, session)
    if parent.parent_id:
        raise HTTPException(
            422, "On ne décline pas une variante : elles sont à plat, toutes "
                 "rattachées à l'origine. Dupliquez-la en sœur pour itérer.")
    titre = (body.variant_title or "").strip()
    if not titre:
        raise HTTPException(422, "Donnez un titre à la variante — c'est ce qui "
                                 "permet de s'y retrouver entre cinq déclinaisons.")
    try:
        valider(body.delta, body.variant_mode)
        # Résoudre tout de suite : un delta incohérent doit être refusé
        # maintenant, pas découvert à la relecture sur une variante qu'on
        # croyait bonne.
        resoudre(_contexte(parent), body.delta, body.variant_mode)
    except VariantError as e:
        raise HTTPException(422, str(e))

    v = Script(
        name=parent.name, description=parent.description,
        folder_id=parent.folder_id, user_id=current.id,
        # Les quatre blobs restent VIDES : le contexte vient du parent, et le
        # dupliquer ici le figerait — une variante doit suivre son origine.
        category=parent.category, tags=parent.tags, is_shared=parent.is_shared,
        parent_id=parent.id, variant_title=titre,
        variant_mode=body.variant_mode,
        variant_delta_json=json.dumps(body.delta or {}, ensure_ascii=False),
    )
    session.add(v)
    session.commit()
    session.refresh(v)
    return _vue_variante(v, parent)


@router.put("/variants/{variant_id}")
def update_variant(
    variant_id: int,
    body: VariantUpdate,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    v = session.get(Script, variant_id)
    if not v or v.user_id != current.id or not v.parent_id:
        raise HTTPException(404, "Variante introuvable ou accès refusé")
    parent = _origine(v, current, session)
    mode = body.variant_mode if body.variant_mode is not None else v.variant_mode
    delta = body.delta if body.delta is not None else json.loads(v.variant_delta_json or "{}")
    try:
        valider(delta, mode)
        resoudre(_contexte(parent), delta, mode)
    except VariantError as e:
        raise HTTPException(422, str(e))
    if body.variant_title is not None:
        titre = body.variant_title.strip()
        if not titre:
            raise HTTPException(422, "Le titre d'une variante ne peut pas être vide.")
        v.variant_title = titre
    v.variant_mode = mode
    v.variant_delta_json = json.dumps(delta, ensure_ascii=False)
    v.updated_at = datetime.utcnow()
    session.add(v)
    session.commit()
    session.refresh(v)
    return _vue_variante(v, parent)


@router.get("/variants/{variant_id}/resolved")
def resolve_variant(
    variant_id: int,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    """Le contexte effectif d'une variante, prêt à charger dans le Pricer."""
    v = _lisible(session.get(Script, variant_id), current, session)
    if not v.parent_id:
        raise HTTPException(422, "Cette entrée est une origine, pas une variante.")
    return _vue_variante(v, _origine(v, current, session))
