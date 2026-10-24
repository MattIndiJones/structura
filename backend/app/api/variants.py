"""Compare variants using one market context and the original nominal basis.

A roll buys net exit proceeds / all-in entry price units of the new note.
Quantity, future undiscounted recovery and a proven contractual cap are separate
metrics. A simulated maximum never establishes a contractual bound. The sealed
study retains the funding assumptions, inputs, prices and resulting distributions.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from ..core.variants import MODE_ROLL, VariantError, params_moteur, resoudre
from ..core.roll_economics import RollFinancing, recovery_summary, roll_budget
from ..db.database import get_session
from ..db.models import Script, User, VariantStudyArchive
from ..services.archived_documents import seal, unseal, ProposalFreeze
from ..core.valuation_runs import calculation_identity
from .auth import get_current_user
from .inlife import InLifePricingRequest, price_in_life
from .scripts_db import _contexte, _lisible

router = APIRouter(prefix="/api/variants", tags=["variants"])

# Les champs de sous-jacent que l'écran saisit en pourcentage. Le contexte
# stocké est en unités d'AFFICHAGE, la requête en unités MOTEUR : sans cette
# table, une volatilité de variante partirait à 34,27 au lieu de 0,3427.
_POURCENTS_UL = {
    "sigma", "q", "sigma_fx", "rho_sfx", "v0", "theta", "xi", "rho_h",
    "rho_rS", "alpha", "beta", "rho", "nu", "skew", "curvature",
}


class CompareRequest(BaseModel):
    """Le corps du parent, tel que l'écran l'envoie, plus les variantes à situer."""
    base: dict
    # L'origine que `base` est censée décrire. Sans elle, rien n'empêche
    # d'appliquer le delta d'un produit A au corps d'un produit B : le tableau
    # rendrait des chiffres dénués de sens sous des titres qui en ont l'air.
    parent_id: Optional[int] = None
    variant_ids: list[int] = Field(default_factory=list)
    # Moins de chemins que le prix de référence : ce tableau classe, il ne
    # publie pas. Le prix qui fait foi reste celui de l'onglet Résultats.
    N: int = Field(default=8000, ge=1000, le=50000)
    roll_financing: RollFinancing = Field(default_factory=RollFinancing)


def _prix(corps: dict, current: User) -> dict:
    """Une valorisation, par le MÊME chemin que l'écran."""
    return price_in_life(InLifePricingRequest(**corps), current)


def _corps_avenant(base: dict, ctx: dict) -> dict:
    """Le corps du parent, augmenté des termes de l'avenant.

    Le passé reste rejoué aux termes d'origine — c'est `base` qui les porte —
    et seule la vie restante prend ceux de la variante."""
    corps = dict(base)
    corps["variant"] = {
        "script": ctx["script_text"],
        "user_params": _params_moteur_http(ctx["script_text"], ctx.get("params")),
        "constats": ctx.get("constats") or {},
        "mode": "avenant",
    }
    return corps


def _corps_roll(base: dict, ctx: dict) -> dict:
    """Le corps d'une note neuve : mêmes sous-jacents, axe des temps recalé.

    Les sous-jacents viennent de `base`, donc DÉJÀ en unités moteur — on ne les
    reconstruit pas, on les filtre et on n'y touche que si la variante a
    explicitement changé un champ. Un roll ne recalibre rien : la volatilité et
    le dividende ont été mesurés à la date de valorisation, ils sont déjà les
    bons."""
    g = ctx["global"]
    corps = dict(base)
    corps.pop("variant", None)

    # Le panier de la variante, dans l'ORDRE du contexte — c'est celui que sa
    # matrice de corrélation décrit, et les deux ne se séparent pas.
    #
    # Un titre HÉRITÉ est repris de `base`, donc déjà en unités moteur et déjà
    # calibré : la variante ne peut pas y toucher. COPIE et non référence —
    # `base` est partagé par toutes les lignes du tableau, et muter en place
    # ferait fuiter une calibration dans tout ce qui se calcule après.
    #
    # Un titre AJOUTÉ n'existe pas dans `base` : sa définition vient du contexte,
    # en unités d'affichage, et doit être convertie.
    depuis_base = {u.get("name"): u for u in base.get("underlyings", [])}
    panier = []
    for u_ctx in (g.get("underlyings") or []):
        nom = u_ctx.get("name")
        herite = depuis_base.get(nom)
        panier.append(dict(herite) if herite else _ajoute_en_unites_moteur(u_ctx))
    if not panier:
        raise HTTPException(422, "La note neuve n'a aucun sous-jacent.")
    corps["underlyings"] = panier

    matrice = g.get("corr_matrix")
    if not matrice or len(matrice) != len(panier):
        raise HTTPException(
            422,
            f"Matrice de corrélation incohérente avec le panier de cette "
            f"déclinaison ({len(matrice or [])} lignes pour {len(panier)} titres).")
    corps["corr_matrix"] = matrice

    corps["script"] = ctx["script_text"]
    corps["user_params"] = _params_moteur_http(ctx["script_text"], ctx.get("params"))
    corps["constats"] = ctx.get("constats") or {}
    for cle in ("strike_date", "value_date", "payment_date"):
        if g.get(cle):
            corps[cle] = g[cle]
    # Strikée aujourd'hui : valorisation = strike, donc pricing à l'émission.
    corps["valuation_date"] = g.get("strike_date")
    # Les niveaux du term sheet d'origine feraient repartir les barrières d'un
    # strike vieux de deux ans, pour un prix parfaitement plausible.
    corps["strike_levels"] = {}
    corps["maturity_date"] = _maturite(ctx, corps)
    return corps


