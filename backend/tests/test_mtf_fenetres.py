"""Mark-to-Future et vie résiduelle face aux constatations sur période — §24.

Une constatation moyennée dont la fenêtre est À CHEVAL sur la date de marque a
des relevés déjà constatés et d'autres encore à venir. La valeur du contrat à
cette date combine les deux : les cours réalisés, comptés chacun une fois, et
les cours à simuler.

Les sondes sont DÉTERMINISTES : vol quasi nulle, dérive de 10 % par an, taux nul
— une trajectoire unique, connue d'avance, S(t) = exp(0,1 t). La valeur attendue
se calcule à la main, sans bruit Monte-Carlo, et quatre chemins suffisent.
"""
import math
from datetime import date, timedelta

import pytest

from backend.app.core.inlife_valuation import InLifeProduct, build_residual
from backend.app.core.payscript.engine import SY, run_mark_to_future, run_mc
from backend.app.core.payscript.parser import (
    effective_T_max, parse_script, resolve_constats,
)

STRIKE = date(2026, 9, 14)
MATURITE = date(2028, 9, 14)
DERIVE = 0.10

MOYENNE_FINALE = """CONSTAT MATURITE AVG

AT MATURITE:
  PAY WOF "moyenne"
"""

# Cinq relevés trimestriels sur la dernière année : 14/09/2027 … 14/09/2028.
CONSTATS = {"MATURITE": {"date": MATURITE.isoformat(), "window_length": "1Y",
                         "window_frequency": "3M"}}


def _ul():
    return [dict(name="U1", ticker="UL.PA", ccy="EUR", sigma=0.0001, q=-DERIVE,
                 v0=1e-8, kappa=2.0, theta=1e-8, xi=0.01, rho_h=-0.7,
                 alpha=0.0001, beta=0.5, rho=-0.3, nu=0.01,
                 sigma_fx=0.0, rho_sfx=0.0, ccyh=0.0)]


def _compile():
    return resolve_constats(parse_script(MOYENNE_FINALE), CONSTATS, anchor=STRIKE,
                            currency="EUR")


def _releves(cs):
    return list(cs.events[0].window_dates[0])


# ── Mark-to-Future ────────────────────────────────────────────────────

def test_le_mark_d_une_fenetre_a_cheval_compte_les_releves_deja_constates():
    """Marque à 83 semaines, sur la grille : trois relevés sont derrière, deux
    devant. Chaque scénario extérieur a CONSTATÉ les trois premiers ; le mark
    doit les reprendre et ne simuler que les deux derniers.

    Chaque relevé se lit à son pas hebdomadaire, sur le chemin extérieur s'il
    est passé, intérieur sinon — la trajectoire étant déterministe, les deux se
    raccordent et la moyenne attendue est celle des cinq pas."""
    cs = _compile()
    releves = _releves(cs)
    assert len(releves) == 5
    t0 = 83 / SY
    pas = sorted({round(t * SY) for t in releves})
    passes = [s for s in pas if s <= 83]
    assert len(passes) == 3, pas

    attendu = 100 * sum(math.exp(DERIVE * s / SY) for s in pas) / len(pas)
    res = run_mark_to_future(cs, _ul(), [[1.0]], r=0.0,
                             T_max=effective_T_max(cs, 2.0), main_price=100.0,
                             model="constant", n_outer=2, n_inner=2, seed=1,
                             mtm_dates=[t0])
    marks = res["results"][0]["pvs"]
    assert marks == pytest.approx([attendu, attendu], abs=0.05), (attendu, marks)


# ── MtM résiduel d'un deal ────────────────────────────────────────────

def _historique(jusqu_a: date):
    """Clôtures des jours ouvrés, 100 au strike puis exp(0,1 t)."""
    dates, serie, jour = [], [], STRIKE - timedelta(days=7)
    while jour <= jusqu_a:
        if jour.weekday() < 5:
            dates.append(jour.isoformat())
            t = max((jour - STRIKE).days, 0) / 365.25
            serie.append(100.0 * math.exp(DERIVE * t))
        jour += timedelta(days=1)
    return {"UL.PA": serie}, dates


VALO = date(2028, 4, 14)


def _residuel(valo=VALO, script=MOYENNE_FINALE, constats=CONSTATS):
    prices, dates = _historique(valo)
    produit = InLifeProduct(
        script_snapshot=script,
        underlyings=[{"name": "U1", "ticker": "UL.PA", "ccy": "EUR"}],
        strike_levels={"U1": 100.0}, strike_date=STRIKE,
        value_date=STRIKE + timedelta(days=2),
        tenor=(MATURITE - STRIKE).days / 365.25, currency="EUR",
        payment_date=MATURITE + timedelta(days=3),
        market={"constats": constats, "r": 0.0, "model": "constant"},
    )
    return build_residual(produit, prices, dates, (valo - STRIKE).days / 365.25, valo)


