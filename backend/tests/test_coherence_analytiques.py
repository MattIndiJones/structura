"""Cohérence interne des analytiques — deux calculs, une seule vérité.

Ce fichier est né d'un défaut précis. L'onglet Probabilités affichait « 32,2 %
de rappel » dans un compteur, et un graphe « P(rappel) par date » vide juste à
côté. Les deux décrivaient le MÊME événement à partir de deux calculs
indépendants — l'un compté sur les chemins, l'autre apparié par date — et rien
ne vérifiait qu'ils concordaient. Il a fallu qu'un calendrier mensuel passe sous
les yeux pour que l'écart se voie ; un trimestriel tombait juste par hasard.

Le motif se répète partout où un écran montre deux fois la même grandeur : un
total et sa ventilation, un compteur et son histogramme, un prix et sa table de
flux. Chacun de ces couples est un endroit où un fil peut se débrancher sans que
le résultat cesse d'être plausible.

D'où ces tests, qui n'affirment rien sur la JUSTESSE des chiffres — d'autres
fichiers s'en chargent — mais exigent que les deux voies **coïncident**. Une
égalité exacte là où elle doit l'être, une tolérance d'échantillonnage là où les
deux voies tirent séparément, et jamais l'inverse.

Le calendrier de référence est MENSUEL, délibérément : c'est celui qui a révélé
le défaut, et un trimestriel laisserait repasser la même erreur.
"""
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from backend.app.api import inlife as api_inlife
from backend.app.api import pricing as api_px
from backend.app.api import scenarios as api_sc
from backend.app.api import simulation as api_sim
from backend.app.core.schemas import (
    PathsRequest, ProbaRequest, ProfileRequest,
)
from backend.app.core.schemas import UnderlyingParams

USER = SimpleNamespace(id=1, entity_id=1)

STRIKE = date(2024, 6, 14)
MATURITE = date(2027, 6, 14)
VALORISATION = date(2026, 6, 14)

PHOENIX = """PARAM COUPON = 1%
PARAM M_AC_BAR = 100%
PARAM M_CPN_BAR = 50%
PARAM M_KI_BAR = 50%

CONSTAT() OBS

AT OBS:
  SET DUE = DUE + COUPON
  SET CPN = INDIC(WOF >= M_CPN_BAR)
  PAY CPN * DUE
  SET DUE = (1 - CPN) * DUE
  SET CALL = INDIC(INDEX >= 3) * INDIC(WOF >= M_AC_BAR)
  PAY CALL * 1
  IF CALL = 1:
    STOP

AT OBS.last:
  SET KI = INDIC(WOF < M_KI_BAR)
  PAY (1 - KI) * 1
  PAY KI * WOF
"""

# Mensuel : le pas qui a fait apparaître le défaut. Un trimestriel tombe juste
# par hasard (0,25 et 0,75 s'arrondissent à eux-mêmes) et ne prouverait rien.
MENSUEL = {"OBS": {"start_date": "2024-06-14", "end_date": "2027-06-14",
                   "roll_date": "2024-07-14", "frequency": "1M",
                   "stub": "short_last", "convention": "following"}}
TRIMESTRIEL = {"OBS": {**MENSUEL["OBS"], "frequency": "3M",
                       "roll_date": "2024-09-14"}}

UL = [UnderlyingParams(name="U1", ticker="UL.PA", ccy="EUR", sigma=0.45, q=0.0)]


def _historique():
    """80 % du strike deux ans, puis 40 % — assez de rappels pour compter."""
    dates, serie = [], []
    jour = STRIKE - timedelta(days=7)
    while jour <= VALORISATION:
        if jour.weekday() < 5:
            dates.append(jour.isoformat())
            serie.append(100.0 if jour <= STRIKE
                         else 80.0 if jour < date(2026, 1, 15) else 40.0)
        jour += timedelta(days=1)
    return {"dates": dates, "prices": {"UL.PA": serie}}


