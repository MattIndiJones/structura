"""Ancrage du calendrier CONSTAT sur la date de valeur (PricingRequest.anchor).

Un CONSTAT porte des dates absolues, le moteur travaille en fractions d'année
depuis t=0. Sans ancre, t=0 = aujourd'hui : le même produit pricé avant trade
et rejoué après booking (api/deals.py ancre sur deal.value_date) ne résout pas
le même calendrier, et les deux prix diffèrent sans raison économique. Ces
tests vérifient que l'ancre traverse /api/price et la grille de stress — dont
les cellules sont repricées dans d'autres process, où une clé de payload non
relue se perdrait silencieusement.
"""
from datetime import date, timedelta

from backend.app.api.pricing import price_endpoint
from backend.app.core.schemas import PricingRequest
from backend.app.core.payscript.scenarios import compute_scenario_grid

# Le call n'est payé qu'à la date du CONSTAT : décaler l'ancre rapproche
# l'observation, donc rogne la valeur temps.
CALL_ON_CONSTAT = """
CONSTAT Obs
AT Obs:
  PAY MAX(S[1] - 1.0, 0) "call"
"""

UL = [dict(name="S1", ticker="", ccy="EUR",
           sigma=0.20, q=0.00, v0=0.04, kappa=2.0, theta=0.04, xi=0.35, rho_h=-0.70,
           alpha=0.20, beta=0.5, rho=-0.30, nu=0.40, sigma_fx=0.0, rho_sfx=0.0, ccyh=0.0)]

OBS_IN_2Y = {"OBS": (date.today() + timedelta(days=730)).isoformat()}
IN_1Y = date.today() + timedelta(days=365)


def _req(anchor):
    return PricingRequest(script=CALL_ON_CONSTAT, underlyings=UL, corr_matrix=[[1.0]],
                          r=0.03, T=0.25, N=4000, seed=42,
                          constats=OBS_IN_2Y, anchor=anchor)


def test_anchor_moves_the_effective_horizon_and_the_price():
    spot = price_endpoint(_req(None))
    forward = price_endpoint(_req(IN_1Y))

    # Observation à +2 ans du jour : ancrée à aujourd'hui elle tombe à 2 ans,
    # ancrée un an plus tard à 1 an. T=0.25 ne fait que plancher l'horizon
    # (effective_T_max ne raccourcit jamais), il ne le pilote pas ici.
    assert abs(spot.t_max_effective - 2.0) < 0.02
    assert abs(forward.t_max_effective - 1.0) < 0.02
    assert forward.price < spot.price


def test_anchor_defaults_to_today():
    """Ne rien envoyer doit rester strictement l'ancien comportement — sinon
    tous les appelants qui n'ont pas de date de valeur (comparateur, scan de
    réinvestissement) changeraient de prix sans le demander."""
    assert price_endpoint(_req(None)).price == price_endpoint(_req(date.today())).price


def test_scenario_grid_carries_the_anchor_to_its_workers():
    common = dict(underlyings=UL, corr_matrix=[[1.0]], r=0.03, T=2.0,
                  model="constant", seed=42, user_params={},
                  spot_shocks=[0.0], vol_shocks=[0.0], N=4000,
                  constat_values=OBS_IN_2Y)
    spot = compute_scenario_grid(CALL_ON_CONSTAT, **common)
    forward = compute_scenario_grid(CALL_ON_CONSTAT,
                                    constat_anchor=IN_1Y.isoformat(), **common)
    assert forward["base_price"] < spot["base_price"]
