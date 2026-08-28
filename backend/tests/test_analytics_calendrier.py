"""Toutes les analytiques doivent voir le MÊME produit que le prix.

Un CONSTAT portant un décalage de règlement faisait échouer le profil de payoff,
les chemins MC, les probabilités, le Mark-to-Future, le backtest, le solveur, la
grille et les scénarios — avec « un décalage de règlement suppose un calendrier :
précisez la devise de règlement » — alors que /api/price, lui, passait.

La cause était unique et bête : `resolve_constats` était appelé avec le seul
`anchor`, sans devise, dans onze endroits différents. Sans devise il n'y a aucun
calendrier de jours ouvrés sur lequel compter le décalage.

Ce fichier teste la RÈGLE plutôt qu'un endpoint : tout modèle de requête
d'analyse doit porter de quoi résoudre le calendrier, et le résolveur partagé
doit s'ancrer sur le strike. Un nouvel endpoint qui oublierait de passer par
`resolve_analysis_constats` retombera dans le même trou — d'où le test
d'inventaire qui interdit les appels nus.
"""
import datetime as dt
import re
from pathlib import Path

import pytest

from backend.app.core.payscript.parser import (
    parse_script, resolve_analysis_constats,
)
from backend.app.core import schemas

RACINE = Path(__file__).resolve().parents[2]

# Deux PARAM : la grille 2D a besoin de deux axes distincts.
SCRIPT = """PARAM COUPON = 2%
PARAM M_BAR = 50%

CONSTAT() OBS

AT OBS:
  PAY COUPON

AT OBS.last:
  SET KI = INDIC(WOF < M_BAR)
  PAY (1 - KI) * 1
  PAY KI * WOF
"""

# Un calendrier qui porte les deux choses qui manquaient : une convention de
# jour ouvré et un décalage de règlement.
CALENDRIER = {"OBS": {"start_date": "2024-06-14", "end_date": "2027-06-14",
                       "roll_date": "2024-09-14", "frequency": "3M",
                       "stub": "short_last", "convention": "following",
                       "settlement_lag": 7}}

# Les modèles de requête de chaque action lançable depuis le Pricer.
MODELES = [
    "ProfileRequest", "PathsRequest", "ProbaRequest", "BacktestRequest",
    "MtfRequest", "MtfDrilldownRequest", "SolverRequest", "GridRequest",
    "ScenarioRequest",
]


def _champs_communs():
    return dict(
        script=SCRIPT,
        underlyings=[schemas.UnderlyingParams(name="U1", ticker="UL.PA")],
        corr_matrix=[[1.0]],
        constats=CALENDRIER,
        strike_date=dt.date(2024, 6, 14),
        settlement_ccy="EUR",
    )


@pytest.mark.parametrize("nom", MODELES)
def test_chaque_requete_d_analyse_resout_son_calendrier(nom):
    """Le décalage de règlement ne doit plus faire échouer une seule analytique."""
    modele = getattr(schemas, nom)
    extra = {}
    # Quelques modèles ont des champs requis qui leur sont propres.
    for champ, valeur in (("main_price", 1.0), ("t", 1.0), ("param_name", "COUPON"),
                          ("target_price", 1.0), ("lo", 0.0), ("hi", 0.1),
                          ("param_x", "COUPON"), ("x_min", 0.0), ("x_max", 0.1),
                          ("param_y", "COUPON"), ("y_min", 0.0), ("y_max", 0.1),
                          ("scenario_ids", [0])):
        if champ in modele.model_fields:
            extra[champ] = valeur
    req = modele(**_champs_communs(), **extra)
    compiled = resolve_analysis_constats(parse_script(SCRIPT), req)
    assert compiled.events, nom


def test_le_calendrier_resolu_est_celui_du_prix():
    """Même produit, mêmes dates — sinon l'analytique décrit autre chose.

    Contrôle direct : la première constatation tombe le 16/09/2024, c'est-à-dire
    le 14 (samedi) reporté au lundi par la convention, et son règlement sept
    jours ouvrés plus tard. Si l'ancrage repartait de la value date ou si la
    convention était perdue, ces deux nombres bougeraient."""
    req = schemas.ProfileRequest(**_champs_communs())
    compiled = resolve_analysis_constats(parse_script(SCRIPT), req)
    ev = compiled.events[0]
    # 16/09/2024 = 0,2574 an après le strike du 14/06/2024 — le 14 était un
    # samedi, reporté au lundi par la convention *following*.
    assert ev.dates[0] == pytest.approx(0.2574, abs=1e-3), ev.dates[:2]
    # Le règlement suit sept jours ouvrés plus loin, jamais confondu avec lui.
    assert ev.payment_dates is not None, "décalage de règlement perdu"
    assert ev.payment_dates[0] > ev.dates[0]


