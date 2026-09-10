"""Les sensibilités d'un deal vivant sont celles de ce qu'il est devenu.

Un produit à mi-vie n'est plus celui qu'on a booké : sa barrière est franchie ou
non, ses coupons mémoire sont acquis ou non, son compteur d'observations a
avancé, et son sous-jacent n'est plus à 100 % du strike. `compute_greeks`
ignorait tout cela et bumpait un produit neuf — et ce sont ces Greeks-là qui
alimentent `deal.greeks_json`, donc l'agrégation de risque du portefeuille.

Ces tests opposent systématiquement le même produit avec et sans son état : ce
qui les sépare est exactement l'erreur qui était publiée sur le livre.
"""
import math

import pytest

from backend.app.core.payscript.parser import parse_script, CompiledScript
from backend.app.core.payscript.engine import (
    run_mc, compute_greeks, _shift_events_for_mtf, SY,
)
from backend.app.api.deals import _residual_greeks, _greeks_state


def _ul(sigma=0.20, q=0.0):
    return [dict(name="S1", ticker="", ccy="EUR",
                 sigma=sigma, q=q, v0=0.04, kappa=2.0, theta=0.04, xi=0.35, rho_h=-0.70,
                 alpha=0.20, beta=0.5, rho=-0.30, nu=0.40,
                 sigma_fx=0.0, rho_sfx=0.0, ccyh=0.0)]


CORR = [[1.0]]
R = 0.03

KI_PUT = """
PARAM KI_BAR = 60%  "barriere de perte en capital"

AT MATURITY
  SET KI = INDIC(S_MIN[1] < KI_BAR)
  PAY (1 - KI) * 1 + KI * WOF "remboursement"
"""

DEGRESSIF = """
PARAM() M_AC_BAR = 110%  "barriere de rappel degressive"
PARAM CPN = 5%           "coupon"

AT 0.5, 1, 1.5
  IF WOF >= M_AC_BAR
    PAY 1 + CPN "rappel"
    STOP

AT MATURITY
  PAY 1 "capital"
"""

REALVOL = """
AT MATURITY
  PAY REALVOL "volatilite realisee"
"""

COUPON_CETTE_SEMAINE = """
PARAM CPN = 5%  "coupon"

AT 0.01, 0.5, 1
  PAY CPN "coupon"

AT MATURITY
  PAY 1 "capital"
"""


def _greeks(script_text, *, state=None, selected=("delta",), T=1.0, sigma=0.20,
            q=0.0, user_params=None, compiled=None, N=8000):
    cs = compiled if compiled is not None else parse_script(script_text)
    return compute_greeks(cs, _ul(sigma, q), CORR, r=R, T=T, N=N,
                          model="constant", seed=42,
                          user_params=user_params or {}, selected=list(selected),
                          state=state)


def _state(spot, **kw):
    """État lifecycle minimal : tout ce que `_mtm_core` transporte, neutre par
    défaut sauf ce que le test veut mettre en scène."""
    base = {"spot_base": [spot], "wof_min": None, "bof_max": None, "index": 0,
            "memo": None, "accum": 0.0, "s_min": None, "s_max": None,
            "s_prev": None, "realvol_state": None, "fix_state": None}
    base.update(kw)
    return base


# ── Les faits réalisés ne se dé-réalisent pas sous un bump ─────────────────

def test_barriere_deja_franchie_rend_le_produit_lineaire():
    """Barrière de perte en capital déjà touchée (minimum réalisé à 50 %, sous
    les 60 % contractuels) : le put est vivant sur 100 % des trajectoires, le
    produit vaut le sous-jacent, son delta est celui d'un forward — le niveau
    de spot lui-même, 0,80 dans ces unités par 100 % de variation relative.

    Sans l'état, le moteur repart d'un minimum vierge : à 1 % de volatilité
    depuis 80 %, la barrière de 60 % n'est jamais atteinte, le produit paraît
    protégé et son delta tombe à zéro. Deux produits différents."""
    avec = _greeks(KI_PUT, sigma=0.01, state=_state(0.8, s_min=[0.5]))
    assert avec["delta_1"] == pytest.approx(0.8, abs=0.05), avec

    sans = _greeks(KI_PUT, sigma=0.01, state=_state(0.8))
    assert abs(sans["delta_1"]) < 0.05, sans


