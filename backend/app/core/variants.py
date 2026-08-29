"""Variantes d'un deal : un delta, jamais une copie.

Une variante ne stocke que ce qui DIFFÈRE de son parent. Ce n'est pas une
économie d'octets, c'est ce qui rend possibles les deux exigences d'affichage
sans lesquelles l'outil ne sert à rien :

  - **colorer ce qui a changé** est gratuit, parce que la couleur est
    l'appartenance au delta et non le résultat d'une comparaison qu'il faudrait
    refaire à chaque affichage, sur les bons champs, sans en oublier ;
  - **griser ce qui a été retiré** est simplement IMPOSSIBLE avec une copie.
    Dans une copie, un sous-jacent retiré est absent, et rien ne distingue « on
    l'a enlevé » de « il n'y a jamais été ». Le delta, lui, porte le retrait
    comme un fait, et le parent garde la fiche complète à afficher en grisé.

Conséquence assumée : une variante SUIT son parent. Repricer l'origine avec les
spots du jour déplace toutes ses variantes — c'est la seule façon de comparer à
marché constant, et c'est l'usage dominant. Figer une variante devenue une
proposition client est une action explicite, qui en fait une copie datée.

Adressage — cinq espaces de noms, choisis pour rester lisibles dans un diff :

    script                        le texte du payoff, en entier
    params[NOM]                   un PARAM
    constats[NOM].<champ>         un champ de calendrier (dont end_date)
    underlyings[NOM].<champ>      un membre du panier, ou l'un de ses champs
    global.<clé>[.<sous-clé>…]    le reste : dates, modèle, taux, funding...

Deux notations, et la distinction est nette : les **crochets** encadrent un nom
choisi par l'utilisateur, le **point** sépare des clés de structure. Ce n'est
pas de la coquetterie — les sous-jacents s'appellent `GLE.PA`, `STLAM.MI`,
`STMPA.PA`. Un adressage entièrement pointé coupait `underlyings.GLE.PA` en
« sous-jacent GLE, champ PA », c'est-à-dire sur le cas normal.

Les sous-jacents s'adressent par NOM et non par rang : retirer le deuxième
décalerait tous les suivants, et un delta écrit avant le retrait désignerait
ensuite un autre titre.
"""
from __future__ import annotations

import copy
import re

MODE_AVENANT = "avenant"
MODE_ROLL = "roll"
MODES = (MODE_AVENANT, MODE_ROLL)

ESPACES = ("script", "params", "constats", "underlyings", "global")


class VariantError(ValueError):
    """Delta incohérent — refus métier, traduit en 422 par l'appelant."""


def contexte_vide() -> dict:
    return {"script_text": "", "params": {}, "constats": {}, "global": {}}


# `espace[NOM]` puis, facultativement, `.champ.sous_champ`.
_NOMME = re.compile(r"^(params|constats|underlyings)\[([^\]]+)\](?:\.(.+))?$")


def _fendre(chemin: str) -> tuple[str, str | None, list[str]]:
    """(espace, nom, champs) — ou VariantError si le chemin ne se lit pas."""
    texte = str(chemin).strip()
    if texte == "script":
        return "script", None, []
    m = _NOMME.match(texte)
    if m:
        espace, nom, reste = m.group(1), m.group(2).strip(), m.group(3)
        if not nom:
            raise VariantError(f"Nom vide dans {chemin!r}.")
        return espace, nom, [c for c in (reste or "").split(".") if c]
    morceaux = [m_ for m_ in texte.split(".") if m_]
    if morceaux and morceaux[0] == "global" and len(morceaux) > 1:
        return "global", None, morceaux[1:]
    if morceaux and morceaux[0] in ("params", "constats", "underlyings"):
        raise VariantError(
            f"Chemin {chemin!r} : un nom s'écrit entre crochets — "
            f"{morceaux[0]}[{'.'.join(morceaux[1:]) or 'NOM'}]. Les sous-jacents "
            f"portent un point dans leur nom (GLE.PA), un chemin tout pointé les "
            f"couperait en deux.")
    raise VariantError(
        f"Chemin inconnu : {chemin!r} — attendu script, "
        f"params[NOM], constats[NOM].champ, underlyings[NOM].champ ou global.clé.")


