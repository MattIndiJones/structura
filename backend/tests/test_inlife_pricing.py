"""Chantier B2 — le Pricer valorise en cours de vie.

Le mode ne se choisit pas, il se déduit de la date de valorisation : égale à la
constatation initiale on price à l'émission, postérieure on rejoue le passé sur
cours réels et on ne simule que la vie restante.

Les tests n'appellent pas Yahoo : ils fournissent un historique fabriqué, ce
qui permet de vérifier ce qui compte vraiment — que l'état du passé entre bien
dans la valeur.
"""
from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.app.api import inlife as api
from backend.app.core.schemas import UnderlyingParams

USER = SimpleNamespace(id=1, entity_id=1)

STRIKE = date(2024, 6, 14)
MATURITE = date(2027, 6, 14)

PHOENIX_MEMOIRE = """PARAM COUPON = 2%
PARAM M_CPN_BAR = 50%
PARAM M_KI_BAR = 50%

CONSTAT() OBS

AT OBS:
  SET DUE = DUE + COUPON
  SET CPN = INDIC(WOF >= M_CPN_BAR)
  PAY CPN * DUE
  SET DUE = (1 - CPN) * DUE

AT OBS.last:
  SET KI = INDIC(WOF < M_KI_BAR)
  PAY (1 - KI) * 1
  PAY KI * WOF
"""

CALENDRIER = {"OBS": {"start_date": "2024-06-14", "end_date": "2027-06-14",
                       "roll_date": "2024-09-14", "frequency": "3M",
                       "stub": "short_last", "convention": "following"}}


def _historique(depart: date, fin: date, apres: float, s0: float = 100.0):
    """Historique fabriqué, en cours NUS et sur JOURS OUVRÉS.

    La densité compte : le rejeu travaille sur une grille de 252 pas par an et
    positionne les constatations dessus. Un historique en jours calendaires —
    365 lignes par an — les ferait tomber trop tôt d'un bon tiers.

    Le titre vaut s0 jusqu'à la constatation initiale incluse, puis le niveau
    passé en second argument : un décrochage franc, pour que le test dise
    quelque chose de net."""
    dates, serie = [], []
    jour = depart
    while jour <= fin:
        if jour.weekday() < 5:
            dates.append(jour.isoformat())
            serie.append(s0 if jour <= STRIKE else apres)
        jour += timedelta(days=1)
    return {"dates": dates, "prices": {"UL.PA": serie}}


def _requete(**over):
    base = dict(
        script=PHOENIX_MEMOIRE,
        underlyings=[UnderlyingParams(name="U1", ticker="UL.PA", ccy="EUR",
                                       sigma=0.25, q=0.02)],
        corr_matrix=[[1.0]],
        r=0.03, N=2000, model="constant", constats=CALENDRIER,
        strike_date=STRIKE, value_date=date(2024, 6, 18),
        maturity_date=MATURITE, payment_date=date(2027, 6, 23),
        settlement_ccy="EUR",
    )
    base.update(over)
    return api.InLifePricingRequest(**base)


@pytest.fixture
def marche(monkeypatch):
    """Historique fabriqué : le titre glisse de 100 à 40, sous la barrière."""
    def _charger(tickers, debut, fin):
        return _historique(STRIKE - timedelta(days=7), date.fromisoformat(fin), 40.0)
    monkeypatch.setattr(api, "load_hist_prices", _charger)


def test_sans_date_de_valorisation_on_price_a_l_emission(marche):
    res = api.price_in_life(_requete(), USER)
    assert res["in_life"] is False
    assert res["past"]["observations_done"] == 0
    assert res["valuation_date"] == STRIKE.isoformat()


def test_avec_une_date_passee_le_produit_a_une_histoire(marche):
    res = api.price_in_life(_requete(valuation_date=date(2026, 6, 14)), USER)
    assert res["in_life"] is True
    # Huit, et non sept : le rejeu place les constatations sur une grille de
    # 252 pas par an, si bien que celle du 15/06/2026 partage le pas de la
    # date de valorisation du 14. Même quantification que la grille Monte
    # Carlo — à un jour près sur une date, pas sur un montant.
    assert res["past"]["observations_done"] == 8
    assert res["past"]["years_elapsed"] == pytest.approx(2.0, abs=0.01)
    assert res["past"]["years_remaining"] == pytest.approx(1.0, abs=0.01)


def test_le_niveau_initial_est_lu_dans_l_historique(marche):
    res = api.price_in_life(_requete(valuation_date=date(2026, 6, 14)), USER)
    # La clôture nue au 14/06/2024 sert de strike, faute de saisie explicite.
    assert res["past"]["strike_levels"]["U1"] == 100.0