def _etat_moteur(res):
    """Les arguments d'état d'un produit vivant, tels que l'API les transmet
    (`ResidualContext.mc_kwargs`)."""
    etat, spots = res.state, res.norm_spots
    return dict(spot_mult=spots, spot_base=spots,
                wof_min_init=etat["wof_min"], bof_max_init=etat["bof_max"],
                index_offset=etat["index"], memo_init=etat["memo"],
                accum_init=etat["accum"], s_min_init=etat["s_min"],
                s_max_init=etat["s_max"], s_prev_init=etat["s_prev"],
                wof0_init=min(spots), realvol_state_init=etat["realvol_state"],
                fix_state_init=etat["fix_state"])


def _moyenne_attendue_au(valo=VALO):
    """Trois clôtures réalisées, deux cours simulés à leur pas hebdomadaire
    depuis la valorisation — la trajectoire est déterministe."""
    t_ecoule = (valo - STRIKE).days / 365.25
    releves = _releves(_compile())
    realises = [math.exp(DERIVE * t) for t in releves if t <= t_ecoule]
    a_venir = [math.exp(DERIVE * (t_ecoule + round((t - t_ecoule) * SY) / SY))
               for t in releves if t > t_ecoule]
    assert (len(realises), len(a_venir)) == (3, 2)
    return (sum(realises) + sum(a_venir)) / 5


def test_le_mtm_d_une_fenetre_a_cheval_compte_les_releves_deja_constates():
    """Valorisation le vendredi 14/04/2028 : les relevés de septembre, décembre
    et mars ont leurs clôtures, ceux de juin et de septembre 2028 sont à venir.

    Attendu : la moyenne des trois clôtures réalisées et des deux cours
    simulés, chacun lu à son pas hebdomadaire depuis la valorisation."""
    res = _residuel()
    horizon = effective_T_max(res.residual_script, (MATURITE - VALO).days / 365.25)
    prix = run_mc(res.residual_script, _ul(), [[1.0]], 0.0, horizon, N=4,
                  model="constant", seed=1, **_etat_moteur(res))["price"]
    assert prix == pytest.approx(_moyenne_attendue_au(), abs=5e-4)


@pytest.mark.parametrize("semaines", [4, 10])
def test_le_mark_to_future_d_un_deal_vivant_repart_de_son_etat_rejoue(semaines):
    """Un Mark-to-Future lancé sur un produit en cours de vie compose deux
    passés : l'historique jusqu'à la valorisation, puis ce que chaque scénario
    extérieur constate jusqu'à la date de marque.

    À 4 semaines, les trois relevés réalisés viennent tous de l'historique. À 10
    semaines, celui du 14/06 est en plus tombé sur chaque scénario."""
    res = _residuel()
    horizon = effective_T_max(res.residual_script, (MATURITE - VALO).days / 365.25)
    attendu = 100 * _moyenne_attendue_au()
    mtf = run_mark_to_future(res.residual_script, _ul(), [[1.0]], r=0.0, T_max=horizon,
                             main_price=100.0, model="constant", n_outer=2, n_inner=2,
                             seed=1, state=_etat_moteur(res),
                             mtm_dates=[semaines / SY])
    assert mtf["results"][0]["pvs"] == pytest.approx([attendu, attendu], abs=0.05)


# ── La vol réalisée se raccorde à la date de marque ─────────────────────

VOL_REALISEE = """CONSTAT STRIKE_FIX AVG
CONSTAT MATURITE

AT MATURITE:
  PAY REALVOL "vol realisee"
"""


def test_la_vol_realisee_se_raccorde_a_la_date_de_marque():
    """Trajectoire déterministe, taux nul : le mark à un an vaut exactement le
    prix d'aujourd'hui. `REALVOL` enchaîne la variation quadratique du passé et
    celle des chemins intérieurs ; son premier rendement intérieur part du
    worst-of à la date de marque, qui doit être exprimé contre le même S0 que
    les chemins — la fenêtre de départ l'a fixé à sa moyenne, pas à 1."""
    cs = resolve_constats(parse_script(VOL_REALISEE), {
        "STRIKE_FIX": {"date": STRIKE.isoformat(), "window_length": "3M",
                       "window_frequency": "1M"},
        "MATURITE": MATURITE.isoformat()}, anchor=STRIKE, currency="EUR")
    horizon = effective_T_max(cs, 2.0)
    prix = run_mc(cs, _ul(), [[1.0]], 0.0, horizon, N=4, model="constant",
                  seed=1)["price"] * 100
    mtf = run_mark_to_future(cs, _ul(), [[1.0]], r=0.0, T_max=horizon,
                             main_price=prix, model="constant", n_outer=2,
                             n_inner=2, seed=1, mtm_dates=[52 / SY])
    assert mtf["results"][0]["pvs"] == pytest.approx([prix, prix], abs=0.01), prix
    # Le panneau d'explication part du même worst-of que l'éventail.
    from backend.app.core.payscript.engine import run_mtf_drilldown
    panneau = run_mtf_drilldown(cs, _ul(), [[1.0]], r=0.0, T_max=horizon,
                                main_price=prix, t0=52 / SY, scenario_ids=[0, 1],
                                model="constant", n_outer=2, n_inner=2, seed=1,
                                mtm_dates=[52 / SY])
    assert [sc["mtf"] for sc in panneau["scenarios"]] == pytest.approx(
        mtf["results"][0]["pvs"], abs=1e-3)