def canonique(chemin: str) -> str:
    """La forme normalisée d'un chemin — `constats[ OBS ].end_date` → `constats[OBS].end_date`.

    Comparer des chemins bruts laisserait un espace parasite décaler une date que
    l'utilisateur venait de fixer à la main, et rien à l'écran ne le dirait."""
    espace, nom, champs = _fendre(chemin)
    if espace == "script":
        return "script"
    if espace == "global":
        return "global." + ".".join(champs)
    suffixe = ("." + ".".join(champs)) if champs else ""
    return f"{espace}[{nom}]{suffixe}"


def _underlying(ctx: dict, nom: str) -> dict | None:
    for u in ctx["global"].get("underlyings") or []:
        if u.get("name") == nom:
            return u
    return None


# ── Application d'un delta ──────────────────────────────────────────

def resoudre(parent: dict, delta: dict | None, mode: str = MODE_AVENANT) -> dict:
    """Le contexte effectif d'une variante : le parent, puis ses écarts.

    `parent` est le contexte complet ({script_text, params, constats, global}),
    `delta` la forme {"set": {chemin: valeur}, "removed": [chemin]}. Ce qui n'y
    figure pas est HÉRITÉ — jamais remplacé par un défaut. C'est la propriété
    qui garantit qu'une variante compare bien « toutes choses égales par
    ailleurs » : un champ qu'on n'a pas voulu changer ne peut pas dériver.
    """
    ctx = copy.deepcopy(parent)
    delta = delta or {}
    # Les RETRAITS d'abord, les ajouts ensuite. Sur un remplacement de titre —
    # « je sors le nom qui bloque et j'en mets un autre » — l'ordre inverse
    # exigerait de l'entrant une corrélation avec le sortant, c'est-à-dire avec
    # un titre sur le point de disparaître. Rien d'autre n'est sensible à
    # l'ordre : `valider` refuse déjà qu'un chemin soit à la fois modifié et
    # retiré.
    for chemin in (delta.get("removed") or []):
        _retirer(ctx, _fendre(chemin), mode)
    for chemin, valeur in (delta.get("set") or {}).items():
        _poser(ctx, _fendre(chemin), valeur, mode)
    if mode == MODE_ROLL:
        # Le recalage des dates fait partie de la résolution : l'appelant ne
        # doit pas avoir à savoir quel mode demande quel post-traitement, sous
        # peine qu'un chemin l'oublie et price une note neuve sur l'axe des
        # temps de l'ancienne.
        ctx = deriver_roll(ctx, {canonique(c) for c in (delta.get("set") or {})})
    return ctx


def _poser(ctx: dict, adresse: tuple, valeur, mode: str) -> None:
    espace, nom, champs = adresse
    if espace == "script":
        ctx["script_text"] = valeur
        return
    if espace == "params":
        ctx["params"][nom] = valeur
        return
    if espace == "constats":
        if not champs:
            ctx["constats"][nom] = valeur
            return
        ctx["constats"].setdefault(nom, {})[".".join(champs)] = valeur
        return
    if espace == "underlyings":
        _exiger_panier_modifiable(mode, "toucher au panier")
        if champs:
            # Un chemin par champ ne désigne plus rien de légitime. Sur un nom
            # HÉRITÉ, la calibration est une hypothèse de marché : la changer
            # ferait comparer des déclinaisons sur des marchés différents, et
            # l'écart de prix mesurerait le changement d'hypothèse au lieu de la
            # restructuration. Sur un nom AJOUTÉ, il n'y a rien à modifier — sa
            # définition arrive en bloc, puisqu'il n'a aucun parent dont hériter.
            raise VariantError(
                f"Un champ de sous-jacent ne se modifie pas ({nom}."
                f"{'.'.join(champs)}). La calibration d'un titre du panier est une "
                f"hypothèse de MARCHÉ, commune à toute la famille : la changer "
                f"casserait la comparaison à marché constant — c'est un scénario, "
                f"pas une déclinaison. Pour remplacer un titre : retirez-le, puis "
                f"ajoutez le nouveau avec sa définition complète.")
        if _underlying(ctx, nom) is not None:
            raise VariantError(
                f"« {nom} » est déjà au panier. Remplacer un titre en bloc n'est "
                f"pas permis : retirez-le puis ajoutez le nouveau, pour que "
                f"l'écran puisse montrer les deux.")
        _ajouter_au_panier(ctx, nom, valeur)
        return
    # global.<clé>[.<sous-clé>…]
    _exiger_globale_amendable(mode, champs)
    noeud = ctx["global"]
    for cle in champs[:-1]:
        noeud = noeud.setdefault(cle, {})
    noeud[champs[-1]] = valeur