def test_le_rang_d_observation_choisit_la_bonne_ligne_de_barriere():
    """Barrière de rappel dégressive [110 %, 100 %, 90 %] : à la troisième
    observation, un spot à 95 % rappelle ; à la première, il teste 110 % et ne
    rappelle pas — deux produits, deux deltas.

    Ce que le test vérifie a changé avec le rang par échéancier. Avant, la
    troisième observation se désignait en héritant un compteur (`index=2`) ;
    désormais le rang est porté par la DATE et survit au décalage résiduel, donc
    il n'y a plus rien à hériter : le script résiduel de ce deal à mi-vie ne
    contient que sa dernière date, et cette date porte le rang 3.

    C'est une propriété plus forte que l'ancienne — le produit ne peut plus se
    tromper de ligne parce qu'un appelant a oublié de transmettre un état."""
    up = {"M_AC_BAR": [1.10, 1.00, 0.90]}
    cs = parse_script(DEGRESSIF)
    assert cs.events[0].ranks == [1, 2, 3]

    # Le deal vu à un an : il ne reste que la constatation de 1,5 an, qui porte
    # le rang 3 et lit donc 90 %.
    residuel = CompiledScript(events=_shift_events_for_mtf(cs.events, 1.0),
                              init_fn=cs.init_fn, params=cs.params,
                              constats=cs.constats, has_stop=cs.has_stop)
    assert residuel.events[0].ranks == [3], residuel.events[0].ranks

    a_mi_vie = _greeks(None, compiled=residuel, sigma=0.05, T=0.5,
                       user_params=up, state=_state(0.95))
    au_depart = _greeks(DEGRESSIF, sigma=0.05, T=1.5, user_params=up,
                        state=_state(0.95))
    assert abs(a_mi_vie["delta_1"] - au_depart["delta_1"]) > 0.2 * max(
        abs(au_depart["delta_1"]), 1e-6), f"mi-vie={a_mi_vie}, départ={au_depart}"


def test_le_niveau_de_reference_de_la_vol_realisee_suit_le_bump():
    """La volatilité réalisée ne dépend pas du niveau du sous-jacent : son delta
    doit être nul.

    Il ne l'est que si le niveau de départ de la série de rendements est
    recalculé sur le spot bumpé. Sinon la jambe haute encaisse un premier
    rendement fantôme de log(1,01) — un saut de 1 % en une semaine, soit ~7 %
    de vol annualisée injectés de nulle part."""
    g = _greeks(REALVOL, sigma=0.01,
                state=_state(1.3, realvol_state={"sumsq": 0.02, "t": 0.5}))
    assert abs(g["delta_1"]) < 0.05, g


def test_le_bump_est_relatif_au_spot_du_jour():
    """Sur un forward prépayé, le prix vaut le spot : le delta doit donc valoir
    le spot lui-même. Un bump pris autour de 1,0 au lieu du spot courant
    donnerait le même chiffre quel que soit le niveau du deal."""
    fwd = 'AT MATURITY\n  PAY S[1] "forward"'
    for spot in (0.7, 1.0, 1.4):
        g = _greeks(fwd, sigma=0.05, state=_state(spot))
        assert g["delta_1"] == pytest.approx(spot, abs=0.02), f"spot={spot}: {g}"


# ── Theta : la décroissance temporelle, séparée du flux qu'elle enjambe ────

def test_le_coupon_de_la_semaine_est_isole_du_theta():
    """Un coupon de 5 % détaché dans la semaine de vieillissement vaut −0,7 par
    jour s'il est compté comme du theta : vrai au niveau du deal, ininterprétable
    une fois sommé sur le livre, où il écrase toutes les vraies décroissances.

    Le flux est donc reporté à part, et le theta ne mesure que la décroissance
    d'un produit dont l'observation a été retirée des deux côtés."""
    g = _greeks(COUPON_CETTE_SEMAINE, selected=("theta",), state=_state(1.0))
    ev = g["theta_event"]
    assert g["theta"] is None
    assert ev is not None and ev["reason"] == "observation_transition_required"


def test_pas_d_evenement_dans_la_semaine_pas_de_decomposition():
    """Cas courant : rien ne tombe dans la fenêtre, le theta est la simple
    différence de prix et aucun événement n'est signalé."""
    g = _greeks('AT MATURITY\n  PAY MAX(S[1] - 1, 0) "call"', selected=("theta",),
                state=_state(1.0))
    assert g["theta_event"] is None
    assert g["theta"] is not None and g["theta"] < 0


def test_le_compteur_avance_quand_une_observation_est_enjambee():
    """L'observation franchie doit incrémenter le compteur d'observations.

    Sans cet incrément, le produit vieilli relit la ligne de barrière qu'il vient
    de consommer : sur une barrière dégressive [110 %, 100 %, 90 %], il retesterait
    100 % au lieu de 90 % et, à 95 % de spot, ne rappellerait pas alors qu'il
    devrait. Le theta comparerait alors deux produits économiquement différents.

    Vérifié contre la différence finie écrite à la main, avec l'incrément
    explicite — la même technique de boucle de référence que les tests de
    vectorisation Heston et SABR."""
    up = {"M_AC_BAR": [1.10, 1.00, 0.90]}
    cs = parse_script(DEGRESSIF)
    # Décalage de 0.49 an : l'observation de 0.5 tombe à 0.01, dans la semaine.
    proche = CompiledScript(
        events=_shift_events_for_mtf(cs.events, 0.49), init_fn=cs.init_fn,
        params=cs.params, constats=cs.constats, has_stop=cs.has_stop)
    etat = _state(0.95, index=1)

    g = compute_greeks(proche, _ul(0.05), CORR, r=R, T=1.0, N=8000,
                       model="constant", seed=42, user_params=up,
                       selected=["theta"], state=etat)
    assert g["theta_event"] is not None and g["theta_event"]["terminates"] is True
    assert g["theta"] is None
    assert g["theta_event"]["reason"] == "observation_transition_required"