def test_un_niveau_initial_saisi_l_emporte_sur_l_historique(marche):
    # Le term sheet fait foi : son strike peut différer de la clôture Yahoo.
    res = api.price_in_life(
        _requete(valuation_date=date(2026, 6, 14), strike_levels={"U1": 80.0}), USER)
    assert res["past"]["strike_levels"]["U1"] == 80.0
    # Strike plus bas ⇒ performance relative plus haute.
    assert res["past"]["worst_of"] == pytest.approx(0.5, abs=1e-6)


def test_la_memoire_accumulee_entre_dans_la_valeur(marche):
    """Le test qui justifie tout le chantier.

    Le sous-jacent décroche à 40 % dès le lendemain de la constatation
    initiale : sous la barrière de coupon, aucun coupon n'est versé et ils
    s'empilent. Une valorisation repartie de zéro les perdrait tous."""
    res = api.price_in_life(_requete(valuation_date=date(2026, 6, 14)), USER)
    memoire = res["past"]["memory"]
    assert memoire.get("DUE", 0) > 0, memoire
    # Huit constatations à 2 % jamais versées : la mémoire les a toutes.
    assert memoire["DUE"] == pytest.approx(0.16, abs=1e-6)


def test_valoriser_avant_la_constatation_initiale_est_refuse(marche):
    with pytest.raises(HTTPException) as exc:
        api.price_in_life(_requete(valuation_date=STRIKE - timedelta(days=1)), USER)
    assert exc.value.status_code == 422
    assert "précède la constatation initiale" in exc.value.detail


def test_valoriser_apres_la_maturite_est_refuse(marche):
    with pytest.raises(HTTPException) as exc:
        api.price_in_life(_requete(valuation_date=MATURITE), USER)
    assert exc.value.status_code == 422
    assert "plus d'optionnalité" in exc.value.detail


def test_sans_historique_un_produit_dependant_du_chemin_est_refuse(monkeypatch):
    monkeypatch.setattr(api, "load_hist_prices",
                        lambda t, d, f: {"dates": ["2024-06-14"], "prices": {}})
    with pytest.raises(HTTPException) as exc:
        api.price_in_life(_requete(valuation_date=date(2026, 6, 14)), USER)
    assert exc.value.status_code == 422
    assert "Historique absent" in exc.value.detail


ATHENA_SANS_MEMOIRE = """PARAM COUPON = 8%
PARAM M_AC_BAR = 100%
PARAM M_KI_BAR = 60%

CONSTAT() OBS

AT OBS:
  SET CALL = INDIC(WOF >= M_AC_BAR)
  PAY CALL * COUPON * INDEX
  PAY CALL * 1
  IF CALL = 1:
    STOP

AT OBS.last:
  SET KI = INDIC(WOF < M_KI_BAR)
  PAY (1 - KI) * 1
  PAY KI * WOF
"""


def test_les_parametres_du_script_ne_sont_pas_de_la_memoire(marche):
    """Ce que l'environnement du moteur mélange, la réponse doit trier.

    `ctx["memo"]` porte les PARAM du script à côté des variables que le passé
    a réellement écrites. Les renvoyer ensemble invitait l'écran à les
    additionner : sur cet Athena, COUPON 8 % + barrière 100 % + barrière 60 %
    s'affichaient comme 168 % de coupons accumulés — sur un produit qui en
    valait 75. Un Athena n'a pas de mémoire du tout."""
    res = api.price_in_life(
        _requete(script=ATHENA_SANS_MEMOIRE, valuation_date=date(2026, 6, 14)), USER)
    memoire = res["past"]["memory"]
    for param in ("COUPON", "M_AC_BAR", "M_KI_BAR"):
        assert param not in memoire, memoire
    # Reste l'état écrit par le rejeu : l'indicateur d'autocall, à zéro
    # puisque le sous-jacent est sous la barrière depuis le premier jour.
    assert memoire == {"CALL": 0}, memoire


def test_un_produit_a_memoire_garde_la_sienne(marche):
    """Le filtre ne doit pas emporter ce qu'il est censé préserver."""
    res = api.price_in_life(_requete(valuation_date=date(2026, 6, 14)), USER)
    memoire = res["past"]["memory"]
    assert memoire["DUE"] == pytest.approx(0.16, abs=1e-6)
    assert "COUPON" not in memoire and "M_CPN_BAR" not in memoire