def _retirer(ctx: dict, adresse: tuple, mode: str) -> None:
    espace, nom, champs = adresse
    if espace == "params":
        ctx["params"].pop(nom, None)
        return
    if espace == "underlyings":
        _exiger_panier_modifiable(mode, "retirer un sous-jacent")
        if champs:
            raise VariantError(
                f"Un champ de sous-jacent ne se retire pas ({nom}.{'.'.join(champs)}) : "
                f"c'est le titre entier qui sort du panier, ou rien.")
        _retirer_du_panier(ctx, nom)
        return
    if espace == "global":
        noeud = ctx["global"]
        for cle in champs[:-1]:
            noeud = noeud.get(cle) or {}
        noeud.pop(champs[-1], None)
        return
    raise VariantError(
        "Un retrait ne s'applique qu'à params[NOM], underlyings[NOM] ou global.clé "
        f"— reçu l'espace {espace!r}.")


# Les dates dont dépend le REJEU du passé. Un avenant ne peut pas y toucher :
# elles définissent l'origine de l'axe des temps et la fenêtre déjà constatée.
_DATES_FIGEES_EN_AVENANT = {
    "strike_date": "la constatation initiale, origine de l'axe des temps",
    "value_date": "la date de valeur, déjà échue",
    "valuation_date": "la date de valorisation, qui n'est pas un terme du produit",
    "trade_date": "la date de négociation, déjà passée",
}


def _exiger_globale_amendable(mode: str, champs: list[str]) -> None:
    """Certaines dates ne s'amendent pas — elles portent le passé.

    Déplacer la date de strike d'un avenant déplace l'ORIGINE de l'axe des
    temps : le passé n'est plus rejoué au bon endroit, et le prix reste
    parfaitement plausible. La table de flux reste même cohérente avec lui.
    Rien ne signalerait que le produit valorisé n'est plus celui qui a été émis.

    La date de valorisation n'est pas non plus un terme du produit : la changer
    est une re-valorisation, pas une restructuration, et ferait comparer des
    déclinaisons à des dates différentes.

    Ce qui reste amendable : la date de PAIEMENT final, et la maturité — qui
    passe par la fin de calendrier (`constats[NOM].end_date`), déjà autorisée.
    """
    if mode != MODE_AVENANT or not champs:
        return
    motif = _DATES_FIGEES_EN_AVENANT.get(champs[0])
    if motif:
        raise VariantError(
            f"Un avenant ne peut pas changer {champs[0]} — c'est {motif}. Le passé "
            f"a été rejoué dessus ; le déplacer donnerait un prix qui ne décrit plus "
            f"le produit émis. Passez en mode nouvelle note (roll), qui est strikée "
            f"aujourd'hui.")


def _exiger_panier_modifiable(mode: str, action: str) -> None:
    """En avenant, le panier est figé — et c'est une règle de structuration.

    Retirer un nom change le sens de `WOF`. Les flux réalisés restent justes,
    ils ont eu lieu ; mais les extrema repris du rejeu décrivent un worst-of à
    quatre noms, et rien ne dit ce qu'ils deviennent à trois. Ce n'est donc pas
    un avenant : c'est une note neuve, et le mode roll est là pour ça."""
    if mode == MODE_AVENANT:
        raise VariantError(
            f"Impossible de {action} sur un avenant : le passé a été rejoué sur "
            f"le panier d'origine, et les extrema qui en sont repris décrivent "
            f"ce panier-là. Passez en mode nouvelle note (roll).")