def test_sans_devise_le_refus_reste_explicite():
    """Le message d'erreur d'origine était juste — il désignait une donnée que
    le front oubliait d'envoyer. On ne le remplace pas par un silence."""
    req = schemas.ProfileRequest(**{**_champs_communs(), "settlement_ccy": None})
    with pytest.raises(ValueError, match="décalage de règlement suppose un calendrier"):
        resolve_analysis_constats(parse_script(SCRIPT), req)


def test_aucun_endpoint_ne_resout_son_calendrier_a_la_main():
    """Inventaire : plus aucun appel nu à resolve_constats dans les endpoints.

    C'est ce test qui empêche la rechute. Onze points d'appel avaient divergé
    parce que chacun appelait le résolveur bas niveau directement ; le jour où
    la devise est devenue nécessaire, dix ne l'ont pas su."""
    nus = []
    for fichier in sorted((RACINE / "backend" / "app" / "api").glob("*.py")):
        for num, ligne in enumerate(fichier.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"resolve_constats\(compiled, req\.constats", ligne):
                nus.append(f"{fichier.name}:{num}")
    assert not nus, ("Ces endpoints résolvent leur calendrier à la main au lieu "
                     f"de passer par resolve_analysis_constats : {nus}")


def test_tout_appel_a_resolve_constats_passe_une_devise():
    """L'invariant réel, workers parallèles compris.

    Le test d'inventaire précédent ne regardait que les endpoints. Or la grille
    de scénarios et la VaR repricent chaque cellule dans un PROCESSUS séparé qui
    re-parse le script depuis une charge sérialisée : ces workers appelaient
    `resolve_constats` sans devise, et la grille échouait quand le prix simple
    passait. Un appel qui ne passe pas `currency=` ne sait pas compter un
    décalage de règlement.
    """
    manquants = []
    for fichier in sorted((RACINE / "backend" / "app").rglob("*.py")):
        lignes = fichier.read_text(encoding="utf-8").splitlines()
        for num, ligne in enumerate(lignes):
            if "resolve_constats(" not in ligne:
                continue
            if ligne.lstrip().startswith(("def ", "from ", "import ", "#")):
                continue
            # L'appel peut s'étaler sur plusieurs lignes.
            fenetre = " ".join(lignes[num:num + 8])
            if "currency=" not in fenetre:
                manquants.append(f"{fichier.relative_to(RACINE)}:{num + 1}")
    assert not manquants, ("Ces appels à resolve_constats ne passent pas de devise, "
                           f"ils échoueront sur tout décalage de règlement : {manquants}")


def test_la_grille_de_scenarios_survit_a_un_decalage_de_reglement():
    """Bout en bout sur le chemin multi-processus.

    Le contrôle statique ci-dessus ne prouve pas que la devise voyage bien
    jusqu'au worker — elle traverse une charge sérialisée et deux signatures de
    fonction. Ce test le vérifie en exécutant vraiment la grille."""
    from backend.app.api import scenarios as api_scenarios
    req = schemas.ScenarioRequest(**_champs_communs(), spot_shocks=[0.0],
                                   vol_shocks=[0.0], N=1000)
    res = api_scenarios.scenarios_endpoint(req)
    assert res, "grille vide"


# ── Alignement sur la vie restante ────────────────────────────────────

def test_le_profil_de_payoff_bascule_sur_la_jambe_residuelle():
    """Le profil doit décrire la note telle qu'elle EST, pas telle qu'émise.

    Sur un produit à mémoire déjà en cours de vie, deux choses changent : il
    reste moins de coupons à toucher, et le solde accumulé se libère au rappel.
    La courbe ne peut donc pas être la même — si ce test passe au vert avec des
    profils identiques, c'est que l'état du passé n'atteint plus l'évaluation.
    """
    from backend.app.api import pricing as api_pricing
    commun = dict(_champs_communs(), T=3.0, value_date=dt.date(2024, 6, 18),
                   maturity_date=dt.date(2027, 6, 14))
    emission = api_pricing.profile_endpoint(schemas.ProfileRequest(**commun))
    assert emission["in_life"] is False

    en_vie = api_pricing.profile_endpoint(schemas.ProfileRequest(
        **commun, valuation_date=dt.date(2026, 6, 14)))
    assert en_vie["in_life"] is True
    assert en_vie["years_remaining"] < 1.1, en_vie["years_remaining"]
    assert en_vie["payoffs"] != emission["payoffs"], (
        "le profil en cours de vie est identique à celui de l'émission : "
        "l'état du passé n'atteint pas l'évaluation")


def test_une_analytique_sans_date_de_valorisation_reste_a_l_emission():
    """Le mode ne se choisit pas, il se déduit — et l'absence de date de
    valorisation doit reproduire exactement le comportement historique."""
    from backend.app.api import pricing as api_pricing
    res = api_pricing.profile_endpoint(schemas.ProfileRequest(
        **_champs_communs(), T=3.0))
    assert res["in_life"] is False
    assert "years_remaining" not in res