def test_la_reponse_porte_les_memes_statistiques_que_le_pricing_normal(marche):
    """Médiane, VaR, probabilités : l'écran les affichait en tirets.

    L'endpoint ne renvoyait que prix, IC et flux. Toutes les cases
    statistiques du panneau de résultats restaient vides dès qu'on valorisait
    en cours de vie — sans que rien n'indique qu'elles n'existaient pas."""
    res = api.price_in_life(_requete(valuation_date=date(2026, 6, 14)), USER)
    for cle in ("median", "var5", "prob_gt100", "payoffs", "elapsed_ms",
                "n_paths", "t_max_effective"):
        assert cle in res, f"{cle} absent de la réponse"
    assert res["payoffs"], "distribution des payoffs vide"
    assert res["t_max_effective"] == pytest.approx(res["past"]["years_remaining"], abs=1e-6)


def test_la_courbe_de_dividende_atteint_le_moteur(marche):
    """Le prix doit bouger — sinon la courbe est saisie pour rien.

    L'instantané passé au rejeu ne portait que nom, vol et dividende plat :
    la courbe, comme toute la calibration Heston/SABR, retombait sur les
    défauts. On pouvait la modifier à l'écran sans effet."""
    plat = api.price_in_life(_requete(valuation_date=date(2026, 6, 14)), USER)["price"]
    charge = api.price_in_life(_requete(
        valuation_date=date(2026, 6, 14),
        underlyings=[UnderlyingParams(name="U1", ticker="UL.PA", ccy="EUR",
                                       sigma=0.25, q=0.02,
                                       dividend_curve=[[1.0, 0.10], [2.0, 0.10], [3.0, 0.10]])],
    ), USER)["price"]
    assert abs(charge - plat) > 1e-3, (plat, charge)


def test_la_courbe_de_taux_atteint_le_moteur(marche):
    """Même contrôle pour les taux : le champ existait, il ne partait pas."""
    plat = api.price_in_life(_requete(valuation_date=date(2026, 6, 14)), USER)["price"]
    courbe = api.price_in_life(_requete(
        valuation_date=date(2026, 6, 14),
        yield_curve=[[0.5, 0.01], [1.0, 0.05], [2.0, 0.08]],
    ), USER)["price"]
    assert abs(courbe - plat) > 1e-4, (plat, courbe)


def test_les_greeks_se_calculent_sur_la_jambe_residuelle(marche):
    """Les sensibilités doivent être celles du produit tel qu'il EST devenu.

    Elles passaient par /api/price, qui bumpe le produit neuf depuis t=0 :
    des Greeks d'émission affichés à côté d'un mark-to-market. Sur ce test le
    sous-jacent a décroché à 40 % dès le lendemain du strike et la barrière de
    coupon est franchie à la baisse — le delta résiduel n'a aucune raison de
    ressembler à celui du même produit à l'émission."""
    res = api.price_in_life(_requete(
        valuation_date=date(2026, 6, 14),
        compute_greeks=True, selected_greeks=["delta", "vega"]), USER)
    g = res["greeks"]
    assert g, "aucun greek renvoyé"
    assert "delta_1" in g and "vega_1" in g, sorted(g)
    # Un produit vivant a une sensibilité non nulle à son sous-jacent.
    assert abs(g["delta_1"]) > 1e-6


def test_sans_demande_explicite_aucun_greek_n_est_calcule(marche):
    """Le bump-and-reprice coûte plusieurs fois le prix : il ne se déclenche
    pas tout seul à chaque valorisation."""
    res = api.price_in_life(_requete(valuation_date=date(2026, 6, 14)), USER)
    assert res["greeks"] == {}


# ── Spread émetteur ───────────────────────────────────────────────────

def test_le_funding_fait_BAISSER_le_prix(marche):
    """Le test qui garde le signe.

    Un spread émetteur n'actualise que les flux : chaque flux positif ne peut
    que valoir moins. Si ce test passe au rouge, c'est que le spread a été
    branché quelque part où il touche aussi le drift."""
    sans = api.price_in_life(_requete(valuation_date=date(2026, 6, 14)), USER)["price"]
    avec = api.price_in_life(_requete(valuation_date=date(2026, 6, 14),
                                       funding_spread=0.02), USER)["price"]
    assert avec < sans, (sans, avec)