def _ajouter_au_panier(ctx: dict, nom: str, definition) -> None:
    """Ajoute un titre au panier, ET sa ligne de corrélation.

    Un nom ajouté n'a pas de parent : sa définition arrive donc entière, ce qui
    n'est pas une exception à la règle « la calibration ne se modifie pas », mais
    le cas où cette règle n'a rien à quoi s'appliquer.

    Les corrélations avec les titres survivants sont EXIGÉES. L'écran remplit un
    couple manquant par zéro, en silence — sur un worst-of, une corrélation nulle
    n'est pas un défaut neutre, elle déplace fortement le prix. Que l'écran
    fournisse zéro est son affaire ; que le delta le PORTE explicitement est la
    nôtre, parce qu'il devient alors visible dans le panneau des écarts au lieu
    d'agir sans que personne l'ait vu.
    """
    if not isinstance(definition, dict):
        raise VariantError(
            f"L'ajout de « {nom} » attend sa définition complète (volatilité, "
            f"dividende, corrélations), pas {type(definition).__name__}.")

    fiche = {k: v for k, v in definition.items() if k != "correlations"}
    fiche["name"] = nom
    correlations = definition.get("correlations") or {}

    paniers = ctx["global"].setdefault("underlyings", [])
    existants = [u.get("name") for u in paniers]
    manquantes = [n for n in existants if n not in correlations]
    if manquantes:
        raise VariantError(
            f"Corrélation manquante entre « {nom} » et {', '.join(manquantes)}. "
            f"Un panier dont une corrélation n'est pas saisie n'est pas "
            f"valorisable : la matrice serait complétée d'office, et personne "
            f"n'aurait choisi la valeur qui price.")

    matrice = ctx["global"].get("corr_matrix") or []
    if len(matrice) != len(paniers):
        raise VariantError(
            f"Matrice de corrélation incohérente avec le panier "
            f"({len(matrice)} lignes pour {len(paniers)} titres) : impossible de "
            f"l'étendre sans deviner.")
    ligne = [float(correlations[n]) for n in existants]
    nouvelle = [[*row, ligne[i]] for i, row in enumerate(matrice)]
    nouvelle.append([*ligne, 1.0])
    paniers.append(fiche)
    ctx["global"]["corr_matrix"] = nouvelle


def _retirer_du_panier(ctx: dict, nom: str) -> None:
    """Retire un sous-jacent ET la ligne/colonne correspondante de la corrélation.

    Les deux ne se séparent pas : une matrice 4×4 pour trois noms est soit
    refusée par le moteur, soit « réparée » en silence — et une corrélation
    réparée d'office est une hypothèse que personne n'a saisie."""
    paniers = ctx["global"].get("underlyings") or []
    noms = [u.get("name") for u in paniers]
    if nom not in noms:
        raise VariantError(f"Sous-jacent inconnu dans le deal d'origine : {nom}")
    if len(paniers) <= 1:
        raise VariantError("Un produit doit garder au moins un sous-jacent.")
    i = noms.index(nom)
    ctx["global"]["underlyings"] = [u for k, u in enumerate(paniers) if k != i]
    matrice = ctx["global"].get("corr_matrix") or []
    if len(matrice) == len(paniers):
        ctx["global"]["corr_matrix"] = [
            [v for c, v in enumerate(ligne) if c != i]
            for l, ligne in enumerate(matrice) if l != i]


# ── Ce que l'écran doit montrer ─────────────────────────────────────

def decrire_ecarts(parent: dict, delta: dict | None) -> list[dict]:
    """Les écarts, prêts à colorer — un par chemin, avec l'avant et l'après.

    C'est le delta lui-même, enrichi de la valeur du parent pour que l'écran
    puisse écrire « 50 % → 30 % » sans relire les deux contextes. `etat` vaut
    `modifie` ou `retire` : un retrait garde sa valeur d'origine, puisqu'il
    s'affiche en grisé plutôt que de disparaître."""
    delta = delta or {}
    ecarts = []
    for chemin, valeur in (delta.get("set") or {}).items():
        ecarts.append({"chemin": chemin, "etat": "modifie",
                       "avant": lire(parent, chemin), "apres": valeur})
    for chemin in (delta.get("removed") or []):
        ecarts.append({"chemin": chemin, "etat": "retire",
                       "avant": lire(parent, chemin), "apres": None})
    ecarts.sort(key=lambda e: e["chemin"])
    return ecarts