@pytest.fixture(autouse=True)
def marche(monkeypatch):
    monkeypatch.setattr(api_inlife, "load_hist_prices",
                        lambda tickers, debut, fin: _historique())


def _dates(en_vie: bool) -> dict:
    return dict(strike_date=STRIKE, maturity_date=MATURITE,
                value_date=date(2024, 6, 18), payment_date=date(2027, 6, 23),
                valuation_date=VALORISATION if en_vie else STRIKE,
                settlement_ccy="EUR", anchor=STRIKE)


def _proba(cal=MENSUEL, en_vie=True, N=6000):
    return api_px.proba_endpoint(ProbaRequest(
        script=PHOENIX, underlyings=UL, corr_matrix=[[1.0]], r=0.025, T=3.0,
        N=N, model="constant", seed=42, constats=cal, **_dates(en_vie)))


def _prix(en_vie=True, cal=MENSUEL, N=6000):
    return api_inlife.price_in_life(api_inlife.InLifePricingRequest(
        script=PHOENIX, underlyings=UL, corr_matrix=[[1.0]], r=0.025, N=N,
        model="constant", seed=42, constats=cal, **_dates(en_vie)), USER)


CALENDRIERS = [pytest.param(MENSUEL, id="mensuel"),
               pytest.param(TRIMESTRIEL, id="trimestriel")]


# ── Onglet Résultats : le prix et sa table de flux ──────────────────

@pytest.mark.parametrize("en_vie", [False, True], ids=["émission", "cours de vie"])
def test_la_table_de_flux_somme_au_prix(en_vie):
    """C'est ce qu'on attend d'une table de flux : expliquer le prix ligne à
    ligne. Si elle ne le somme pas, elle décrit un autre produit — et personne
    ne s'en apercevrait, puisque chaque ligne reste plausible."""
    res = _prix(en_vie=en_vie)
    total = sum(e["pv"] for e in res["flux_table"].values())
    assert total / res["n_eff"] == pytest.approx(res["price"], abs=1e-6)


@pytest.mark.parametrize("en_vie", [False, True], ids=["émission", "cours de vie"])
def test_l_intervalle_de_confiance_encadre_le_prix(en_vie):
    res = _prix(en_vie=en_vie)
    bas, haut = res["ic95"]
    assert bas < res["price"] < haut


# ── Onglet Probabilités : le compteur et sa ventilation ─────────────

@pytest.mark.parametrize("cal", CALENDRIERS)
def test_les_scenarios_se_partagent_tous_les_chemins(cal):
    """Rappel, perte et remboursement normal doivent couvrir l'échantillon
    exactement : un chemin non classé ne s'afficherait nulle part."""
    d = _proba(cal)
    assert d["autocall_count"] + d["ki_count"] + d["normal_count"] == d["total"]


@pytest.mark.parametrize("cal", CALENDRIERS)
def test_les_pourcentages_suivent_leurs_comptes(cal):
    """Deux expressions de la même grandeur, à l'arrondi près."""
    d = _proba(cal)
    assert d["autocall_pct"] == pytest.approx(d["autocall_count"] / d["total"] * 100, abs=0.05)
    assert d["ki_pct"] == pytest.approx(d["ki_count"] / d["total"] * 100, abs=0.05)


@pytest.mark.parametrize("cal", CALENDRIERS)
def test_la_ventilation_par_date_somme_au_compteur_de_rappels(cal):
    """LE défaut d'origine.

    `obs_times` sortait brut, les clés de `event_counts` arrondies à quatre
    décimales : l'appariement ratait dès qu'une date n'était pas ronde. Sur un
    calendrier mensuel, l'écran lisait 23 rappels sur 58 — graphe vide, donut
    tout rouge, et un compteur qui affichait pourtant 32 %."""
    d = _proba(cal)
    lisibles = sum(d["event_counts"].get(t, 0) for t in d["obs_times"])
    assert lisibles == d["autocall_count"]