def test_les_probabilites_basculent_sur_la_jambe_residuelle():
    """Le chiffre qui trahissait le défaut : la durée espérée.

    Une durée espérée de 2,12 ans sur un produit auquel il reste 1,10 an est
    arithmétiquement impossible — c'était la signature d'une analyse menée sur
    le produit NEUF. Elle doit désormais tenir dans la vie restante.
    """
    from backend.app.api import pricing as api_pricing
    commun = dict(_champs_communs(), T=3.0, value_date=dt.date(2024, 6, 18),
                   maturity_date=dt.date(2027, 6, 14), N=2000)
    em = api_pricing.proba_endpoint(schemas.ProbaRequest(**commun))
    assert em["in_life"] is False

    vie = api_pricing.proba_endpoint(schemas.ProbaRequest(
        **commun, valuation_date=dt.date(2026, 6, 14)))
    assert vie["in_life"] is True
    reste = vie["years_remaining"]
    assert vie["expected_life"] <= reste + 1e-6, (
        f"durée espérée {vie['expected_life']} > vie restante {reste} : "
        "l'analyse porte encore sur le produit à l'émission")
    assert em["expected_life"] > reste, "le cas à l'émission devrait dépasser le résiduel"


def test_les_chemins_partent_du_niveau_du_jour():
    """Les trajectoires affichées doivent démarrer là où le produit EST.

    Sans le spot du jour, l'éventail repart de 100 % du strike — sur une note
    dont le worst-of a décroché, il montre des chemins qui n'existent pas.
    """
    from backend.app.api import pricing as api_pricing
    commun = dict(_champs_communs(), T=3.0, value_date=dt.date(2024, 6, 18),
                   maturity_date=dt.date(2027, 6, 14), N_stat=200, N_display=10)
    vie = api_pricing.paths_endpoint(schemas.PathsRequest(
        **commun, valuation_date=dt.date(2026, 6, 14)))
    assert vie["in_life"] is True
    assert vie["years_remaining"] < 1.1


@pytest.mark.parametrize("nom,appel", [
    ("solveur", lambda c, v: __import__(
        "backend.app.api.simulation", fromlist=["x"]).solve_endpoint(
        schemas.SolverRequest(**c, param_name="COUPON", target_price=0.9,
                               lo=0.0, hi=0.1, N=1000, max_iter=5, **v))),
    ("grille", lambda c, v: __import__(
        "backend.app.api.simulation", fromlist=["x"]).grid_endpoint(
        schemas.GridRequest(**c, param_x="COUPON", x_min=0.01, x_max=0.03,
                             x_steps=2, param_y="M_BAR", y_min=0.4, y_max=0.6,
                             y_steps=2, N=800, **v))),
    ("mark_to_future", lambda c, v: __import__(
        "backend.app.api.pricing", fromlist=["x"]).mtf_endpoint(
        schemas.MtfRequest(**c, main_price=0.9, n_outer=30, n_inner=150,
                            n_dates=2, **v))),
    ("scenarios", lambda c, v: __import__(
        "backend.app.api.scenarios", fromlist=["x"]).scenarios_endpoint(
        schemas.ScenarioRequest(**c, spot_shocks=[0.0], vol_shocks=[0.0],
                                 N=800, **v))),
])
def test_chaque_analytique_bascule_sur_la_vie_restante(nom, appel):
    """Toutes les analytiques doivent répondre sur la MÊME jambe que le prix.

    Le contrôle porte sur le fait de basculer, pas sur une valeur : chaque
    analytique a sa propre sortie, mais toutes doivent annoncer `in_life` et une
    vie restante cohérente. Un endpoint ajouté plus tard sans passer par
    `residual_context_or_none` échouera ici.

    Les scénarios sont le cas piégeux : ils repricent dans des PROCESSUS
    séparés, donc l'état doit traverser une charge sérialisée et le script
    résiduel se reconstruire côté worker.
    """
    commun = dict(_champs_communs(), T=3.0, value_date=dt.date(2024, 6, 18),
                   maturity_date=dt.date(2027, 6, 14))
    em = appel(commun, {})
    assert em["in_life"] is False, nom

    vie = appel(commun, {"valuation_date": dt.date(2026, 6, 14)})
    assert vie["in_life"] is True, nom
    assert 0 < vie["years_remaining"] < 1.1, (nom, vie["years_remaining"])


def test_le_backtest_reste_a_l_emission_et_le_dit():
    """Seule analytique non alignée, et volontairement.

    Rejouer « émettre ce produit à diverses dates passées » n'a pas d'équivalent
    en cours de vie : c'est une étude de la structure, pas de l'exemplaire qu'on
    détient. Elle porte donc encore le bandeau d'avertissement à l'écran. Si un
    jour elle bascule, ce test tombera et rappellera de retirer le bandeau."""
    from backend.app.api import pricing as api_pricing
    res = api_pricing.backtest_endpoint(schemas.BacktestRequest(
        **_champs_communs(), T=3.0, valuation_date=dt.date(2026, 6, 14)))
    assert "in_life" not in res