def lire(ctx: dict, chemin: str):
    """La valeur d'un chemin dans un contexte, ou None s'il n'y en a pas."""
    try:
        espace, nom, champs = _fendre(chemin)
    except VariantError:
        return None
    if espace == "script":
        return ctx.get("script_text")
    if espace == "params":
        return (ctx.get("params") or {}).get(nom)
    if espace == "constats":
        noeud = (ctx.get("constats") or {}).get(nom)
        return _descendre(noeud, champs)
    if espace == "underlyings":
        u = _underlying(ctx, nom)
        if u is None or not champs:
            return u
        return _descendre(u, champs)
    return _descendre(ctx.get("global") or {}, champs)


def _descendre(noeud, champs):
    for cle in champs:
        if not isinstance(noeud, dict):
            return None
        noeud = noeud.get(cle)
    return noeud


def valider(delta: dict | None, mode: str) -> None:
    """Refuse un delta mal formé avant qu'il n'atteigne la base.

    Un delta invalide stocké est bien pire qu'un delta refusé : il ne se
    manifeste qu'à la relecture, longtemps après, sur une variante qu'on croyait
    bonne."""
    if mode not in MODES:
        raise VariantError(f"Mode inconnu : {mode!r} — attendu {' ou '.join(MODES)}.")
    delta = delta or {}
    inconnues = set(delta) - {"set", "removed"}
    if inconnues:
        raise VariantError(f"Clés inattendues dans le delta : {', '.join(sorted(inconnues))}.")
    if not isinstance(delta.get("set", {}), dict):
        raise VariantError("`set` doit être un objet {chemin: valeur}.")
    if not isinstance(delta.get("removed", []), list):
        raise VariantError("`removed` doit être une liste de chemins.")
    for chemin in list(delta.get("set") or {}) + list(delta.get("removed") or []):
        _fendre(chemin)
    doublons = set(delta.get("set") or {}) & set(delta.get("removed") or [])
    if doublons:
        raise VariantError(
            f"Chemin à la fois modifié et retiré : {', '.join(sorted(doublons))}.")


# ── Le roll : une note neuve, strikée aujourd'hui ───────────────────
#
# Un roll n'est pas un avenant paramétré autrement, c'est un autre produit. Le
# client débouclé vend sa note à sa valeur du jour et en achète une neuve : il
# n'y a plus de passé à rejouer, la première constatation est aujourd'hui, et
# les cours du jour deviennent le nouveau 100 %. Tout redevient libre — panier,
# calendrier, payoff — précisément parce que rien n'est hérité de l'histoire.
#
# Ce qui suit ne fait donc qu'une chose : déplacer l'axe des temps. Les
# hypothèses de marché (vol, dividendes, corrélation) ont été calibrées à la
# date de valorisation, elles sont déjà les bonnes.

# Les dates que porte le contexte global, et ce qu'elles deviennent.
_DATES_GLOBALES = ("trade_date", "strike_date", "value_date", "payment_date")
_DATES_CONSTAT = ("start_date", "roll_date", "end_date")


def _decaler(iso: str, jours: int) -> str:
    from datetime import date, timedelta
    try:
        return (date.fromisoformat(str(iso)) + timedelta(days=jours)).isoformat()
    except (TypeError, ValueError):
        return iso