@pytest.mark.parametrize("cal", CALENDRIERS)
def test_aucune_date_de_rappel_n_est_orpheline(cal):
    """Un compte dont la date n'est pas dans `obs_times` ne s'afficherait
    nulle part — c'est le même défaut vu par l'autre bout."""
    d = _proba(cal)
    assert not set(d["event_counts"]) - set(d["obs_times"])


@pytest.mark.parametrize("cal", CALENDRIERS)
def test_les_percentiles_sont_ordonnes(cal):
    d = _proba(cal)
    p = d["percentiles"]
    assert p["p5"] <= p["p25"] <= p["p75"] <= p["p95"]


@pytest.mark.parametrize("cal", CALENDRIERS)
def test_l_histogramme_couvre_tout_l_echantillon(cal):
    """`final_wofs` alimente le second graphe : il doit décrire les mêmes
    chemins que les compteurs, pas un sous-ensemble."""
    d = _proba(cal)
    assert len(d["final_wofs"]) == d["total"]


@pytest.mark.parametrize("cal", CALENDRIERS)
def test_le_prix_des_probabilites_rejoint_celui_des_resultats(cal):
    """Le recoupement le plus fort disponible : deux chemins de code entièrement
    distincts — `run_mc` et `run_mc_proba` — valorisent le même produit. Qu'ils
    concordent est ce qui rend crédible le reste de l'onglet ; qu'ils divergent
    signalerait qu'une hypothèse n'atteint pas l'un des deux.

    L'aide de l'écran prévient d'ailleurs que le prix des Probabilités est
    calculé sur un échantillon dédié : la tolérance couvre ce bruit, pas un
    écart de produit."""
    assert _proba(cal)["price"] == pytest.approx(_prix(cal=cal)["price"], rel=0.03)


@pytest.mark.parametrize("cal", CALENDRIERS)
def test_la_duree_esperee_reste_dans_la_vie_du_produit(cal):
    d = _proba(cal)
    assert 0 < d["expected_life"] <= 3.01


# ── Onglet Chemins MC ───────────────────────────────────────────────

@pytest.mark.parametrize("cal", CALENDRIERS)
def test_les_chemins_se_partagent_tous_les_tirages(cal):
    """La légende affiche trois pourcentages qui doivent faire 100 %."""
    d = api_px.paths_endpoint(PathsRequest(
        script=PHOENIX, underlyings=UL, corr_matrix=[[1.0]], r=0.025, T=3.0,
        model="constant", seed=42, constats=cal,
        N_stat=800, N_display=20, **_dates(True)))
    assert d["autocall_count"] + d["ki_count"] + d["normal_count"] == d["total"]
    assert len(d["path_data"]) <= d["total"]
    assert {p["outcome"] for p in d["path_data"]} <= {"autocall", "ki", "normal"}


# ── Entre onglets : la même grandeur, deux échantillons ─────────────

def test_le_fugit_et_la_duree_esperee_decrivent_la_meme_chose():
    """L'aide de l'écran l'affirme — « même quantité que le Fugit de l'onglet
    Résultats » — et personne ne le vérifiait. Les deux tirages diffèrent, donc
    on tolère le bruit ; ce qu'on refuse, c'est qu'ils décrivent deux produits.
    """
    fugit = _prix()["fugit"]
    esperee = _proba()["expected_life"]
    assert fugit == pytest.approx(esperee, rel=0.10), (fugit, esperee)


def _rupture(prof):
    """Le niveau où le payoff saute le plus — la barrière, telle que le
    diagramme la dessine."""
    xs, ys = prof["levels"], prof["payoffs"]
    i = max(range(len(ys) - 1), key=lambda k: abs(ys[k + 1] - ys[k]))
    return xs[i + 1]


def _profil(params=None):
    from backend.app.core.schemas import ProfileRequest
    return api_px.profile_endpoint(ProfileRequest(
        script=PHOENIX, underlyings=UL, corr_matrix=[[1.0]], r=0.025, T=3.0,
        model="constant", seed=42, constats=MENSUEL,
        user_params=params or {}, **_dates(True)))