def _ajoute_en_unites_moteur(u: dict) -> dict:
    """Un sous-jacent AJOUTÉ par la variante, converti pour le moteur.

    Il n'existe pas dans le corps de l'écran, donc rien à hériter : sa fiche
    arrive en unités d'affichage (σ = 45,0) et doit passer en unités moteur
    (0,45).

    On délègue à `_engine_underlyings`, LE convertisseur du chemin en cours de
    vie, plutôt que d'en écrire un second. La première version de cette fonction
    divisait naïvement par 100 une liste de champs — et perdait au passage le
    `ccyh`, qui se divise par 10 000, ainsi que toute la courbe de dividende.
    Pydantic ignorant les champs inconnus, rien n'échouait : le titre ajouté
    arrivait au moteur sans dividende, avec un prix parfaitement plausible.

    C'est le motif que ce chantier a passé son temps à fermer ailleurs : deux
    voies pour une seule conversion finissent toujours par diverger sur le
    champ que l'une des deux n'a pas vu."""
    from ..core.inlife_valuation import _engine_underlyings
    fiche = {k: v for k, v in u.items() if k != "correlations"}
    identite = {"name": fiche.get("name", ""), "ticker": fiche.get("ticker", ""),
                "ccy": fiche.get("ccy", "EUR")}
    return _engine_underlyings({"underlyings": [fiche]}, [identite])[0]


def _maturite(ctx: dict, corps: dict) -> str:
    """La fin du calendrier de la variante — sa maturité."""
    fins = [v.get("end_date") for v in (ctx.get("constats") or {}).values()
            if isinstance(v, dict) and v.get("end_date")]
    if fins:
        return max(fins)
    # Sans calendrier daté, on prolonge le ténor depuis le nouveau strike.
    strike = date.fromisoformat(corps["strike_date"])
    return (strike + timedelta(days=int(round(365.25 * (ctx["global"].get("T") or 3.0))))).isoformat()


def _proba_pair(res: dict, seuil: float) -> Optional[float]:
    """P(payoff ≥ seuil), lue sur la distribution non actualisée.

    `prob_gt100` ne répond qu'au seuil 1,0 ; un roll en demande un autre."""
    payoffs = res.get("payoffs") or []
    if not payoffs:
        return None
    return round(sum(1 for p in payoffs if p >= seuil) / len(payoffs), 6)