def test_funding_et_taux_agissent_en_sens_OPPOSES(marche):
    """La raison d'être de la séparation, en un test.

    Monter la courbe de TAUX monte aussi le forward des sous-jacents, et sur
    une note ce second effet l'emporte : le prix monte. Monter le spread
    ÉMETTEUR n'actualise que les flux : le prix baisse. Router le funding dans
    la courbe de taux donnerait donc le signe inverse — une note qui vaut plus
    cher à mesure que son émetteur se dégrade."""
    ref = api.price_in_life(_requete(valuation_date=date(2026, 6, 14)), USER)["price"]
    taux = api.price_in_life(_requete(
        valuation_date=date(2026, 6, 14),
        yield_curve=[[2.5, 0.05], [3.0, 0.05], [3.5, 0.05]]), USER)["price"]
    credit = api.price_in_life(_requete(
        valuation_date=date(2026, 6, 14), funding_spread=0.02), USER)["price"]
    assert taux > ref > credit, (taux, ref, credit)


def test_le_funding_ne_touche_pas_le_drift(marche):
    """Contrôle direct : à spread nul le prix est celui d'avant, au bit près.

    Une courbe de funding vide et un niveau plat à zéro doivent laisser le
    chemin de pricing historique exactement inchangé."""
    ref = api.price_in_life(_requete(valuation_date=date(2026, 6, 14)), USER)["price"]
    neutre = api.price_in_life(_requete(valuation_date=date(2026, 6, 14),
                                         funding_spread=0.0,
                                         funding_curve=[]), USER)["price"]
    assert neutre == ref


def test_le_greek_de_credit_vaut_a_peu_pres_moins_prix_fois_duree(marche):
    """Sensibilité au spread : signe négatif, et ordre de grandeur −P×D.

    C'est le contrôle de cohérence qui attrape une erreur d'échelle : la
    dérivée est rendue par unité de spread, le desk lira le centième."""
    res = api.price_in_life(_requete(
        valuation_date=date(2026, 6, 14),
        compute_greeks=True, selected_greeks=["credit"]), USER)
    credit = res["greeks"]["credit"]
    assert credit < 0, credit
    attendu = -res["price"] * res["past"]["years_remaining"]
    assert credit == pytest.approx(attendu, rel=0.35), (credit, attendu)


def test_le_spread_implicite_retrouve_celui_qui_a_produit_le_prix(marche):
    """Aller-retour : on price à 150 bps, on redemande le spread du prix obtenu."""
    connu = 0.015
    prix = api.price_in_life(_requete(valuation_date=date(2026, 6, 14),
                                       funding_spread=connu), USER)["price"]
    res = api.implied_funding(api.ImpliedFundingRequest(
        **_requete(valuation_date=date(2026, 6, 14)).model_dump(),
        target_price=prix), USER)
    assert res["converged"], res
    assert res["funding_spread"] == pytest.approx(connu, abs=5e-4), res["funding_spread"]


def test_un_prix_hors_d_atteinte_le_dit_au_lieu_de_converger_a_cote(marche):
    """Un prix que le seul crédit n'explique pas doit être refusé clairement.

    C'est le cas de l'ask de la note Marex : 55 % quand le modèle plafonne à
    47 % même en actualisant mieux que le sans-risque. Rendre la borne comme
    si c'était une solution laisserait croire à un spread négatif calibré."""
    with pytest.raises(HTTPException) as exc:
        api.implied_funding(api.ImpliedFundingRequest(
            **_requete(valuation_date=date(2026, 6, 14)).model_dump(),
            target_price=5.0), USER)
    assert exc.value.status_code == 422
    assert "hors d'atteinte" in exc.value.detail

# ── Règle A7 — les deux origines de l'axe des temps ─────────────────
#
# En cours de vie, une réponse porte DEUX origines à la fois, et les confondre
# est l'erreur qui est revenue le plus souvent pendant le chantier des 26-27/08 :
#
#   · le FUTUR — horizon simulé, `t` de la table de flux — se compte depuis la
#     DATE DE VALORISATION, parce que le Monte-Carlo résiduel ne simule que la
#     vie restante ;
#   · le PASSÉ — `years_elapsed`, flux réalisés, observations faites — se compte
#     depuis le STRIKE, qui reste l'origine du produit.
#
# Le symptôme d'un mauvais ancrage ne se lit pas dans une valeur isolée : le
# prix reste plausible. Il se lit en RECONSTRUISANT une date. C'est pourquoi ces
# tests ne comparent pas des nombres à des nombres — ils reconvertissent un `t`
# en date de calendrier et regardent où il tombe. La maturité d'un trois ans
# s'affichait dix mois trop tôt sans que rien d'autre ne bouge.
#
# Les dates de valorisation évitent volontairement les jours de constatation :
# une constatation ajustée qui tomberait le jour même rendrait « déjà faite ou
# pas encore » ambigu, et le test dirait alors quelque chose d'autre que ce
# qu'il prétend.

TENOR = (MATURITE - STRIKE).days / 365.25


