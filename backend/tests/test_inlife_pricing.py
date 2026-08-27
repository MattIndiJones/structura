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