def test_le_profil_dessine_la_barriere_du_script():
    """Le diagramme de payoff et le prix décrivent le même produit : la rupture
    du diagramme doit tomber sur la barrière de protection, pas ailleurs.

    C'est le même genre de recoupement que le reste du fichier — deux lectures
    d'une seule vérité — appliqué à un graphe plutôt qu'à un compteur."""
    assert _rupture(_profil()) == pytest.approx(50.0, abs=1.5)


def test_deplacer_la_barriere_deplace_la_rupture():
    """Sans ça, le test précédent passerait aussi sur un diagramme figé qui
    ignorerait le script. On exige que le dessin BOUGE."""
    assert _rupture(_profil({"M_KI_BAR": 0.30})) == pytest.approx(30.0, abs=1.5)
    assert _rupture(_profil({"M_KI_BAR": 0.70})) == pytest.approx(70.0, abs=1.5)


# ── Onglet Simulation : le solveur et sa grille ─────────────────────

def test_le_solveur_atteint_vraiment_le_prix_qu_il_annonce():
    """Le solveur rend une valeur de PARAM et un prix atteint. Repricer à cette
    valeur doit redonner ce prix — sinon il rend une solution qui n'en est pas
    une, et rien à l'écran ne le dirait."""
    from backend.app.core.schemas import SolverRequest
    cible = _prix()["price"] * 1.05
    sol = api_sim.solve_endpoint(SolverRequest(
        script=PHOENIX, underlyings=UL, corr_matrix=[[1.0]], r=0.025, T=3.0,
        model="constant", seed=42, constats=MENSUEL, param_name="M_KI_BAR",
        target_price=cible, lo=0.05, hi=0.95, N=4000, **_dates(True)))

    verif = api_inlife.price_in_life(api_inlife.InLifePricingRequest(
        script=PHOENIX, underlyings=UL, corr_matrix=[[1.0]], r=0.025, N=4000,
        model="constant", seed=42, constats=MENSUEL,
        user_params={"M_KI_BAR": sol["param_value"]}, **_dates(True)), USER)
    assert verif["price"] == pytest.approx(sol["achieved_price"], rel=0.02), (
        sol["param_value"], sol["achieved_price"], verif["price"])
    # Et le prix atteint doit bien être la cible demandée, sinon le solveur
    # rend une valeur cohérente avec elle-même mais qui rate son objectif.
    if sol["converged"]:
        assert sol["achieved_price"] == pytest.approx(sol["target_price"], abs=2e-3)


def test_la_grille_retombe_sur_le_prix_aux_valeurs_courantes():
    """Une case de la grille et le prix affiché décrivent le même produit dès
    que les deux paramètres valent ceux du script."""
    from backend.app.core.schemas import GridRequest
    g = api_sim.grid_endpoint(GridRequest(
        script=PHOENIX, underlyings=UL, corr_matrix=[[1.0]], r=0.025, T=3.0,
        model="constant", seed=42, constats=MENSUEL, N=4000,
        param_x="M_KI_BAR", x_min=0.50, x_max=0.90, x_steps=3,
        param_y="COUPON", y_min=0.01, y_max=0.03, y_steps=3, **_dates(True)))

    ref = api_inlife.price_in_life(api_inlife.InLifePricingRequest(
        script=PHOENIX, underlyings=UL, corr_matrix=[[1.0]], r=0.025, N=4000,
        model="constant", seed=42, constats=MENSUEL,
        user_params={"M_KI_BAR": 0.50, "COUPON": 0.01}, **_dates(True)), USER)
    # La case (x=0,50 ; y=0,01) est celle du script.
    assert g["prices"][0][0] == pytest.approx(ref["price"], rel=0.03), (
        g["prices"][0][0], ref["price"])


# ── Onglet Scénarios : la case sans choc EST le prix ────────────────

