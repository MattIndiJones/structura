"""Comparaison des déclinaisons d'un deal, côte à côte.

À iso-valeur, le prix ne départage plus rien : c'est tout l'intérêt de
restructurer, et c'est aussi ce qui rend un tableau de prix inutile pour
choisir. La colonne qui décide est **P(récupérer le pair d'origine)**, et elle
demande d'être calculée avec soin, parce qu'elle ne veut pas dire la même chose
selon le mode.

Sur un AVENANT, le nominal ne bouge pas : récupérer le pair, c'est que la jambe
résiduelle rende 100 %. La probabilité se lit directement.

Sur un ROLL, le détenteur débouclé à P₀ achète k = P₀ / P_neuve unités d'une
note neuve. Son remboursement par unité de nominal D'ORIGINE vaut donc
k × payoff_neuf, et récupérer le pair exige payoff_neuf ≥ 1/k = P_neuve / P₀.
Sur le dossier Marex : P₀ = 46 %, P_neuve = 87 %, donc il faudrait que la note
neuve rende 189 % de SON pair. Autant dire jamais.

Afficher la P(≥100 %) brute de la note neuve à côté de celle d'un avenant
ferait exactement le contresens que ces chiffres révèlent : 54 % contre 28 %
donnerait le roll gagnant, alors qu'il plafonne la récupération à 53 % du
nominal d'origine.

Le tableau porte donc les deux : la probabilité ramenée au nominal d'origine, et
le plafond de récupération. Un chiffre sans son plafond n'est pas comparable.

Note de méthode : le corps de requête du PARENT est fourni par l'écran, tel
qu'il l'envoie pour afficher son prix. Rien n'est reconstruit ici. Une seconde
voie de construction — même soignée — finirait par produire des unités ou des
dates légèrement autres, et le tableau classerait des produits que l'écran ne
price pas.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from ..core.variants import MODE_ROLL, VariantError, params_moteur, resoudre
from ..db.database import get_session
from ..db.models import Script, User
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

    lignes = [{
        "id": None, "titre": "Origine", "mode": "",
        "prix": p0, "ecart": 0.0,
        # Nominal inchangé : récupérer le pair, c'est que la jambe rende 100 %.
        "proba_pair_origine": origine.get("prob_gt100"),
        "plafond": 1.0,
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
        try:
            ctx = resoudre(_contexte(parent), delta, mode)
            corps = (_corps_roll if mode == MODE_ROLL else _corps_avenant)(corps_base, ctx)
            res = _prix(corps, current)
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
        if mode == MODE_ROLL:
            # k unités d'une note neuve pour P₀ de valeur débouclée.
            k = (p0 / prix) if prix > 0 else 0.0
            plafond = k
            # Récupérer le pair D'ORIGINE exige payoff_neuf ≥ 1/k.
            proba = _proba_pair(res, 1.0 / k) if k > 0 else 0.0
        else:
            plafond = 1.0
            proba = res.get("prob_gt100")

        lignes.append({
            "id": v.id, "titre": v.variant_title, "mode": mode,
            "prix": prix, "ecart": round(prix - p0, 6),
            "proba_pair_origine": proba, "plafond": round(plafond, 6),
            "duree": res.get("fugit"),
            "ecarts": len(delta.get("set") or {}) + len(delta.get("removed") or []),
        })

    return {"lignes": lignes, "N": req.N,
            "valuation_date": origine.get("valuation_date"),
            "in_life": origine.get("in_life", False)}


def _refus(v: Script, mode: str, delta: dict, motif: str) -> dict:
    """Une ligne qui dit pourquoi elle n'a pas de prix.

    L'omettre laisserait croire que la variante n'existe pas ; lui donner un
    prix nul la ferait classer dernière. Un refus se lit."""
    return {
        "id": v.id, "titre": v.variant_title, "mode": mode,
        "prix": None, "ecart": None, "proba_pair_origine": None,
        "plafond": None, "duree": None,
        "ecarts": len(delta.get("set") or {}) + len(delta.get("removed") or []),
        "refus": motif,
    }


def _params_moteur_http(script: str, params_affichage: dict) -> dict:
    """`params_moteur`, avec le refus traduit en 422 plutôt qu'en trace."""
    try:
        return params_moteur(script, params_affichage)
    except ValueError as e:
        raise HTTPException(422, f"Script de variante illisible : {e}")