@router.post("/compare")
def compare_variants(
    req: CompareRequest,
    current: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    """Situe chaque déclinaison contre son origine, sur la même base de marché."""
    corps_base = dict(req.base)
    corps_base["N"] = req.N
    corps_base.pop("variant", None)
    corps_base.pop("compute_greeks", None)

    origine = _prix(corps_base, current)
    if origine.get("early_recall"):
        raise HTTPException(422, origine.get("message", "Produit déjà rappelé."))
    p0 = origine["price"]
    from ..runtime import business_now
    from datetime import timezone
    now = business_now()
    calculated_at = (now.replace(tzinfo=timezone.utc) if now.tzinfo is None
                     else now.astimezone(timezone.utc)).isoformat()
    valuation_date = origine.get('valuation_date') or corps_base.get('valuation_date')
    evidence = [{"id": None, "input": corps_base, "result": origine}]

    lignes = [{
        "id": None, "titre": "Origine", "mode": "",
        "prix": p0, "ecart": 0.0,
        # Nominal inchangé : récupérer le pair, c'est que la jambe rende 100 %.
        "proba_pair_origine": origine.get("prob_gt100"),
        **recovery_summary(origine, 1.0),
        "duree": origine.get("fugit"),
        "ecarts": 0,
    }]

    for vid in req.variant_ids:
        v = _lisible(session.get(Script, vid), current, session)
        parent = session.get(Script, v.parent_id) if v.parent_id else None
        if not parent:
            continue
        if req.parent_id is not None and parent.id != req.parent_id:
            lignes.append(_refus(
                v, v.variant_mode or "avenant", {},
                f"Cette déclinaison appartient à un autre deal ({parent.name}) : "
                f"ses écarts ne décrivent rien sur celui-ci."))
            continue
        delta = json.loads(v.variant_delta_json or "{}")
        mode = v.variant_mode or "avenant"
        item = {"id": v.id, "parent_id": parent.id, "parent_context": _contexte(parent),
                "delta": delta, "mode": mode, "title": v.variant_title}
        evidence.append(item)
        try:
            ctx = resoudre(_contexte(parent), delta, mode)
            corps = (_corps_roll if mode == MODE_ROLL else _corps_avenant)(corps_base, ctx)
            item["input"] = corps
            res = _prix(corps, current)
            item["result"] = res
        except VariantError as e:
            lignes.append(_refus(v, mode, delta, str(e)))
            continue
        except HTTPException as e:
            lignes.append(_refus(v, mode, delta, str(e.detail)))
            continue
        if res.get("early_recall"):
            lignes.append(_refus(v, mode, delta, res.get("message", "Rappel anticipé.")))
            continue

        prix = res["price"]
        financing = None
        try:
            if mode == MODE_ROLL:
                k, financing = roll_budget(p0, prix, req.roll_financing,
                    valuation_date=valuation_date, calculated_at=calculated_at)
                proba = _proba_pair(res, 1.0 / k) if k > 0 else 0.0
                recovery = recovery_summary(res, k, script=corps['script'])
            else:
                proba = res.get('prob_gt100')
                recovery = recovery_summary(res, 1.0)
        except ValueError as exc:
            lignes.append(_refus(v, mode, delta, str(exc)))
            continue

        lignes.append({
            "id": v.id, "titre": v.variant_title, "mode": mode,
            "prix": prix, "ecart": round(prix - p0, 6),
            "proba_pair_origine": proba, **recovery,
            "roll_financing": financing,
            "duree": res.get("fugit"),
            "ecarts": len(delta.get("set") or {}) + len(delta.get("removed") or []),
        })

    result = {"lignes": lignes, "N": req.N, 'comparison_schema_version': 2,
            'roll_financing': req.roll_financing.model_dump(mode='json'),
            'calculated_at': calculated_at,
            "valuation_date": origine.get("valuation_date"),
            "in_life": origine.get("in_life", False)}
    if req.parent_id is not None:
        parent = _lisible(session.get(Script, req.parent_id), current, session)
        import hashlib
        from pathlib import Path
        result["preview"] = seal({"purpose": "VARIANT_STUDY", "user_id": current.id,
            "script_id": parent.id, "created_at": business_now().isoformat(),
            "parent_context": _contexte(parent), "request": req.model_dump(mode="json"),
            "calculation_identity": calculation_identity(), "evidence": evidence,
            "comparison_method_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "result": dict(result)})
    return result


@router.post("/archives")
def freeze_variant_study(body: ProposalFreeze, current: Annotated[User, Depends(get_current_user)],
                         session: Annotated[Session, Depends(get_session)]):
    from uuid import uuid5, NAMESPACE_URL
    from ..core.valuation_context import canonical_json
    claims = unseal(body.preview, current.id, "VARIANT_STUDY")
    _lisible(session.get(Script, claims["script_id"]), current, session)
    archive_id = str(uuid5(NAMESPACE_URL, "structura-variant-study:" + body.preview["signature"]))
    row = session.get(VariantStudyArchive, archive_id)
    if row is None:
        row = VariantStudyArchive(id=archive_id, script_id=claims["script_id"], user_id=current.id,
                                  evidence_json=canonical_json(claims))
        session.add(row)
        from ..core.audit import record_audit_event
        record_audit_event(session, action="VARIANT_STUDY_FROZEN", object_type="SCRIPT",
                           object_id=row.script_id, actor_user_id=current.id, result="SUCCESS",
                           after={"archive_id": row.id})
        session.commit()
    return {"archive_id": row.id}


@router.get("/archives/{script_id}")
def list_variant_studies(script_id: int, current: Annotated[User, Depends(get_current_user)],
                         session: Annotated[Session, Depends(get_session)]):
    _lisible(session.get(Script, script_id), current, session)
    return [{"archive_id": row.id, "created_at": row.created_at.isoformat(),
             "evidence": json.loads(row.evidence_json)} for row in session.exec(select(VariantStudyArchive).where(
                 VariantStudyArchive.script_id == script_id, VariantStudyArchive.user_id == current.id)
                 .order_by(VariantStudyArchive.created_at.desc())).all()]


def _refus(v: Script, mode: str, delta: dict, motif: str) -> dict:
    """Une ligne qui dit pourquoi elle n'a pas de prix.

    L'omettre laisserait croire que la variante n'existe pas ; lui donner un
    prix nul la ferait classer dernière. Un refus se lit."""
    return {
        "id": v.id, "titre": v.variant_title, "mode": mode,
        "prix": None, "ecart": None, "proba_pair_origine": None,
        "plafond": None, "duree": None,
        'reinvested_notional': None, 'recovery_mean': None, 'recovery_median': None,
        'recovery_sample_max': None, 'recovery_cap_method': 'UNAVAILABLE', 'roll_financing': None,
        "ecarts": len(delta.get("set") or {}) + len(delta.get("removed") or []),
        "refus": motif,
    }


def _params_moteur_http(script: str, params_affichage: dict) -> dict:
    """`params_moteur`, avec le refus traduit en 422 plutôt qu'en trace."""
    try:
        return params_moteur(script, params_affichage)
    except ValueError as e:
        raise HTTPException(422, f"Script de variante illisible : {e}")