# ── Les autres lecteurs du résiduel ──────────────────────────────────

def _mark_attendu():
    """La moyenne des cinq relevés à leur pas hebdomadaire — trajectoire
    déterministe, donc le même nombre qu'ils soient passés ou à venir."""
    pas = sorted({round(t * SY) for t in _releves(_compile())})
    return 100 * sum(math.exp(DERIVE * s / SY) for s in pas) / len(pas)


def test_le_drill_down_explique_le_meme_mark_que_l_eventail():
    """Le panneau d'explication rejoue les tirages de l'éventail : il doit
    compter les mêmes relevés constatés, sinon il explique un autre mark que
    celui qu'on lui montre."""
    from backend.app.core.payscript.engine import run_mtf_drilldown
    cs = _compile()
    t0 = 83 / SY
    commun = dict(r=0.0, T_max=effective_T_max(cs, 2.0), main_price=100.0,
                  model="constant", n_outer=2, n_inner=2, seed=1, mtm_dates=[t0])
    eventail = run_mark_to_future(cs, _ul(), [[1.0]], **commun)["results"][0]["pvs"]
    panneau = run_mtf_drilldown(cs, _ul(), [[1.0]], t0=t0, scenario_ids=[0, 1], **commun)
    assert [sc["mtf"] for sc in panneau["scenarios"]] == pytest.approx(eventail, abs=1e-3)
    assert eventail == pytest.approx([_mark_attendu()] * 2, abs=0.05)


def test_le_worker_de_var_reprice_la_meme_fenetre_que_le_mtm():
    """Le worker de VaR reconstruit le résiduel depuis le TEXTE du script : la
    part constatée doit voyager dans l'état sérialisé, sinon le scénario nul
    d'une étude de VaR s'écarte du MtM qu'il est censé reproduire."""
    import json
    from backend.app.core.compute.pricers.var_scenario import price_var_scenario_job
    res = _residuel()
    payload = json.loads(json.dumps({
        "script_text": MOYENNE_FINALE, "constat_values": CONSTATS,
        "value_date": (STRIKE + timedelta(days=2)).isoformat(),
        "strike_date": STRIKE.isoformat(), "settlement_ccy": "EUR",
        "T_elapsed": res.T_elapsed, "passe_jusqu_a": res.passe_jusqu_a,
        "state": res.state, "norm_spots": res.norm_spots, "engine_uls": _ul(),
        "corr": [[1.0]], "r_frac": 0.0,
        "T_remaining": effective_T_max(res.residual_script,
                                       (MATURITE - VALO).days / 365.25),
        "model_used": "constant", "yc": [], "sigma_r": 0.0, "a_r": 0.0,
        "antithetic": True, "user_params": {}, "barrier_monitoring": "weekly",
        "n_paths": 4}))
    assert price_var_scenario_job(payload)["price"] == pytest.approx(
        _moyenne_attendue_au(), abs=5e-4)


def test_la_grille_de_stress_reprice_la_meme_fenetre_que_le_mtm():
    """Même contrainte pour la grille : chaque cellule recompile le script dans
    son propre processus."""
    from backend.app.core.compute.pricers.scenario_grid import price_scenario_grid_job
    res = _residuel()
    etat = _etat_moteur(res)
    spots = etat.pop("spot_mult")
    etat.pop("spot_base")
    payload = dict(
        script_text=MOYENNE_FINALE, constat_values=CONSTATS,
        constat_anchor=STRIKE.isoformat(), constat_currency="EUR",
        underlyings=_ul(), corr=[[1.0]], r=0.0,
        T=effective_T_max(res.residual_script, (MATURITE - VALO).days / 365.25),
        n_paths=4, model="constant", seed=1, user_params={},
        spot_shock=0.0, vol_shock=0.0, yield_curve=[], sigma_r=0.0, a_r=0.0,
        barrier_monitoring="weekly", residual_state=etat, state_spots=spots,
        residual_elapsed=res.T_elapsed, residual_passe=res.passe_jusqu_a,
        residual_releves=res.state.get("releves_realises"))
    assert price_scenario_grid_job(payload)["price"] == pytest.approx(
        _moyenne_attendue_au(), abs=5e-4)