def _annees(depuis: date, jusqu_a: date) -> float:
    return (jusqu_a - depuis).days / 365.25


@pytest.mark.parametrize("valuation", [
    date(2025, 7, 15),          # ~1 an écoulé
    date(2026, 7, 15),          # ~2 ans écoulés
    date(2027, 4, 15),          # dernier trimestre
])
def test_A7_l_horizon_simule_est_la_vie_restante_et_non_le_tenor(marche, valuation):
    """Ce qui est simulé, c'est ce qu'il reste — jamais le tenor d'origine."""
    res = api.price_in_life(_requete(valuation_date=valuation), USER)

    restant = _annees(valuation, MATURITE)
    assert res["t_max_effective"] == pytest.approx(restant, abs=0.01)
    # Et franchement inférieur au tenor : un horizon resté au tenor signifierait
    # que la vie déjà écoulée est simulée une seconde fois.
    assert res["t_max_effective"] < TENOR - 0.5


@pytest.mark.parametrize("valuation", [
    date(2025, 7, 15),
    date(2026, 7, 15),
])
def test_A7_les_t_du_flux_se_recomptent_depuis_la_valorisation(marche, valuation):
    """LE test de la règle : reconvertir le dernier `t` en date de calendrier.

    Ancré sur la valorisation, il tombe sur la maturité ; ancré sur le strike,
    il tombe trop tôt, exactement du temps déjà écoulé. Les deux lectures
    donnent le MÊME nombre et des dates différentes — d'où la reconstruction,
    qui est la seule façon de les distinguer."""
    res = api.price_in_life(_requete(valuation_date=valuation), USER)
    flux = res["flux_table"]
    assert flux, "aucun flux : le test ne prouverait rien"

    t_max = max(f["t"] for f in flux.values())
    jours = round(t_max * 365.25)
    depuis_valorisation = valuation + timedelta(days=jours)
    depuis_strike = STRIKE + timedelta(days=jours)

    assert abs((depuis_valorisation - MATURITE).days) <= 4, (
        f"le dernier flux tombe le {depuis_valorisation}, pas sur la maturité "
        f"{MATURITE} — l'axe du futur n'est pas ancré sur la valorisation")

    # Contrôle du contrôle : les deux lectures doivent être franchement
    # distinctes, sinon la première assertion passerait pour de mauvaises
    # raisons le jour où les deux origines se rapprochent.
    assert abs((depuis_strike - MATURITE).days) > 300, (
        "les deux ancrages donnent presque la même date : le test ne discrimine "
        "plus rien")


@pytest.mark.parametrize("valuation,faites", [
    (date(2025, 7, 15), 4),     # 4 constatations trimestrielles écoulées
    (date(2026, 7, 15), 8),
])
def test_A7_le_passe_se_compte_depuis_le_strike(marche, valuation, faites):
    """L'autre moitié de la règle : le passé garde le strike pour origine.

    Deux origines dans une même réponse — c'est précisément ce qui rend
    l'erreur facile, et ce qu'aucun test ne vérifiait."""
    res = api.price_in_life(_requete(valuation_date=valuation), USER)
    passe = res["past"]

    assert passe["years_elapsed"] == pytest.approx(
        _annees(STRIKE, valuation), abs=0.01)
    # Les deux moitiés doivent recomposer le produit : ni trou, ni recouvrement.
    assert passe["years_elapsed"] + passe["years_remaining"] == pytest.approx(
        TENOR, abs=0.02)
    assert passe["observations_done"] == faites


def test_A7_avancer_la_valorisation_deplace_la_frontiere(marche):
    """Le passé grossit, la vie restante fond, et la somme ne bouge pas.

    Une seule date de valorisation ne verrait pas un axe figé : il en faut trois
    pour prouver que la frontière se déplace, et qu'elle se déplace sans perdre
    ni dupliquer de temps."""
    total, reste_prec, faites_prec = None, None, -1
    for valuation in (date(2025, 7, 15), date(2026, 7, 15), date(2027, 4, 15)):
        passe = api.price_in_life(_requete(valuation_date=valuation), USER)["past"]
        reste, faites = passe["years_remaining"], passe["observations_done"]

        if reste_prec is not None:
            assert reste < reste_prec, "la vie restante ne diminue pas"
            assert faites > faites_prec, "les constatations faites n'augmentent pas"

        somme = passe["years_elapsed"] + reste
        if total is not None:
            assert somme == pytest.approx(total, abs=0.02), (
                "la somme passé + futur dérive : les deux axes ne se rejoignent plus")
        total, reste_prec, faites_prec = somme, reste, faites
