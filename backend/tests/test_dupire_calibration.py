"""La calibration Dupire tient-elle son identité de base ?

Une nappe implicite PLATE à σ₀ a pour vol locale σ₀ partout — ce n'est pas une
approximation, c'est une identité. Toute déviation est une erreur numérique, et
elle ne se signale nulle part : elle se contente de déplacer les prix.

L'inversion précédente, par différences finies sur des prix Black-Scholes,
divisait par un ∂²C/∂K² minuscule dans les ailes et approchait ∂C/∂T par une
différence AVANT sur un pas atteignant 23 % de la maturité. Elle rendait
jusqu'à 150 % de vol locale là où la réponse est 20 % — le plafond de la
fonction habillant la divergence en nombre plausible.

Les tests ci-dessous exigent l'identité elle-même, à trois niveaux : la vol
locale, le prix, et le delta. C'est le seul garde-fou qui aurait attrapé le
défaut, parce qu'aucune assertion de valeur ne peut distinguer un prix faux
d'un prix juste sans référence indépendante — et la nappe plate en est une.
"""
import pytest

from backend.app.core.payscript.engine import _dupire_vol, compute_greeks, run_mc
from backend.app.core.payscript.parser import parse_script, resolve_constats

SIGMA0, R, Q = 0.20, 0.03, 0.03

AUTOCALL = """PARAM COUPON = 8%
PARAM RAPPEL = 100%
PARAM M_BARRIERE = 60%

CONSTAT() OBS

AT OBS:
  IF WOF >= RAPPEL:
    PAY 1 + COUPON * INDEX
    STOP

AT OBS.last:
  SET KI = INDIC(WOF < M_BARRIERE)
  PAY (1 - KI) * 1
  PAY KI * WOF
"""

# Trimestriel : la première constatation tombe à T = 0,25, exactement la zone où
# l'ancienne inversion divergeait. Un calendrier annuel ne l'aurait pas vue.
CALENDRIER = {"OBS": {"start_date": "2026-09-03", "end_date": "2029-09-03",
                      "roll_date": "2026-12-03", "frequency": "3M",
                      "stub": "short_last", "convention": "following"}}


def _ul(skew: float = 0.0) -> list[dict]:
    return [{"name": "SX5E", "sigma": SIGMA0, "q": Q, "skew": skew, "curvature": 0.0}]


def _compile():
    from datetime import date
    return resolve_constats(parse_script(AUTOCALL), CALENDRIER,
                            anchor=date(2026, 9, 3), currency="EUR")


@pytest.mark.parametrize("T", [0.25, 0.5, 1.0, 3.0])
@pytest.mark.parametrize("K", [0.6, 0.8, 1.0, 1.2, 1.6])
def test_nappe_plate_donne_la_vol_locale_plate(K, T):
    """Le cœur du sujet. L'ancienne implémentation rendait 1,50000 en
    (K=0,60 ; T=0,25) — sept fois et demie la bonne réponse."""
    assert _dupire_vol(K, T, SIGMA0, 0.0, 0.0, R, Q) == pytest.approx(SIGMA0, abs=1e-4)


def test_nappe_plate_le_prix_localvol_egale_le_prix_vol_constante():
    """Même nappe, deux moteurs : le même produit doit valoir le même prix. Un
    écart ici est une erreur de calibration pure, puisqu'aucune hypothèse de
    marché ne les sépare."""
    c = _compile()
    args = dict(user_params={}, seed=42)
    cst = run_mc(c, _ul(), [[1.0]], R, 3.0, 40000, "constant", **args)["price"]
    lv = run_mc(c, _ul(), [[1.0]], R, 3.0, 40000, "localvol", **args)["price"]
    # 5 bps : ce qui reste est du bruit Monte Carlo entre deux diffusions
    # distinctes, pas un biais de calibration (l'ancienne version en montrait 27).
    assert lv == pytest.approx(cst, abs=0.0005)


def test_nappe_plate_le_delta_localvol_egale_le_delta_vol_constante():
    """Et l'identité doit tenir aussi sur la sensibilité — c'est elle que le
    desk couvre, et une calibration qui fabrique un faux skew fabrique d'abord
    un faux delta."""
    c = _compile()
    args = dict(user_params={}, seed=42, selected=["delta"])
    cst = compute_greeks(c, _ul(), [[1.0]], R, 3.0, 40000, "constant", **args)["delta_1"]
    lv = compute_greeks(c, _ul(), [[1.0]], R, 3.0, 40000, "localvol", **args)["delta_1"]
    assert lv == pytest.approx(cst, abs=0.01)


def test_le_skew_reste_un_skew():
    """Garde-fou en sens inverse : à force d'exiger l'identité sur nappe plate,
    on pourrait « corriger » jusqu'à ne plus rien calibrer du tout. Une nappe
    penchée doit produire une vol locale penchée, et plus fortement que la nappe
    implicite dont elle dérive."""
    bas = _dupire_vol(0.80, 1.0, SIGMA0, -0.30, 0.0, R, Q)
    haut = _dupire_vol(1.20, 1.0, SIGMA0, -0.30, 0.0, R, Q)
    assert bas > SIGMA0 > haut
    # L'implicite entre ces deux strikes varie de skew × log(1,2/0,8) ≈ 12 pts ;
    # la vol locale, elle, amplifie le skew — c'est sa propriété connue.
    assert (bas - haut) > 0.30 * (0.4055)
