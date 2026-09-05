"""Lecture technique d'un portefeuille client — niveaux, protections, familles.

Ce module répond à trois questions qu'un structureur pose avant d'appeler un
client : à quels **niveaux** il traite (coupon), quelles **protections** il
accepte (barrière), et si le trade s'est fait **avec nous ou ailleurs** — et
dans ce cas à quel prix.

Deux difficultés, toutes deux affrontées plutôt que contournées.

**Un deal booké ne porte pas ses niveaux en clair.** Coupon et barrière vivent
dans les PARAM du script PayScript, pas dans des colonnes. Une ligne
d'historique importée, elle, les porte explicitement. Sans extraction, l'écran
afficherait des niveaux pour les clients importés et rien pour ceux dont nous
avons booké les trades — la pire des incohérences, puisqu'elle frappe justement
les données dont nous sommes sûrs.

**PayScript n'a pas de notion formelle de « barrière ».** `AC_BAR`, `KI_BAR`
sont des conventions de nos modèles. Le projet a déjà résolu ce problème pour la
watchlist : le contrat `M_` (moniteurs déclarés, direction déduite de l'usage)
quand il existe, l'heuristique de nom sinon. On le réutilise plutôt que d'en
écrire une seconde version qui divergerait.

Ce qui n'est pas extractible reste **None** — jamais zéro. Un coupon inconnu et
un coupon nul ne se ressemblent que pour qui ne lit pas.
"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Optional, Sequence

from sqlmodel import Session, select

from ..db.models import Underlying


# ── Niveaux d'un deal booké ───────────────────────────────────────────

def _plausible_coupon(valeur: float) -> bool:
    """Un coupon se stocke en fraction (0,08 = 8 %).

    La borne haute est volontairement large — 60 % l'an existe sur un phoenix
    worst-of très risqué. La borne basse exclut zéro : un PARAM à 0 n'est pas
    un coupon, c'est un champ vide.
    """
    return 0.0 < valeur <= 0.60


def niveaux_du_script(script: Optional[str]) -> dict:
    """Coupon et protections lus dans un script PayScript.

    Rend `{"coupon_pct": float|None, "barriers": [{name, kind, level_pct}],
    "protection_pct": float|None}`. `protection_pct` est le niveau de la
    barrière de capital — la plus basse des barrières « ki », celle qui décide
    de la perte en capital.
    """
    vide = {"coupon_pct": None, "barriers": [], "protection_pct": None}
    if not script:
        return vide
    try:
        from .payscript.parser import parse_script
        compile_ = parse_script(script)
    except Exception:
        # Un snapshot illisible ne doit pas faire tomber la fiche : on rend
        # « rien » plutôt qu'une exception, et l'écran affiche « — ».
        return vide

    params = list(getattr(compile_, "params", []) or [])
    valeurs = {p.name: p.stored_val for p in params
               if isinstance(getattr(p, "stored_val", None), (int, float))}

    coupon = None
    for nom, valeur in valeurs.items():
        if "COUPON" in nom.upper() and _plausible_coupon(float(valeur)):
            coupon = round(float(valeur) * 100, 4)
            break

    barrieres: list[dict] = []
    moniteurs = getattr(compile_, "monitors", None) or []
    if moniteurs:
        # Contrat M_ explicite : la direction vient de l'usage réel du
        # paramètre dans le script, pas d'une devinette sur son nom.
        for moniteur in moniteurs:
            niveau = valeurs.get(moniteur["name"])
            if niveau is None:
                continue
            genre = {"up": "autocall", "down": "ki"}.get(
                moniteur.get("direction"), "neutre")
            barrieres.append({"name": moniteur["name"], "kind": genre,
                              "level_pct": round(float(niveau) * 100, 2)})
    else:
        # Scripts hérités, sans M_ : même heuristique que la watchlist, pour
        # que les deux écrans ne se contredisent jamais sur un même deal.
        from ..api.deals import _classify_param_barrier
        for param in params:
            valeur = getattr(param, "stored_val", None)
            if not isinstance(valeur, (int, float)):
                continue
            genre = _classify_param_barrier(param.name, float(valeur))
            if genre:
                barrieres.append({"name": param.name, "kind": genre,
                                  "level_pct": round(float(valeur) * 100, 2)})

    protections = [b["level_pct"] for b in barrieres if b["kind"] == "ki"]
    return {"coupon_pct": coupon, "barriers": barrieres,
            "protection_pct": min(protections) if protections else None}


# ── Découpage d'un panier importé ───────────────────────────────

_SEPARATEURS = re.compile(r"[/,;+|]")


def decouper_sous_jacents(texte: Optional[str]) -> list[str]:
    """Les tickers d'une cellule d'historique.

    Un deal booké porte ses sous-jacents dans un tableau JSON ; une ligne
    importée n'a qu'une colonne de texte, et un panier y arrive tel que le
    client l'écrit : « SX5E / SPX », « LVMH, Kering, Hermès ».

    Sans ce découpage, **toute transaction importée serait classée mono** — et
    comme l'historique est justement la source principale du module, les
    moyennes « panier » se seraient construites sur les seuls deals bookés ici,
    c'est-à-dire sur la minorité des données. Les séparateurs acceptés ne
    figurent dans aucune convention de ticker connue (Yahoo, Bloomberg, RIC),
    donc découper ne casse pas un symbole légitime.
    """
    if not texte:
        return []
    return [morceau.strip() for morceau in _SEPARATEURS.split(texte)
            if morceau.strip()]


# ── Familles de sous-jacents ──────────────────────────────────────────
# Le catalogue `underlyings` porte déjà la distinction dans ses groupes :
# « Indices Europe », « Actions FR (CAC) », « Banques », « Luxe »,
# « ETF / Matières premières ». On la lit plutôt que de la redéfinir.

_PREFIXES_NATURE = (
    ("indice", ("indices", "indice")),
    ("etf", ("etf", "matières premières", "matieres premieres")),
    ("action", ("actions", "banques", "luxe")),
)


def _nature_du_groupe(groupe: Optional[str]) -> Optional[str]:
    if not groupe:
        return None
    minuscule = groupe.strip().casefold()
    for nature, prefixes in _PREFIXES_NATURE:
        if any(minuscule.startswith(p) or p in minuscule for p in prefixes):
            return nature
    return None


def catalogue_natures(session: Session) -> dict[str, str]:
    """Ticker → nature, d'après le groupe du catalogue.

    Chargé une fois par lecture et passé aux appels : une requête par
    transaction transformerait l'onglet technique en N+1.
    """
    natures: dict[str, str] = {}
    for ligne in session.exec(select(Underlying)).all():
        nature = _nature_du_groupe(ligne.group_name)
        if nature:
            natures[ligne.ticker.strip().upper()] = nature
    return natures


def nature_du_sous_jacent(ticker: str,
                          natures: dict[str, str]) -> Optional[str]:
    """La nature d'un ticker : catalogue d'abord, convention Yahoo ensuite.

    Le préfixe « ^ » désigne un indice chez Yahoo — c'est un signal fiable et
    indépendant du catalogue, utile pour un sous-jacent qui n'y figure pas
    encore. Au-delà, on rend `None` : deviner qu'un ticker inconnu est une
    action produirait une moyenne fausse sans le dire.
    """
    if not ticker:
        return None
    propre = ticker.strip().upper()
    if propre in natures:
        return natures[propre]
    if propre.startswith("^"):
        return "indice"
    return None


def famille_de_panier(tickers: Sequence[str],
                      natures: dict[str, str]) -> dict:
    """Structure et nature d'un panier.

    `structure` : mono (un sous-jacent) ou multi. `nature` : indice, action,
    etf, mixte — ou None si aucun des sous-jacents n'est classable. Un panier
    dont on ne connaît qu'une partie est rendu d'après ce qu'on connaît, avec
    `partial` à True : c'est une moyenne sur une base incomplète, et l'écran
    doit pouvoir le signaler.
    """
    propres = [t for t in tickers if t]
    if not propres:
        return {"structure": None, "nature": None, "partial": False, "n": 0}

    structure = "mono" if len(propres) == 1 else "multi"
    connues = [nature_du_sous_jacent(t, natures) for t in propres]
    identifiees = {n for n in connues if n}
    if not identifiees:
        return {"structure": structure, "nature": None,
                "partial": True, "n": len(propres)}
    nature = identifiees.pop() if len(identifiees) == 1 else "mixte"
    return {"structure": structure, "nature": nature,
            "partial": any(n is None for n in connues), "n": len(propres)}


LIBELLES_FAMILLE = {
    ("mono", "indice"): "Mono-indice",
    ("mono", "action"): "Mono-action",
    ("mono", "etf"): "Mono-ETF",
    ("multi", "indice"): "Panier d'indices",
    ("multi", "action"): "Panier d'actions",
    ("multi", "etf"): "Panier d'ETF",
    ("multi", "mixte"): "Panier mixte",
    ("mono", "mixte"): "Mono",
}


def libelle_famille(structure: Optional[str], nature: Optional[str]) -> str:
    if structure is None:
        return "Sans sous-jacent renseigné"
    if nature is None:
        return f"{'Mono' if structure == 'mono' else 'Panier'} — nature inconnue"
    return LIBELLES_FAMILLE.get((structure, nature),
                                f"{structure} · {nature}")


# ── Moyennes par famille ──────────────────────────────────────────────

def _mediane(valeurs: Sequence[float]) -> Optional[float]:
    """Médiane, arrondie à quatre décimales.

    L'arrondi n'est pas cosmétique : la moyenne de 6,80 et 7,50 sort en binaire
    à 7,1499999999999995, et cette valeur part telle quelle dans le JSON de
    l'API. L'écran la remet en forme, mais tout autre consommateur — un export,
    un test d'égalité — hériterait du bruit.
    """
    if not valeurs:
        return None
    triees = sorted(valeurs)
    n = len(triees)
    brute = (float(triees[n // 2]) if n % 2
             else (triees[n // 2 - 1] + triees[n // 2]) / 2.0)
    return round(brute, 4)


SEUIL_MOYENNE = 2


def moyennes_par_famille(lignes: Sequence[dict]) -> list[dict]:
    """Coupon et protection médians, par famille de sous-jacent.

    La médiane, comme partout dans ce module. Et un seuil : sous deux
    observations, aucune moyenne n'est rendue — le coupon d'une transaction
    unique n'est pas une moyenne, c'est ce coupon-là, et le présenter comme une
    tendance ferait croire à une régularité qui n'existe pas.
    """
    groupes: dict[tuple, list[dict]] = defaultdict(list)
    for ligne in lignes:
        groupes[(ligne.get("structure"), ligne.get("nature"))].append(ligne)

    sortie = []
    for (structure, nature), items in groupes.items():
        coupons = [i["coupon_pct"] for i in items if i.get("coupon_pct") is not None]
        protections = [i["protection_pct"] for i in items
                       if i.get("protection_pct") is not None]
        # Ce que la famille mélange. Une médiane de protection sur un capital
        # garanti (100 %) et un autocall (60 %) donne 80 %, chiffre exact et
        # dépourvu de sens : la famille est celle du SOUS-JACENT, pas celle du
        # payoff. Nommer les types réunis laisse le lecteur voir ce qu'il lit.
        types = sorted({(i.get("product_type") or "").strip()
                        for i in items if (i.get("product_type") or "").strip()})
        sortie.append({
            "structure": structure, "nature": nature,
            "label": libelle_famille(structure, nature),
            "product_types": types,
            "n_trades": len(items),
            "n_coupons": len(coupons),
            "median_coupon_pct": (_mediane(coupons)
                                  if len(coupons) >= SEUIL_MOYENNE else None),
            "median_protection_pct": (_mediane(protections)
                                      if len(protections) >= SEUIL_MOYENNE else None),
            # Le coupon seul quand il n'y en a qu'un : le fait vaut mieux que
            # le vide, tant qu'il n'est pas présenté comme une médiane.
            "single_coupon_pct": coupons[0] if len(coupons) == 1 else None,
            "partial": any(i.get("partial") for i in items),
        })
    return sorted(sortie, key=lambda g: -g["n_trades"])


def repartition_execution(lignes: Sequence[dict]) -> dict:
    """Avec nous, ailleurs, ou inconnu — et à quel prix ailleurs.

    Les trois états sont rendus séparément. Fondre « inconnu » dans « ailleurs »
    gonflerait la part de marché qu'on croit ne pas avoir, et fausserait
    exactement la lecture pour laquelle ce champ existe.
    """
    avec, ailleurs, inconnu = [], [], []
    for ligne in lignes:
        cible = {True: avec, False: ailleurs}.get(ligne.get("traded_with_us"), inconnu)
        cible.append(ligne)

    prix_ailleurs = [l["price_pct"] for l in ailleurs if l.get("price_pct") is not None]
    prix_avec = [l["price_pct"] for l in avec if l.get("price_pct") is not None]
    return {
        "with_us": len(avec), "elsewhere": len(ailleurs), "unknown": len(inconnu),
        "median_price_elsewhere": _mediane(prix_ailleurs),
        "median_price_with_us": _mediane(prix_avec),
        "n_priced_elsewhere": len(prix_ailleurs),
    }