def deriver_roll(ctx: dict, figes: set) -> dict:
    """Recale un contexte sur un strike d'aujourd'hui.

    `figes` porte les chemins que le delta a explicitement fixés : ceux-là ne
    bougent pas. L'ordre compte — on applique le delta D'ABORD, puis on décale
    ce qu'il n'a pas fixé. L'inverse décalerait une maturité que l'utilisateur
    venait de saisir à la main, ce qui est le genre de chose qu'on ne remarque
    qu'en relisant un term sheet.

    Le décalage préserve le TÉNOR : une note de trois ans se roule en trois ans
    à partir d'aujourd'hui. Une autre durée se demande explicitement, en fixant
    la fin de calendrier dans le delta.
    """
    g = ctx["global"]
    ancien, nouveau = g.get("strike_date"), g.get("valuation_date") or g.get("strike_date")
    if not (ancien and nouveau):
        # Distinguer les deux causes, parce qu'elles n'appellent pas le même
        # geste. Un contexte SANS AUCUNE date vient d'un script enregistré avant
        # que les dates et le panier ne soient persistés : la date est bien à
        # l'écran, elle manque seulement dans ce qui a été sauvegardé. Envoyer
        # l'utilisateur chercher un champ à remplir le ferait tourner en rond.
        if not any(g.get(cle) for cle in _DATES_GLOBALES):
            raise VariantError(
                "Ce deal a été enregistré avant que ses dates et son panier ne "
                "soient conservés : son contexte n'en porte aucun, et une note "
                "neuve ne sait pas sur quoi se recaler. Rouvrez l'origine dans le "
                "Pricer et réenregistrez-la — les dates de l'écran seront alors "
                "sauvegardées avec elle. L'avenant, lui, fonctionne déjà.")
        raise VariantError(
            "Une note neuve a besoin d'une date de valorisation : c'est elle qui "
            "devient sa constatation initiale. Saisissez-la dans l'onglet Deal.")
    from datetime import date
    try:
        jours = (date.fromisoformat(str(nouveau)) - date.fromisoformat(str(ancien))).days
    except ValueError:
        raise VariantError(f"Dates illisibles : strike {ancien!r}, valorisation {nouveau!r}.")
    if jours < 0:
        raise VariantError(
            f"La valorisation ({nouveau}) précède la constatation initiale ({ancien}) : "
            f"il n'y a pas encore de note à rouler.")

    for cle in _DATES_GLOBALES:
        if g.get(cle) and f"global.{cle}" not in figes:
            g[cle] = _decaler(g[cle], jours)
    for nom, valeurs in (ctx.get("constats") or {}).items():
        if not isinstance(valeurs, dict):
            continue
        for cle in _DATES_CONSTAT:
            if valeurs.get(cle) and f"constats[{nom}].{cle}" not in figes:
                valeurs[cle] = _decaler(valeurs[cle], jours)

    # La note est neuve : elle se price à l'émission, et ses niveaux initiaux
    # sont les cours du jour. Laisser traîner les niveaux du term sheet
    # d'origine ferait repartir les barrières d'un strike vieux de deux ans —
    # un worst-of à 34 % serait pris pour un worst-of à 100 %.
    g["strike_date"] = str(nouveau)
    g["valuation_date"] = str(nouveau)
    g.pop("strike_levels", None)
    return ctx


# ── Unités : l'écran stocke en affichage, le moteur veut des fractions ──

def params_moteur(script: str, params_affichage: dict) -> dict:
    """Les PARAM d'un contexte stocké, convertis pour le moteur.

    `is_pct` vient du script lui-même : c'est la seule source qui sache si
    « 30 » veut dire 30 % ou 30. Un PARAM absent du script est ignoré plutôt
    que transmis — une variante peut avoir supprimé la ligne qui le déclarait,
    et l'envoyer quand même ferait porter au moteur un paramètre que son script
    ne lit pas.
    """
    from .payscript.parser import parse_script
    compiled = parse_script(script)          # ValueError remonte à l'appelant
    pct = {p.name: p.is_pct for p in compiled.params}
    sortie = {}
    for nom, v in (params_affichage or {}).items():
        if nom not in pct:
            continue
        if isinstance(v, list):
            sortie[nom] = [x / 100 if pct[nom] else x
                           for x in v if x is not None and x != ""]
        elif v is not None:
            sortie[nom] = v / 100 if pct[nom] else v
    return sortie


def termes_de_rejeu(contexte: dict) -> dict:
    """Les trois termes sous lesquels le PASSÉ doit être rejoué.

    Ce sont ceux de l'ORIGINE, et seulement ces trois-là : un avenant ne peut
    changer ni le panier, ni le strike, ni les hypothèses de marché — ils sont
    donc communs, et l'écran les porte déjà correctement.

    Rendu au client pour qu'il puisse construire sa requête sans reconstruire le
    contexte du parent : le corps principal prend ces termes, le bloc `variant`
    prend ceux de l'écran. C'est cette asymétrie qui interdit à une barrière
    abaissée de rappeler dans le passé.
    """
    return {
        "script": contexte["script_text"],
        "user_params": params_moteur(contexte["script_text"], contexte.get("params")),
        "constats": contexte.get("constats") or {},
    }