def test_theta_absent_plutot_que_faux_sur_un_etat_non_roulable():
    """Deux cas où vieillir d'une semaine demanderait d'inventer de l'état : une
    date de fixing dans la fenêtre (le fixing serait perdu de la moyenne au lieu
    d'y être replié) et un script à volatilité réalisée (la variance de la
    semaine est simulée d'un côté, il faudrait la deviner de l'autre). Mieux
    vaut pas de theta qu'un theta faux."""
    cs = parse_script('AT MATURITY\n  PAY WOF \"asiatique\"')
    fixe = CompiledScript(events=cs.events, init_fn=cs.init_fn, params=cs.params,
                          constats=cs.constats, strike_fix_dates=[1 / 104],
                          strike_fix_reduction='AVG')
    g = _greeks(None, compiled=fixe, selected=("theta",), state=_state(1.0))
    assert g["theta"] is None and g["theta_event"]["reason"] == "fenetre_strike_fix"

    g2 = _greeks(REALVOL, selected=("theta",), sigma=0.05,
                 state=_state(1.0, realvol_state={"sumsq": 0.02, "t": 0.5}))
    assert g2["theta"] is None and g2["theta_event"]["reason"] == "realvol"


# ── Unités consommées par les notes PDF ───────────────────────────────────

def _ctx(script_text, spot, **state_kw):
    """ctx minimal, dans la forme que `_mtm_core` produit."""
    cs = parse_script(script_text)
    return {
        "residual_script": cs, "engine_uls": _ul(0.20), "corr": CORR,
        "r_frac": R, "T_remaining": 1.0, "N_used": 8000, "model_used": "constant",
        "user_params": {}, "sigma_r": 0.0, "a_r": 0.0, "yc": [],
        "barrier_monitoring": "weekly", "antithetic": True,
        "underlyings_json": [{"name": "S1", "ticker": ""}],
        "norm_spots": [spot],
        "state": {"wof_min": None, "bof_max": None, "index": 0, "memo": None,
                  "accum": 0.0, "s_min": None, "s_max": None, "s_prev": None,
                  "realvol_state": None, "fix_state": None, **state_kw},
    }


def test_les_unites_des_notes_pdf_sont_preservees():
    """Les notes de valorisation lisent des points de nominal. Le delta partage
    déjà la même échelle que le Greek brut ; le gamma doit être remis à l'échelle
    d'un bump de 1 %. Un facteur 100 introduit ici serait invisible ailleurs."""
    ctx = _ctx('AT MATURITY\n  PAY MAX(S[1] - 1, 0) "call"', 1.0)
    brut = compute_greeks(ctx["residual_script"], ctx["engine_uls"], CORR, r=R,
                          T=1.0, N=8000, model="constant", seed=42, user_params={},
                          selected=["delta", "gamma", "vega"],
                          antithetic=True, state=_greeks_state(ctx))
    pdf = _residual_greeks(ctx, 8000)[0]
    assert pdf["delta_pts"] == pytest.approx(brut["delta_1"], abs=0.005)
    assert pdf["gamma_pts"] == pytest.approx(brut["gamma_1"] * 0.01, abs=0.005)
    assert pdf["vega_pts"] == pytest.approx(brut["vega_1"], abs=0.005)


def test_le_vega_des_notes_existe_desormais_hors_gbm():
    """Le vega des notes était systématiquement absent sous Heston : il bumpait
    un champ `sigma` que ce modèle n'utilise pas. Il passe maintenant par
    l'entrée de volatilité du simulateur, honorée par les cinq modèles."""
    ctx = _ctx('AT MATURITY\n  PAY MAX(S[1] - 1, 0) "call"', 1.0)
    ctx["model_used"] = "heston"
    assert _residual_greeks(ctx, 8000)[0]["vega_pts"] is not None


def test_vega_heston_respecte_la_martingale_du_payoff_lineaire():
    """PAY S n'a aucune exposition à la volatilité sous mesure risque-neutre."""
    cs = parse_script("AT MATURITY:\n  PAY S[1]")
    ul = _ul(0.20)
    ul[0].update(v0=0.04, kappa=2.0, theta=0.04, xi=0.35, rho_h=-0.70, q=0.0)
    g = compute_greeks(cs, ul, CORR, r=0.03, T=1.0, N=40000,
                       model="heston", seed=42, user_params={}, selected=["vega"])
    assert abs(g["vega_1"]) < 0.005