def test_le_scenario_sans_choc_redonne_le_prix():
    """La grille de stress se lit par rapport à son centre. Si la case
    (spot 0 %, vol 0 %) ne vaut pas le prix affiché, tous les écarts lus autour
    sont faux — et ils restent parfaitement plausibles."""
    from backend.app.core.schemas import ScenarioRequest
    sc = api_sc.scenarios_endpoint(ScenarioRequest(
        script=PHOENIX, underlyings=UL, corr_matrix=[[1.0]], r=0.025, T=3.0,
        model="constant", seed=42, constats=MENSUEL, N=3000,
        spot_shocks=[-0.10, 0.0, 0.10], vol_shocks=[0.05, 0.0, -0.05],
        **_dates(True)))
    i = sc["vol_shocks"].index(0.0)
    j = sc["spot_shocks"].index(0.0)
    ref = _prix(N=3000)["price"]
    assert sc["prices"][i][j] == pytest.approx(ref, rel=0.03), (sc["prices"][i][j], ref)


# ── Perte en capital : nominal contre valeur, deux questions ────────

GARANTI = "AT 3:\n  PAY 1\n"
ULS_SIMPLE = [{"name": "U1", "sigma": 0.30, "q": 0.0}]


def _proba_brut(script, **kw):
    from backend.app.core.payscript.parser import parse_script
    from backend.app.core.payscript.engine import run_mc_proba
    return run_mc_proba(parse_script(script), ULS_SIMPLE, [[1.0]], 0.03, 3.0,
                        N=3000, model="constant", seed=42, **kw)


def test_un_capital_garanti_n_annonce_aucune_perte():
    """Régression, et la plus grossière du lot.

    `capital_loss_pct` comparait le flux ACTUALISÉ à un pair NOMINAL de 1,0. Un
    produit qui rend exactement le pair à trois ans vaut 0,91 en valeur
    présente : il était donc compté en perte de capital sur CHAQUE chemin. La
    mesure annonçait 100 % de perte sur un produit où rien ne peut se perdre.

    Le classement des issues, lui, faisait déjà la lecture nominale une ligne
    plus haut — c'est cette mesure-là qui était seule à se tromper."""
    d = _proba_brut(GARANTI)
    assert d["capital_loss_pct"] == 0.0, d["capital_loss_pct"]
    assert d["ki_count"] == 0


def test_la_perte_en_capital_est_absente_de_l_analyse_de_prix():
    """Sans prix de référence, « récupère-t-on ce qu'on a payé » n'a pas de
    réponse. La rendre quand même la ferait comparer à un pair nominal — le
    défaut qu'on vient de corriger, recréé sous un autre nom."""
    assert _proba_brut(GARANTI)["net_loss_pct"] is None


def test_la_perte_nette_se_mesure_contre_le_prix_paye():
    """Deux valeurs présentes comparées entre elles. Payée sous sa valeur, la
    note ne perd rien ; payée au-dessus, elle perd toujours."""
    assert _proba_brut(GARANTI, capital_ref=0.80)["net_loss_pct"] == 0.0
    assert _proba_brut(GARANTI, capital_ref=0.99)["net_loss_pct"] == 100.0


def test_les_deux_mesures_repondent_bien_a_deux_questions():
    """Sur un produit risqué elles diffèrent, et c'est le but : perdre le pair
    et perdre ce qu'on a payé ne sont pas le même événement."""
    risque = ("PARAM M_KI = 70%\n"
              "AT 3:\n"
              "  SET KI = INDIC(WOF < M_KI)\n"
              "  PAY (1 - KI) * 1\n"
              "  PAY KI * WOF\n")
    d = _proba_brut(risque, capital_ref=0.60)
    assert 0 < d["capital_loss_pct"] < 100
    assert d["net_loss_pct"] != d["capital_loss_pct"]


@pytest.mark.parametrize("cal", CALENDRIERS)
def test_la_perte_en_capital_recoupe_le_compte_de_pertes(cal):
    """Les deux se lisent maintenant sur la même grandeur nominale : toute
    perte classée « KI » est une perte en capital, donc le compte de KI ne peut
    pas dépasser la mesure."""
    d = _proba(cal)
    assert d["capital_loss_pct"] >= d["ki_pct"] - 0.2, (d["capital_loss_pct"], d["ki_pct"])
